#!/usr/bin/env python3
"""Resolve recovered source identities for the full Wasm game link.

Address metadata chooses equivalent source symbols only. It never provides
executable addresses or loads code from the original Windows executable.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess

from link_native import decode, encode

ROOT = Path(__file__).resolve().parents[1]


def identity(name):
    raw = decode(name)
    packed = raw.startswith('titbit_va_')
    raw = raw.removeprefix('titbit_va_')
    coff = raw[3:] if raw.startswith('\\01') else raw if raw.startswith('?') else '_' + raw
    return raw, coff, packed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--objects', type=Path, default=ROOT / 'build/web/objects-packed')
    parser.add_argument('--native', type=Path)
    parser.add_argument('--nm', default='llvm-nm')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/web/game-link')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / 'config/source-build.json').read_text())
    recipes = {r['source']: r for r in config['recipes']}
    bindings = {name: int(value, 16) for name, value in config['bindings'].items()}
    source_aliases = {r['alias']: r['provider'] for r in config['aliases']}
    source_aliases.update(json.loads((ROOT / 'config/source-aliases.json').read_text(encoding='utf-8-sig')))
    veneers = (ROOT / 'src/lanes/codex/import_veneers.cpp').read_text()
    for api, function in re.findall(r'// (\w+)[^\n]*\nextern "C" void \*g_[^;]+;\nextern "C" __declspec\(naked\) void(?: __stdcall)? (FUN_[0-9a-f]+)', veneers):
        source_aliases['_' + function] = '_' + api
    omitted = {'src/native/engine_entry_candidate.cpp', 'src/native/game_input.cpp',
               'src/lanes/codex/data/cxx_startup.c', 'src/seer/callasm.c',
               'src/lanes/codex/import_veneers.cpp'}
    rows = [r for r in json.loads((args.objects / 'report.json').read_text())['rows']
            if r['status'] == 'compiled' and r['source'] not in omitted]
    native_names = set()
    if args.native:
        for path in args.native.glob('*.o'):
            for line in subprocess.check_output([args.nm, '-g', '-P', str(path)], text=True).splitlines():
                fields = line.split()
                if len(fields) > 1 and fields[1] != 'U': native_names.add(fields[0])
    names = defaultdict(list)
    addresses = defaultdict(list)
    bycoff = {}
    fields = {}
    local_bindings = {}

    def address(name, source):
        raw, old, packed = identity(name)
        local = local_bindings.get(source, {})
        if old in local: return int(local[old], 16) if local[old] is not None else None
        for key in (Path(source).stem + ':' + old, old):
            if key in bindings: return bindings[key]
        if '@?1?' in old or old.startswith(('??_', '??1')): return None
        match = re.search(r'(?:004|005)[0-9a-fA-F]{5}', old.split('@', 1)[0] if old.startswith('?') else old)
        return int(match[0], 16) if match else None

    for row in rows:
        key = row['source'].replace('/', '__')
        row['ir'] = str((args.objects / (key + '.ll')).resolve())
        row['raw'] = str((args.objects / (key + '.packed.ms.ll')).resolve())
        row['out'] = str((args.out / (key + '.ll')).resolve())
        row['priority'] = recipes.get(row['source'], {}).get('priority', 0)
        local = dict(recipes.get(row['source'], {}).get('symbolAddresses', {}))
        spec = (ROOT / row['source']).with_suffix('.bindings.json')
        if spec.exists():
            data = json.loads(spec.read_text())
            local.update(data.get('bindings', {}))
            local.update({name: None for name in data.get('unboundSymbols', [])})
            fields.update(data.get('fieldAliases', {}))
        local_bindings[row['source']] = local
        row['definitions'], row['undefined'] = {}, []
        for line in subprocess.check_output([args.nm, '-g', '-P', row['object']], text=True).splitlines():
            tokens = line.split()
            if len(tokens) < 2: continue
            name, kind = tokens[:2]
            if kind == 'U': row['undefined'].append(name)
            else:
                row['definitions'][name] = kind
                names[name].append(row)
                bycoff[identity(name)[1]] = name
                value = address(name, row['source'])
                if value is not None: addresses[value].append((row['priority'], name))
    crt_names = ('fopen', 'fclose', 'fread', 'fwrite', 'fseek', 'ftell', 'fflush', 'fgetc', 'fputc',
                 'fgets', 'fputs', 'ungetc', 'setvbuf', 'vfprintf', 'fprintf', 'feof', 'ferror',
                 'fileno', 'tmpfile', 'stat', 'wcslen', 'itoa', 'fgetpos', 'fsetpos', 'rand',
                 'srand', 'clock', 'vprintf', 'vsprintf', 'vsnprintf', 'printf', 'sprintf',
                 'snprintf', 'sscanf', 'scanf', 'fscanf')
    crt = {name: 'tb_crt_' + name for name in crt_names}
    crt.update({'_filbuf': 'tb_crt_filbuf', '_flsbuf': 'tb_crt_flsbuf', '_fileno': 'tb_crt_fileno',
                '_filelength': 'tb_crt_filelength', '_errno': 'tb_crt_errno', '_iob': 'tb_crt_iob',
                '_pctype': 'tb_crt_pctype', '_isctype': 'tb_crt_isctype', '__mb_cur_max': 'tb_crt_mb_cur_max',
                '_strdup': 'strdup', '_itoa': 'tb_crt_itoa', '_purecall': 'titbit_purecall',
                '_vsnprintf': 'tb_crt_vsnprintf', '_snprintf': 'tb_crt_snprintf',
                '_setjmp3': 'emscripten_setjmp', 'stat32': 'tb_crt_stat'})
    special = {'??2@YAPAXI@Z': 'titbit_operator_new', '??3@YAXPAX@Z': 'titbit_operator_delete',
               '??_U@YAPAXI@Z': 'titbit_operator_new', '??_V@YAXPAX@Z': 'titbit_operator_delete',
               '??_7type_info@@6B@': 'titbit_type_info_vtable', '??_C@_00A@?$AA@': 'titbit_empty_text',
               '??_B?1???id@?$ctype@G@std@@$D@@9@51': 'titbit_iostream_setup_guard'}
    for old, value in bindings.items():
        if old.startswith('?') and '@@3' in old:
            plain = old[1:].split('@')[0]
            if plain in native_names: addresses[value].append((-100, plain))
        if old in special: addresses[value].append((-100, special[old]))

    def visibility_key(old): return re.sub(r'(@@)[AQIE](?=[AB][EG])', r'\1Q', old)
    visibility = {visibility_key(identity(name)[1]): name for name in names}
    field_aliases = {}
    for old, spec in fields.items():
        alias = encode(old) if old.startswith('?') else old.lstrip('_')
        field_aliases[alias] = spec['locator'].lstrip('_')
        value = address(alias, '') or bindings.get(old)
        if value is None:
            value = next((int(local[old], 16) for local in local_bindings.values() if local.get(old)), None)
        if value is not None: addresses[value].append((-1, alias))

    def resolve(name, source):
        raw, old, packed = identity(name)
        plain = raw[4:].split('@')[0] if raw.startswith('\\01_') else raw
        if plain.startswith(('gl', 'glu')) and 'tb_gl_stdcall_' + plain in native_names:
            return 'tb_gl_stdcall_' + plain
        if raw in crt:
            target = crt[raw]
            return 'titbit_va_' + target if packed else target
        if old in special: return special[old]
        if old in source_aliases:
            target = source_aliases[old]
            if target in special: return special[target]
            if target in bycoff: return bycoff[target]
            if target.startswith('?') and '@@3' in target:
                plain = target[1:].split('@')[0]
                if plain in native_names: return plain
            if target.startswith('_') and '@' not in target and '?' not in target:
                plain = target[1:]
                result = crt.get(plain, plain)
                return 'titbit_va_' + result if packed else result
        if raw.startswith('\\01_'):
            plain = raw[4:].split('@')[0]
            return crt.get(plain, plain)
        if visibility_key(old) in visibility: return visibility[visibility_key(old)]
        value = address(name, source)
        if value in addresses: return min(addresses[value])[1]
        if raw.startswith('?') and '@@3' in raw:
            plain = raw[1:].split('@')[0]
            if plain in native_names: return plain
        return None

    aliases, unresolved = {}, defaultdict(list)
    dispatch = set()
    for row in rows:
        for name in row['undefined']:
            if name in names or name in field_aliases: continue
            target = resolve(name, row['source'])
            if target and target != name: aliases[name] = target
            else: unresolved[decode(name)].append(row['source'])
        if row['source'] == 'src/lanes/engine41/script_api.cpp':
            dispatch.update(aliases.get(name, name) for name in row['undefined'])
    for name, spec in list(aliases.items()):
        seen = {name}
        while spec in aliases and spec not in seen:
            seen.add(spec)
            spec = aliases[spec]
        aliases[name] = spec
    plan = {'rows': sorted(rows, key=lambda row: (row['priority'], row['source'])),
            'aliases': aliases, 'fields': field_aliases, 'dispatch': sorted(dispatch),
            'unresolved': dict(sorted(unresolved.items()))}
    (args.out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'objects': len(rows), 'aliases': len(aliases), 'fields': len(field_aliases),
                      'unresolvedBeforePlatform': len(unresolved)}))


if __name__ == '__main__': main()

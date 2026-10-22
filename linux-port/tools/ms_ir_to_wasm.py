#!/usr/bin/env python3
"""Experimental source-IR bridge: preserve MS record layouts, target wasm32.

This produces relocatable objects, not a playable game. It deliberately leaves
runtime imports unresolved so platform work cannot be mistaken for a working port.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys
from build_wasm_varargs import build as build_varargs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
import ms_eh_to_dwarf
import retarget_ir

NEEDS_PORT = {
    'src/seer/callasm.c': 'x86 dynamic calls need typed Wasm adapters',
    'src/lanes/codex/import_veneers.cpp': 'x86 naked import jumps need typed wrappers',
    'src/lanes/codex/vorbis_file.c': 'x87 rounding-control assembly needs a portable implementation',
    'src/lanes/codex/vorbis_lsp.c': 'x87 float conversion needs a portable implementation',
}


def convert(source):
    text, symbols = retarget_ir.convert(ms_eh_to_dwarf.convert(source))
    text = re.sub(r'^target datalayout = .*$',
                  'target datalayout = "e-m:e-p:32:32-i64:64-n32:64-S128"', text, flags=re.M)
    text = re.sub(r'^target triple = .*$',
                  'target triple = "wasm32-unknown-unknown"', text, flags=re.M)
    text = re.sub(r'\b(?:x86_stdcallcc|x86_thiscallcc|x86_fastcallcc|dllimport|dllexport)\s+', '', text)
    text = re.sub(r'"(?:target-cpu|target-features|tune-cpu)"="[^"]*"', '', text)
    # x86 inalloca passes the address of a caller-owned argument frame. Wasm
    # needs an ordinary pointer parameter; the MS field offsets remain in IR.
    text = re.sub(r'\binalloca\([^)]*\)\s*', '', text)
    text = re.sub(r'\balloca inalloca\b', 'alloca', text)
    return text, symbols


def compile_ir(source, output, compiler, varargs_lowerer, sjlj=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    packed = output.with_suffix('.packed.ms.ll')
    result = subprocess.run([str(varargs_lowerer), str(source), str(packed)],
                            capture_output=True, text=True)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-4000:])
    text, symbols = convert(packed.read_text())
    ir = output.with_suffix('.ll')
    ir.write_text(text)
    ir.with_suffix('.symbols.json').write_text(json.dumps(symbols, indent=2) + '\n')
    command = [compiler, '--target=wasm32-unknown-unknown', '-mexception-handling',
               '-Wno-override-module', '-O2', '-c', str(ir), '-o', str(output)]
    if sjlj:
        command += ['-mllvm', '-wasm-enable-sjlj', '-matomics', '-mbulk-memory']
    result = subprocess.run(command, capture_output=True, text=True)
    output.with_suffix('.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-4000:])
    if output.read_bytes()[:8] != b'\0asm\x01\0\0\0':
        raise RuntimeError('Compiler did not produce a WebAssembly object')
    return symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ir', type=Path, default=ROOT / 'build/web/ms-ir')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/web/objects')
    parser.add_argument('--compiler', default='clang++')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--game', action='store_true', help='Portable codec code and Wasm setjmp/longjmp')
    parser.add_argument('--varargs-lowerer', type=Path,
                        help='Native wasm-varargs helper; built with LLVM 18 if omitted')
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 64:
        parser.error('--jobs must be between 1 and 64')
    report = json.loads((args.ir / 'report.json').read_text())
    lowerer = (args.varargs_lowerer.resolve() if args.varargs_lowerer
               else build_varargs(args.out / 'wasm-varargs'))

    def one(row):
        result = {'source': row['source']}
        if row['status'] != 'compiled':
            return dict(result, status='frontend-error', errors=row.get('errors', []))
        if row['source'] in NEEDS_PORT and not (args.game and row['source'] in
                ('src/lanes/codex/vorbis_file.c', 'src/lanes/codex/vorbis_lsp.c')):
            return dict(result, status='needs-port', reason=NEEDS_PORT[row['source']])
        output = args.out / (row['source'].replace('/', '__') + '.o')
        source = args.ir / (row['source'].replace('/', '__') + '.ll')
        try:
            compile_ir(source, output, args.compiler, lowerer, sjlj=args.game)
            return dict(result, status='compiled', object=str(output))
        except (OSError, RuntimeError, ValueError) as exc:
            return dict(result, status='backend-error', error=str(exc))

    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(one, report['rows']))
    summary = {name: sum(row['status'] == name for row in rows)
               for name in ('compiled', 'needs-port', 'frontend-error', 'backend-error')}
    (args.out / 'report.json').write_text(json.dumps({
        'target': 'wasm32-unknown-unknown', 'playable': False,
        'varargsABI': 'ms-x86-packed-v1',
        'summary': summary, 'rows': rows,
    }, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary))
    return int(any(summary[name] for name in ('frontend-error', 'backend-error')))


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compile source to Microsoft-layout LLVM IR with open Win32/portable headers.

VC6 is not a normal build input. --vc98 is an explicit, optional historical
comparison mode; it is never inferred from the user's environment.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from source_leaf import relocate

ROOT = Path(__file__).resolve().parents[1]


def adapt_sdk_header(path, sdk, out):
    """Correct legacy C++ spelling only, in private generated copies of headers."""
    relative = path.relative_to(sdk)
    name = path.name.upper()
    selected = {'UTILITY', 'STREAMBUF', 'IOS', 'OSTREAM', 'ISTREAM', 'FSTREAM', 'XLOCALE',
                'VECTOR', 'DEQUE', 'ITERATOR', 'ATLBASE.H', 'ATLWIN.H', 'OCIDL.H', 'ERRNO.H', 'STDARG.H'}
    if name not in selected:
        return path
    text = path.read_text(encoding='latin1')
    old = text
    if name == 'STDARG.H':
        # VC6 takes &last_parameter and assumes it is the incoming stack slot.
        # Clang can spill that formal into a different alloca, particularly with
        # stack realignment. LLVM va_start must recover the real argument area.
        # Keep the legacy va_arg lvalue macro: SeeR takes &(va_arg(ap,int)), and
        # its 4-byte slot rounding is exactly the MS x86 argument ABI.
        text=re.sub(r'^#define va_start\(ap,v\).*$','\u0023define va_start(ap,v) __builtin_va_start(ap,v)',
                    text,flags=re.MULTILINE)
        text=re.sub(r'^#define va_end\(ap\).*$','\u0023define va_end(ap) __builtin_va_end(ap)',
                    text,flags=re.MULTILINE)
    if name in {'UTILITY', 'STREAMBUF', 'IOS', 'OSTREAM', 'ISTREAM', 'FSTREAM'}:
        # These defaults already appear on forward declarations in IOSFWD.
        text = text.replace('class _Tr = char_traits<_E>', 'class _Tr')
    if name == 'XLOCALE':
        text = text.replace('class _CRTIMP codecvt<wchar_t, char, mbstate_t>',
                            'template<> class _CRTIMP codecvt<wchar_t, char, mbstate_t>')
        text = text.replace('class _CRTIMP ctype<char>', 'template<> class _CRTIMP ctype<char>')
    if name == 'VECTOR':
        text = text.replace('class vector<_Bool, _Bool_allocator>', 'template<> class vector<_Bool, _Bool_allocator>')
        # In a nested derived iterator, a bare iterator can resolve to the base
        # std::iterator instead of this enclosing container's declared iterator.
        text = text.replace('const_iterator(const iterator& _X)', 'const_iterator(const vector<_Bool, _Bool_allocator>::iterator& _X)')
    if name in {'OSTREAM', 'ISTREAM'}:
        text = text.replace('flags() & unitbuf', 'flags() & ios_base::unitbuf')
        text = text.replace('flags() & skipws', 'flags() & ios_base::skipws')
    if name == 'DEQUE':
        text = text.replace('class iterator : public const_iterator {\n\tpublic:',
                            'class iterator : public const_iterator {\n\tpublic:\n'
                            '\t\tusing const_iterator::_First; using const_iterator::_Last;\n'
                            '\t\tusing const_iterator::_Next; using const_iterator::_Map;\n'
                            '\t\tusing const_iterator::_Add;')
    if name == 'ATLWIN.H':
        text = text.replace('for(int i = 0; i < m_aChainEntry.GetSize(); i++)',
                            'int i; for(i = 0; i < m_aChainEntry.GetSize(); i++)')
        seen = set()
        def defaults(match):
            parameters = match.group(2)
            if match.group(4) in seen:
                parameters = re.sub(r'\s*=\s*[^,>]+', '', parameters)
            seen.add(match.group(4))
            return match.group(1)+parameters+match.group(3)+match.group(4)
        text = re.sub(r'(template\s*<)([^>]+)(>\s*class\s+(?:ATL_NO_VTABLE\s+)?)(\w+)', defaults, text)
    if name == 'FSTREAM':
        text = re.sub(r'(?<!::)(?<!->)(?<!\.)\b(in|out|trunc|app|ate|binary)\b', r'ios_base::\1', text)
    if name == 'ITERATOR':
        text = text.replace('_C::iterator(_I)', 'typename _C::iterator(_I)')
    if name == 'ERRNO.H':
        text = text.replace('_CRTIMP extern int errno;',
                            '_CRTIMP extern int * __cdecl _errno(void);\n#define errno (*_errno())')
    if name == 'ATLBASE.H':
        start = text.index('class CComQIPtr<IUnknown, &IID_IUnknown>') if 'class CComQIPtr<IUnknown, &IID_IUnknown>' in text else -1
        if start == -1:
            match = re.search(r'class\s+CComQIPtr<IUnknown,\s*&IID_IUnknown>', text)
            start = match.start() if match else -1
        if start != -1:
            end = text.index('\n};', start)+3
            text = text[:start]+re.sub(r'\bT\b', 'IUnknown', text[start:end])+text[end:]
    if name == 'OCIDL.H':
        text = text.replace('typedef __RPC_FAR *LPFONTEVENTS;', 'typedef IFontEventsDisp __RPC_FAR *LPFONTEVENTS;')
    if text == old:
        return path
    generated = out/'sdk-adapted'/relative
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(text, encoding='latin1')
    return generated


def sdk_overlay(sdk, out):
    roots = []
    for name in ('Include', 'ATL/Include'):
        folder = sdk/name
        contents = []
        if folder.is_dir():
            for path in folder.rglob('*'):
                if path.is_file():
                    adapted = adapt_sdk_header(path, sdk, out)
                    contents.append({'type': 'file', 'name': str(path.relative_to(folder)), 'external-contents': str(adapted)})
            roots.append({'type': 'directory', 'name': str(folder), 'contents': contents})
    overlay = out/'sdk-overlay.json'
    overlay.write_text(json.dumps({'version': 0, 'case-sensitive': 'false', 'roots': roots}, indent=1))
    return overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vc98', type=Path, help='Optional legacy-header comparison build; normal builds use portable headers')
    parser.add_argument('--compiler', default='clang++-18')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--filter', default='')
    parser.add_argument('--with-runtime', action='store_true')
    parser.add_argument('--wasm', action='store_true', help='Use portable Wasm setjmp and codec arithmetic')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--extra-source', action='append', default=[])
    parser.add_argument('--out', type=Path)
    parser.add_argument('--win32-headers', type=Path, default=Path('/usr/i686-w64-mingw32/include'))
    parser.add_argument('--resource-dir', type=Path, help='Clang resource directory (for split toolchain outputs)')
    parser.add_argument('--portable', type=Path, help='Override the project-owned portable header directory')
    args = parser.parse_args()
    args.win32_headers = args.win32_headers.resolve()
    if args.portable:
        args.portable = args.portable.resolve()
    if args.resource_dir:
        args.resource_dir = args.resource_dir.resolve()
    sdk = args.vc98.resolve() if args.vc98 else None
    if sdk and not (sdk/'Include').is_dir():
        parser.error('--vc98 must point to an installed VC98 directory')
    out = (args.out or Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build'))/('ms-runtime-ir' if args.runtime_only else 'ms-ir')).resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.compiler)
    if not compiler:
        parser.error('Compiler not found: '+args.compiler)
    overlay = sdk_overlay(sdk, out) if sdk else None
    configuration = json.loads((ROOT/'config/source-build.json').read_text())
    recipes = configuration['recipes']
    if args.runtime_only:
        recipes = []
    if args.with_runtime or args.runtime_only:
        recipes += [{'source': 'src/linux_runtime/vc6_cpp_runtime.cpp', 'cwd': '.', 'includes': [], 'flags': []}]
    recipes += [{'source': source, 'cwd': '.', 'includes': [], 'flags': []} for source in args.extra_source]
    recipes = [row for row in recipes if args.filter in row['source']]
    base = [compiler, '-target', 'i386-pc-windows-msvc', '-fms-extensions', '-fms-compatibility',
            '-fms-compatibility-version=12.0', '-fdeclspec', '-DTITBIT_SOURCE_LINK', '-DTITBIT_WIDESCREEN_HOOKS',
            '-O2', '-fno-strict-aliasing', '-fno-omit-frame-pointer', '-fdelayed-template-parsing',
            '-ffunction-sections', '-fdata-sections', '-ferror-limit=16',
            '-Wno-ignored-attributes', '-Wno-pragma-pack', '-Wno-microsoft-cast']
    portable = args.portable or (ROOT/'portable' if (ROOT/'portable').is_dir() else ROOT.parent/'portable')
    # Preserve the base branch's path-independent Linux builds while allowing
    # the browser frontend to override its portable headers and target macros.
    base += ['-ffile-prefix-map='+str(ROOT)+'=linux-port',
             '-ffile-prefix-map='+str(portable.resolve())+'=portable']
    if args.wasm:
        base += ['-DTITBIT_WASM_SOURCE']
    if sdk:
        base += ['-ivfsoverlay', str(overlay)]
    else:
        resource = subprocess.check_output([compiler, '-print-resource-dir'], text=True).strip()
        if args.resource_dir:
            resource = str(args.resource_dir)
        base += ['-nostdinc', '-DTITBIT_PORTABLE_HEADERS', '-fgnuc-version=4.2.1',
                 '-D__MINGW32__', '-D__i386__', '-D_X86_',
                 '-I', str(portable/'include/win32'), '-I', str(portable/'include/cxx'),
                 '-I', str(portable/'include/crt'), '-isystem', resource+'/include',
                 '-isystem', str(args.win32_headers)]
    start = time.monotonic()

    def compile_one(row):
        source = ROOT/row['source']
        key = row['source'].replace('/', '__')
        result = {'source': row['source']}
        actual = source
        if source.suffix.lower() == '.asm':
            if source.name != '00498de0-dinput_thunk.asm':
                return dict(result, status='blocked', category='masm-source')
            actual = out/'generated/dinput_thunk.cpp'
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_text('''// Source equivalent of the original import jump thunk.
typedef long (__stdcall *DirectInputCreateFn)(void *, unsigned, void **, void *);
extern "C" DirectInputCreateFn input_import __asm__("__imp__DirectInputCreateA@16");
extern "C" long __stdcall DirectInputCreateA(void *instance, unsigned version, void **output, void *outer) {
 return input_import(instance, version, output, outer);
}
''')
            result['adaptation'] = 'MASM import jump translated to typed tail-call source'
        elif row.get('relocatableLeaf') or row['source'] == 'src/native/game_audio.cpp':
            text = source.read_text()
            if row.get('relocatableLeaf'):
                text, references = relocate(text, configuration['imageMetadata']['dataRanges'])
                result['dataReferences'] = references
            else:
                text = text.replace('ActiveSoundEntry* active_sounds;\nint active_sound_count;',
                                    'extern ActiveSoundEntry* active_sounds;\nextern int active_sound_count;')
            actual = out/'generated'/key
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_text(text)
        command = list(base)
        command += ['-x', 'c', '-std=gnu89'] if source.suffix.lower() == '.c' else ['-std=c++98']
        for flag in row.get('flags', []):
            if flag.startswith('/D') and flag != '/Dfor=if (0) ; else for':
                command.append('-D'+flag[2:])
            elif flag == '/Zp4':
                command.append('-fpack-struct=4')
            elif flag == '/Od':
                command.append('-O0')
        folders = [source.parent, ROOT/'src/lanes/include']+[ROOT/p for p in row.get('includes', [])]
        if source.name == 'dom_parser.cpp':
            folders += [ROOT/'src/lanes/engine41/cpxml43/xmlincl', ROOT/'src/lanes/engine41/cpxml43/xmlincl/SAX']
        if sdk:
            folders += [sdk/'Include', sdk/'ATL/Include']
        for folder in folders:
            command += ['-I', str(folder)]
        ir = out/(key+'.ll')
        temporary_ir = ir.with_suffix('.new.ll')
        command += ['-S', '-emit-llvm', os.path.relpath(actual, ROOT/row.get('cwd', '.')), '-o', str(temporary_ir)]
        result['command'] = command
        try:
            run = subprocess.run(command, cwd=ROOT/row.get('cwd', '.'), capture_output=True, text=True, errors='replace', timeout=120)
            log = run.stdout+run.stderr
            (out/(key+'.log')).write_text(log)
            errors = [line.strip() for line in log.splitlines() if ': error:' in line or ': fatal error:' in line]
            result.update(exitCode=run.returncode, errors=errors)
            if run.returncode == 0:
                temporary_ir.replace(ir)
                result.update(status='compiled', ir=str(ir.resolve()), sha256=hashlib.sha256(ir.read_bytes()).hexdigest())
            else:
                temporary_ir.unlink(missing_ok=True)
                match = re.search(r"fatal error: '([^']+)' file not found", '\n'.join(errors))
                category = 'missing-header:'+match.group(1) if match else 'compiler-error'
                result.update(status='blocked', category=category)
        except subprocess.TimeoutExpired:
            temporary_ir.unlink(missing_ok=True)
            result.update(status='blocked', category='timeout')
        return result

    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(compile_one, row) for row in recipes]):
            row = future.result()
            rows.append(row)
            print(f"[{len(rows)}/{len(recipes)}] {row['status']}: {row['source']}", flush=True)
    error_counts = Counter()
    for row in rows:
        for error in row.get('errors', []):
            error_counts[re.sub(r'^.*?:\d+:\d+: (?:fatal )?error: ', '', error)] += 1
    report = {'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
              'target': 'i386-pc-windows-msvc / LLVM IR', 'sdk': str(sdk) if sdk else 'project-owned portable headers', 'sourceLink': True,
              'compat': False, 'translationUnits': len(rows), 'seconds': round(time.monotonic()-start, 2),
              'summary': dict(Counter(row.get('category', 'compiled') for row in rows)),
              'errorHistogram': dict(error_counts.most_common()), 'rows': sorted(rows, key=lambda row: row['source'])}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('rows', 'errorHistogram')}, indent=2))
    return int(any(row['status'] != 'compiled' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())

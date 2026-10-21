#!/usr/bin/env python3
"""Build and execute portable string/container/EH/stream tests as native ELF32.

Run build_platform.py first. No game assets or executable are needed.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build')).resolve()


def encode(name):
    return 'titbit_ms_'+name.encode().hex() if any(char in name for char in '@?\\') else name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vc98', type=Path, help='Optional legacy-header comparison build')
    parser.add_argument('--native', type=Path, default=BUILD/'native')
    parser.add_argument('--out', type=Path, default=BUILD/'cpp-runtime-test')
    args = parser.parse_args()
    out = args.out.resolve()
    native = args.native.resolve()
    names = ('crt_linux.o', 'crt_new.o', 'ms_exception.o', 'sdl_platform.o')
    for name in names:
        if not (native/name).is_file():
            parser.error('Missing native boundary object '+name+'; run tools/build_platform.py first')
    out.mkdir(parents=True, exist_ok=True)
    portable = ROOT/'portable' if (ROOT/'portable').is_dir() else ROOT.parent/'portable'
    extras = [] if args.vc98 else ['--extra-source', os.path.relpath(portable/'src/container_smoke.cpp', ROOT),
                                  '--extra-source', os.path.relpath(portable/'src/win32_abi.cpp', ROOT)]
    subprocess.run([sys.executable, str(ROOT/'tools/compile_ms_ir.py'),
                    '--runtime-only', '--extra-source', 'src/linux_runtime/tests/vc6_cpp_smoke.cpp',
                    '--out', str(out/'ir'), '--jobs', '1']+
                    (['--vc98', str(args.vc98.resolve())] if args.vc98 else extras), cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT/'tools/ms_ir_to_elf.py'), '--ir', str(out/'ir'),
                    '--out', str(out/'elf'), '--jobs', '1'], cwd=ROOT, check=True)
    aliases = {
        encode('??2@YAPAXI@Z'): 'titbit_operator_new', encode('??3@YAXPAX@Z'): 'titbit_operator_delete',
        encode('??_U@YAPAXI@Z'): 'titbit_operator_new', encode('??_V@YAXPAX@Z'): 'titbit_operator_delete',
        encode('??_7type_info@@6B@'): 'titbit_type_info_vtable', '_errno': 'tb_crt_errno', '_iob': 'tb_crt_iob',
        '_pctype': 'tb_crt_pctype', '__mb_cur_max': 'tb_crt_mb_cur_max', '_filbuf': 'tb_crt_filbuf',
        '_flsbuf': 'tb_crt_flsbuf', '_fileno': 'tb_crt_fileno', '_filelength': 'tb_crt_filelength'}
    functions = ('fopen', 'fclose', 'fread', 'fwrite', 'fseek', 'ftell', 'fflush', 'fgetc', 'fputc',
                 'fgets', 'fputs', 'ungetc', 'setvbuf', 'feof', 'ferror', 'fgetpos', 'fsetpos')
    aliases.update({name: 'tb_crt_'+name for name in functions})
    objects = []
    rows = json.loads((out/'elf/report.json').read_text())['rows']
    for row in rows:
        if row['status'] != 'compiled':
            raise RuntimeError('ELF generation failed: '+row['source'])
        target = out/(Path(row['object']).name+'.adapted.o')
        shutil.copy2(row['object'], target)
        # GNU objcopy cannot merge two source names into one destination in a
        # single operation; handle independent import aliases in separate calls.
        for source, replacement in aliases.items():
            if source in row['undefined']:
                subprocess.run(['objcopy', '--redefine-sym', source+'='+replacement, str(target)], check=True)
        objects.append(str(target))
    subprocess.run(['clang++-18', '-m32', '-O2', '-c', str(ROOT/'src/linux_runtime/vc6_native_helpers.cpp'),
                    '-o', str(out/'native_helpers.o')], check=True)
    subprocess.run(['clang-18', '-m32', *([] if args.vc98 else ['-DTITBIT_PORTABLE_SMOKE']),
                    '-c', str(ROOT/'src/linux_runtime/tests/smoke_main.c'),
                    '-o', str(out/'main.o')], check=True)
    objects += [str(out/'native_helpers.o'), str(out/'main.o')]+[str(native/name) for name in names]
    built = subprocess.run(['clang++-18', '-m32', '-no-pie', '-Wl,--gc-sections', *objects,
                            '-L/usr/lib/i386-linux-gnu', '-lSDL2', '-lGL', '-lpthread', '-o', str(out/'smoke')],
                           capture_output=True, text=True)
    (out/'link.log').write_text(built.stdout+built.stderr)
    if built.returncode:
        raise RuntimeError(built.stdout+built.stderr)
    # The shared smoke fixture writes relative build/* files. Keep those writes
    # inside this test output even for a clean checkout or --build-dir build.
    work = out/'work'
    (work/'build').mkdir(parents=True, exist_ok=True)
    run = subprocess.run([str(out/'smoke')], cwd=work, capture_output=True, text=True, timeout=20)
    result = {'ok': run.returncode == 0, 'exitCode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr,
              'coverage': ['legacy copy-on-write strings' if args.vc98 else 'portable string/container ownership and fixed layouts', 'string replacement', 'typed exceptions',
                           'exception copying', 'unwind observer', 'C locale facets',
                           'file streams', 'stream seeking', 'source FILE32/getc interface',
                           'fread/feof', 'descriptor/file length', '64-bit fpos round trip']}
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())

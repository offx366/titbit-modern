#!/usr/bin/env python3
"""Build and execute the experimental Wasm compiler/SeeR probes (not the game)."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from ms_ir_to_wasm import compile_ir
from build_wasm_varargs import build as build_varargs

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='clang++')
    parser.add_argument('--linker', default='wasm-ld')
    parser.add_argument('--node', default='node')
    parser.add_argument('--resource-dir', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/web/probe')
    parser.add_argument('--varargs-lowerer', type=Path)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.compiler)
    if not compiler:
        parser.error('Compiler not found: ' + args.compiler)
    resource = args.resource_dir or Path(subprocess.check_output(
        [compiler, '-print-resource-dir'], text=True).strip())
    lowerer = (args.varargs_lowerer.resolve() if args.varargs_lowerer
               else build_varargs(args.out / 'wasm-varargs'))
    sources = [
        'probes/msabi_probe.cpp',
        'probes/msabi_inalloca.cpp',
        'src/native/vector_geometry.cpp',
        'src/seer/Vcpudeco.c',
        'web/abi_probe.cpp',
        'web/seer_probe.c',
        'web/varargs_probe.cpp',
        'web/varargs_caller.cpp',
    ]
    save_sources = ['src/lanes/engine41/quest_state.cpp', 'web/save_probe.cpp']
    objects = {}
    for source in sources + save_sources:
        src = ROOT / source
        output = args.out / (source.replace('/', '__') + '.o')
        ir = output.with_suffix('.ms.ll')
        command = [compiler, '-target', 'i386-pc-windows-msvc', '-fms-extensions',
                   '-fms-compatibility-version=12.0', '-fno-strict-aliasing',
                   '-fno-builtin', '-DTITBIT_WASM_PROBE', '-O2', '-nostdinc',
                   '-I', str(PROJECT / 'portable/include/crt'),
                   '-isystem', str(resource / 'include')]
        command += ['-x', 'c', '-std=gnu89'] if src.suffix == '.c' else ['-std=c++11']
        if source == 'probes/msabi_probe.cpp':
            # This probe tests virtual dispatch, not Microsoft's RTTI runtime.
            command += ['-fno-rtti']
        command += ['-S', '-emit-llvm', str(src), '-o', str(ir)]
        subprocess.run(command, check=True)
        compile_ir(ir, output, compiler, lowerer)
        objects[source] = output
    exports = ['probe_run', 'probe_inalloca', 'probe_geometry', 'probe_seer', 'probe_varargs']
    subprocess.run([args.linker, '--no-entry', '--fatal-warnings', '-z', 'stack-size=1048576',
                    *['--export=' + name for name in exports],
                    *[str(objects[source]) for source in sources],
                    '-o', str(args.out / 'titbit-probe.wasm')], check=True)
    save_exports = ['__wasm_call_ctors', 'save_state_address', 'save_state_size',
                    'save_state_reset', 'save_write', 'save_read']
    subprocess.run([args.linker, '--no-entry', '--fatal-warnings', '--export-memory',
                    '--allow-undefined-file=' + str(ROOT / 'web/save-imports.txt'),
                    *['--export=' + name for name in save_exports],
                    *[str(objects[source]) for source in save_sources],
                    '-o', str(args.out / 'titbit-save-probe.wasm')], check=True)
    for name in ('index.html', 'probe.js', 'check.mjs', 'saves.js', 'save-probe.html',
                 'save-probe.js', 'save-checks.html', 'save-checks.js', 'check-save-wasm.mjs'):
        shutil.copyfile(ROOT / 'web' / name, args.out / name)
    subprocess.run([args.node, str(args.out / 'check.mjs'), str(args.out / 'titbit-probe.wasm')], check=True)
    subprocess.run([args.node, str(args.out / 'check-save-wasm.mjs'),
                    str(args.out / 'titbit-save-probe.wasm')], check=True)
    (args.out / 'build.json').write_text(json.dumps({
        'target': 'wasm32-unknown-unknown', 'playable': False,
        'varargsABI': 'ms-x86-packed-v1',
        'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
        'sources': sources, 'exports': exports,
        'saveProbe': {'sources': save_sources, 'exports': save_exports,
                      'formatBytes': 408, 'playable': False},
    }, indent=2) + '\n')
    print('Built and verified:', args.out / 'titbit-probe.wasm')


if __name__ == '__main__':
    main()

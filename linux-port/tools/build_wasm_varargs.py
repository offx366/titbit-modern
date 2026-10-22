#!/usr/bin/env python3
"""Build the native LLVM 18 helper for the private packed-varargs Wasm ABI."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(output, compiler=None, llvm_config=None, source='wasm_varargs.cpp'):
    compiler = compiler or os.environ.get('TITBIT_NATIVE_CXX', 'c++')
    llvm_config = llvm_config or os.environ.get('TITBIT_LLVM_CONFIG', 'llvm-config')
    version = subprocess.check_output([llvm_config, '--version'], text=True).strip()
    if not version.startswith('18.'):
        raise ValueError('wasm-varargs requires LLVM 18, found ' + version)
    flags = shlex.split(subprocess.check_output([
        llvm_config, '--cxxflags', '--ldflags', '--libs', 'core', 'irreader',
        '--system-libs'], text=True))
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([compiler, str(ROOT / 'tools' / source), '-O2',
                    *flags, '-o', str(output)], check=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler')
    parser.add_argument('--llvm-config')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/web/wasm-varargs')
    args = parser.parse_args()
    print(build(args.out, args.compiler, args.llvm_config))

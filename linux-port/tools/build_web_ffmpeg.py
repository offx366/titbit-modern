#!/usr/bin/env python3
"""Build the pinned AVI decoder for WebAssembly (no original game assets)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

VERSION = '6.1.1'
SHA256 = '8684f4b00f94b85461884c3719382f1261f0d9eb3d59640a1f4ac0873616f968'


def build(prefix, environment, jobs=8):
    prefix = Path(prefix).resolve()
    libraries = [prefix/'lib'/f'lib{name}.a' for name in ('avformat', 'avcodec', 'swscale', 'avutil')]
    if all(p.exists() for p in libraries):
        return libraries
    prefix.mkdir(parents=True, exist_ok=True)
    archive = prefix/f'ffmpeg-{VERSION}.tar.xz'
    if not archive.exists():
        partial = archive.with_suffix('.part')
        with urllib.request.urlopen(f'https://ffmpeg.org/releases/ffmpeg-{VERSION}.tar.xz', timeout=60) as response:
            with partial.open('wb') as target:
                shutil.copyfileobj(response, target)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('FFmpeg source checksum mismatch')
        partial.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('FFmpeg source checksum mismatch')
    source = prefix/'src'
    if not source.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(prefix, filter='data')
        (prefix/f'ffmpeg-{VERSION}').rename(source)
    emcc = shutil.which('emcc', path=environment['PATH'])
    emar = shutil.which('emar', path=environment['PATH'])
    emranlib = shutil.which('emranlib', path=environment['PATH'])
    emnm = shutil.which('llvm-nm', path=environment['PATH'])
    configure = [source/'configure', f'--prefix={prefix}', '--enable-cross-compile',
        '--target-os=none', '--arch=wasm32', f'--cc={emcc}', f'--ar={emar}',
        f'--ranlib={emranlib}', f'--nm={emnm}', '--extra-cflags=-O2 -pthread -fwasm-exceptions',
        '--extra-ldflags=-pthread -fwasm-exceptions', '--disable-everything',
        '--disable-programs', '--disable-doc', '--disable-network', '--disable-autodetect',
        '--disable-asm', '--disable-inline-asm', '--disable-runtime-cpudetect',
        '--disable-pthreads', '--disable-w32threads', '--disable-os2threads',
        '--disable-avdevice', '--disable-avfilter', '--disable-postproc', '--disable-swresample',
        '--enable-static', '--disable-shared', '--enable-small',
        '--enable-demuxer=avi', '--enable-decoder=msmpeg4v2,msvideo1', '--enable-protocol=file',
        '--enable-swscale']
    with (prefix/'build.log').open('w') as log:
        for command in (configure, ['make', f'-j{jobs}'], ['make', 'install']):
            subprocess.run(list(map(str,command)), cwd=source, env=environment,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
    return libraries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--environment', type=Path)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    environment = dict(os.environ)
    if args.environment:
        environment.update(json.loads(args.environment.read_text()))
    print('\n'.join(map(str,build(args.prefix,environment,args.jobs))))

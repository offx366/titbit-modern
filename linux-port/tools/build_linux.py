#!/usr/bin/env python3
"""Build the reconstructed source as native ELF32 using the MSVC ABI bridge."""
import argparse
try:
    import fcntl
except ImportError:
    fcntl = None
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build')).resolve()
EXTRA_SOURCES = ('platform/game_entry_ms.cpp', 'platform/game_initializers_ms.cpp', 'src/linux_runtime/missing_members.cpp',
                 'src/linux_runtime/lane_string_members.cpp')


def preflight(vc98, environment):
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64', 'i386', 'i686'):
        raise RuntimeError('The native game target requires x86 Linux; run this command inside WSL Ubuntu.')
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required.')
    if vc98:
        for directory in ('Include', 'ATL/Include'):
            if not (vc98/directory).is_dir():
                raise RuntimeError('VC98 header directory not found: '+str(vc98/directory))
    elif not Path('/usr/i686-w64-mingw32/include/windows.h').is_file():
        raise RuntimeError('Open Win32 headers missing: install mingw-w64-i686-dev (no VC6 SDK is needed).')
    versions = {}
    for tool in ('clang-18', 'clang++-18', 'opt-18', 'llvm-ar-18', 'nm', 'objcopy', 'pkg-config'):
        path = shutil.which(tool)
        if not path:
            raise RuntimeError('Required tool missing: '+tool+'; see docs/BUILD-LINUX.md')
        run = subprocess.run([path, '--version'], capture_output=True, text=True, env=environment)
        versions[tool] = (run.stdout or run.stderr).splitlines()[0]
    libraries = ('gl', 'glu') + (() if environment.get('TITBIT_SDL2') else ('sdl2',)) +         (() if environment.get('TITBIT_FFMPEG') else ('libavformat', 'libavcodec', 'libavutil', 'libswscale', 'libswresample'))
    subprocess.run(['pkg-config', '--exists', *libraries], env=environment, check=True)
    with tempfile.TemporaryDirectory(prefix='titbit-native-check-') as temporary:
        executable = Path(temporary)/'check'
        source = '#include <stdint.h>\nint main(void){return sizeof(void*)!=4;}\n'
        run = subprocess.run(['clang-18', '-m32', '-x', 'c', '-', '-o', str(executable)],
                             input=source, capture_output=True, text=True, env=environment)
        if run.returncode:
            raise RuntimeError('32-bit C compiler/runtime check failed:\n'+run.stderr)
        subprocess.run([str(executable)], check=True, env=environment)
    return versions


def write_report(path, report):
    temporary = path.with_suffix('.new.json')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vc98', type=Path,
                        help='Optional reference build with legacy VC98 headers; normal builds do not use VC6')
    parser.add_argument('--build-dir', type=Path, help='Isolated build output; leaves the existing build unchanged')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--ffmpeg', type=Path, default=os.environ.get('TITBIT_FFMPEG'),
                        help='Prefix of the minimal static FFmpeg from tools/build_ffmpeg_min.sh (fewer runtime libraries)')
    parser.add_argument('--minimal', action='store_true',
                        help='Build (once) and link the minimal static FFmpeg and SDL2: the game then needs only 32-bit glibc and GL')
    parser.add_argument('--sdl2', type=Path, default=os.environ.get('TITBIT_SDL2'),
                        help='Prefix of the static SDL2 from tools/build_sdl2_min.sh (X11/Wayland/audio loaded at run time)')
    parser.add_argument('--check', action='store_true', help='Check toolchain and ELF32 execution without rebuilding')
    parser.add_argument('--test-runtime', action='store_true', help='Also execute string/EH/locale/FILE32 checks')
    global BUILD
    args = parser.parse_args()
    if args.build_dir:
        BUILD = args.build_dir.resolve()
    os.environ['TITBIT_BUILD_DIR'] = str(BUILD)
    if args.jobs < 1 or args.jobs > 64:
        parser.error('--jobs must be between 1 and 64')
    vc98 = args.vc98.expanduser().resolve() if args.vc98 else None
    environment = dict(os.environ)
    environment.pop('TITBIT_VC6', None)
    if args.minimal:
        # outside the repository: autotools (SDL2) cannot build in paths with spaces
        cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'titbit'
        for script, prefix, attr in (('build_ffmpeg_min.sh', cache/'ffmpeg-min', 'ffmpeg'),
                                     ('build_sdl2_min.sh', cache/'sdl2-min', 'sdl2')):
            marker = prefix/'lib'/('libavformat.a' if attr == 'ffmpeg' else 'libSDL2.a')
            recipe = hashlib.sha256((ROOT/'tools'/script).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            stamp = prefix/'recipe.sha256'
            if marker.exists() and not args.check and (not stamp.is_file() or stamp.read_text().strip() != recipe):
                # built by an older recipe: keep the verified download, rebuild the rest
                for old in prefix.iterdir():
                    if not old.name.endswith(('.tar.gz', '.tar.xz')):
                        shutil.rmtree(old) if old.is_dir() else old.unlink()
            if not marker.exists() and not args.check:  # --check only validates the toolchain
                print('Building '+prefix.name+' (one time)...', flush=True)
                subprocess.run(['sh', str(ROOT/'tools'/script), str(prefix)], check=True)
                stamp.write_text(recipe+'\n')
            setattr(args, attr, prefix)
    if args.ffmpeg:
        environment['TITBIT_FFMPEG'] = str(args.ffmpeg.expanduser().resolve())
    if args.sdl2:
        environment['TITBIT_SDL2'] = str(args.sdl2.expanduser().resolve())
    pkgconfig = Path('/usr/lib/i386-linux-gnu/pkgconfig')
    if pkgconfig.is_dir() and 'PKG_CONFIG_LIBDIR' not in environment:
        environment['PKG_CONFIG_LIBDIR'] = str(pkgconfig)+':/usr/share/pkgconfig'
    try:
        versions = preflight(vc98, environment)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc)+'\n')
    if args.check:
        print('Toolchain and native ELF32 execution: OK')
        print(json.dumps(versions, indent=2))
        return 0
    BUILD.mkdir(parents=True, exist_ok=True)
    lock = (BUILD/'.linux-build.lock').open('a+')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(1, 'Another build_linux.py process owns this build directory. Wait for it to finish.\n')
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())+'\n'); lock.flush()
    logs = BUILD/'logs'
    logs.mkdir(exist_ok=True)
    report_path = BUILD/'linux-build.json'
    report = {'version': 1, 'status': 'running', 'host': platform.platform(), 'python': sys.version.split()[0],
              'target': 'ELF32 / Intel 80386 / Microsoft object ABI', 'toolchain': versions,
              'sourceMetadataSHA256': hashlib.sha256((ROOT/'config/source-build.json').read_bytes()).hexdigest(),
              'steps': []}
    started = time.monotonic()

    def stage(name, command):
        print(name, flush=True)
        log = logs/(name.split()[0]+'.log')
        start = time.monotonic()
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        row = {'stage': name, 'command': command, 'exitCode': result.returncode,
               'seconds': round(time.monotonic()-start, 2), 'log': os.path.relpath(log, ROOT)}
        report['steps'].append(row)
        write_report(report_path, report)
        if result.returncode:
            raise RuntimeError(name+' failed; see '+str(log))

    try:
        frontend = [sys.executable, str(ROOT/'tools/compile_ms_ir.py'),
                    '--with-runtime', '--jobs', str(args.jobs)]
        if vc98:
            frontend += ['--vc98', str(vc98)]
        for source in EXTRA_SOURCES:
            frontend += ['--extra-source', source]
        stage('01 Source to Microsoft ABI LLVM IR', frontend)
        stage('02 LLVM IR to native ELF32 objects',
              [sys.executable, str(ROOT/'tools/ms_ir_to_elf.py'), '--jobs', str(args.jobs)])
        stage('03 Generate source resource strings',
              [sys.executable, str(ROOT/'platform/generate_resources.py'),
               str(ROOT/'src/lanes/codex/resources/titbit.rc'), str(ROOT/'platform/resource_strings.inc')])
        stage('04 Build native SDL OpenGL FFmpeg boundary', [sys.executable, str(ROOT/'tools/build_platform.py')])
        helper = BUILD/'ms-runtime-elf/objects/vc6_native_helpers.o'
        helper.parent.mkdir(parents=True, exist_ok=True)
        stage('05 Build GNU exception state helper',
              ['clang++-18', '-m32', '-std=c++17', '-O2', '-ffile-prefix-map='+str(ROOT)+'=linux-port',
               '-fno-omit-frame-pointer', '-mstackrealign',
               '-c', str(ROOT/'src/linux_runtime/vc6_native_helpers.cpp'), '-o', str(helper)])
        stage('06 Resolve source bindings and link', [sys.executable, str(ROOT/'tools/link_native.py'), '--link'])
        linked = json.loads((BUILD/'native/link-plan.json').read_text())
        if not linked.get('linked'):
            raise RuntimeError('Native link failed; see build/native/link.log')
        executable = BUILD/'titbit'
        with executable.open('rb') as stream:
            header = stream.read(20)
        if header[:7] != b'\x7fELF\x01\x01\x01' or int.from_bytes(header[18:20], 'little') != 3:
            raise RuntimeError('Link output is not a native little-endian ELF32 Intel 80386 executable.')
        if args.test_runtime:
            stage('07 Verify native CRT and C++ header ABI',
                  [sys.executable, str(ROOT/'tools/check_cpp_runtime.py')]+(['--vc98', str(vc98)] if vc98 else []))
        report.update(status='complete', seconds=round(time.monotonic()-started, 2),
                      output={'path': os.path.relpath(executable, ROOT),
                              'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()})
        print('Built: '+str(executable))
        print('Game assets and gameplay validation are separate; see docs/BUILD-LINUX.md.')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        report.update(status='failed', error=str(exc), seconds=round(time.monotonic()-started, 2))
        print(str(exc), file=sys.stderr)
    except KeyboardInterrupt:
        report.update(status='interrupted', seconds=round(time.monotonic()-started, 2))
        print('Build interrupted.', file=sys.stderr)
    finally:
        write_report(report_path, report)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

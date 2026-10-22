#!/usr/bin/env python3
"""Build the experimental full browser engine from recovered source modules."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from build_wasm_varargs import build as build_helper
from patch_web_lighting import build as build_lighting
from build_web_ffmpeg import build as build_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, help='Optional explicit toolchain environment JSON')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/web/game')
    parser.add_argument('--stages', default='frontend,objects,platform,rewrite,link')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    args.out = args.out.resolve(); args.out.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    if args.environment: environment.update(json.loads(args.environment.read_text()))
    compiler = environment.get('TITBIT_CLANG') or shutil.which('clang++', path=environment['PATH'])
    resource = environment.get('TITBIT_CLANG_RESOURCE_DIR') or subprocess.check_output(
        [compiler, '-print-resource-dir'], text=True).strip()
    native_cxx = environment.get('TITBIT_NATIVE_CXX', 'c++')
    llvm_config = environment.get('TITBIT_LLVM_CONFIG', 'llvm-config')
    llvm_bin = Path(subprocess.check_output([llvm_config, '--bindir'], text=True).strip())
    emcc = shutil.which('emcc', path=environment['PATH'])
    emxx = shutil.which('em++', path=environment['PATH'])
    if not emcc: parser.error('emcc is missing; enter nix develop .#web')
    cache = args.out / 'emscripten-cache'
    if not (cache / 'sysroot').exists():
        original_cache = Path(environment.get('EM_CACHE', Path(emcc).resolve().parents[1] / 'share/emscripten/cache'))
        shutil.copytree(original_cache, cache, dirs_exist_ok=True)
        for path in [cache, *cache.rglob('*')]:
            if not path.is_symlink(): path.chmod(path.stat().st_mode | 0o200)
    environment['EM_CACHE'] = str(cache)
    video_libraries = build_ffmpeg(args.out/'ffmpeg', environment, args.jobs)
    stages = args.stages.split(',')
    if any(stage not in ('frontend','objects','platform','rewrite','link') for stage in stages):
        parser.error('Unknown stage')
    logs = args.out / 'logs'; logs.mkdir(exist_ok=True)

    def run(name, command):
        print(name, flush=True)
        with (logs / (name + '.log')).open('w') as log:
            result = subprocess.run(list(map(str, command)), cwd=ROOT, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print((logs / (name + '.log')).read_text()[-7000:], file=sys.stderr)
            raise RuntimeError(name + ' failed')

    frontend, objects, native, linked = [args.out / name for name in ('frontend','objects','native','link')]
    lowerer = args.out / 'wasm-varargs'
    if 'objects' in stages:
        build_helper(lowerer, native_cxx, llvm_config)
    if 'frontend' in stages:
        headers = args.out / 'headers'
        shutil.copytree(PROJECT / 'portable', headers / 'portable', dirs_exist_ok=True)
        run('headers', ['patch','-p1','--directory',headers,'--input',PROJECT/'nix/engine/portable-headers.patch'])
        run('frontend', [sys.executable, ROOT/'tools/compile_ms_ir.py','--wasm',
            '--compiler',compiler,'--resource-dir',resource,'--win32-headers',environment['TITBIT_WIN32_HEADERS'],
            '--portable',headers/'portable','--out',frontend,'--with-runtime','--jobs',str(args.jobs),
            '--extra-source','platform/game_initializers_ms.cpp','--extra-source','web/game_entry.cpp',
            '--extra-source','src/linux_runtime/missing_members.cpp','--extra-source','src/linux_runtime/lane_string_members.cpp'])
    if 'objects' in stages:
        run('objects', [sys.executable,ROOT/'tools/ms_ir_to_wasm.py','--game','--ir',frontend,
            '--out',objects,'--compiler',compiler,'--varargs-lowerer',lowerer,'--jobs',str(args.jobs)])
    native_sources = [ROOT/'platform'/name for name in (
        'sdl_platform.c','win32_sdl.c','win32_kernel.c','win32_heap.c','win32_misc.c',
        'win32_mixer.c','win32_host.c','gl_stdcall.c','crt_linux.c','crt_new.cpp',
        'ms_exception.cpp','ms_rtti.cpp','game_input_native.cpp')]
    native_sources += [ROOT/'web/platform_browser.cpp', ROOT/'web/audio_browser.cpp', ROOT/'web/crt_browser.c', ROOT/'platform/avi_ffmpeg.c']
    native.mkdir(exist_ok=True)
    if 'platform' in stages:
        for source in native_sources:
            cpp = source.suffix=='.cpp' or source.name=='gl_stdcall.c'
            run('platform-' + source.stem, [emxx if cpp else emcc,
                *(['-x','c++'] if cpp else []),
                '-O1','-g','-pthread','-fwasm-exceptions','-D_FILE_OFFSET_BITS=64','-sUSE_SDL=2',
                '-I'+str(args.out/'ffmpeg/include'),
                '-Wno-ignored-attributes','-c',source,'-o',native/(source.stem+'.o')])
    if 'rewrite' in stages:
        run('plan', [sys.executable,ROOT/'tools/plan_web_link.py','--objects',objects,
            '--native',native,'--nm',llvm_bin/'llvm-nm','--out',linked])
        helper = args.out/'wasm-rewrite'
        build_helper(helper,native_cxx,llvm_config,'wasm_rewrite.cpp')
        run('rewrite', [helper,linked/'plan.json'])
        plan = json.loads((linked/'plan.json').read_text())
        def compile_one(row):
            name = row['source'].replace('/','__')
            # Use the final runtime's LLVM for setjmp lowering: its helper ABI
            # changes between LLVM releases, unlike the source IR boundary.
            sjlj = any(token in Path(row['out']).read_text() for token in ('@setjmp(', '@longjmp('))
            backend = [emcc,'-pthread','-fwasm-exceptions','-sSUPPORT_LONGJMP=wasm'] if sjlj else [
                compiler,'--target=wasm32-unknown-unknown','-mexception-handling','-matomics','-mbulk-memory']
            run('codegen-' + name, [*backend,'-O2',
                '-c',row['out'],'-o',Path(row['out']).with_suffix('.o')])
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            list(pool.map(compile_one,plan['rows']))
        run('dispatch', [emcc,'-pthread','-fwasm-exceptions',
            '-O2','-c',linked/'dispatch.ll','-o',linked/'dispatch.o'])
    if 'link' in stages:
        lighting = build_lighting(Path(emcc).resolve().parents[1]/'share/emscripten/src/lib/libglemu.js', args.out/'legacy-lighting.js')
        plan = json.loads((linked/'plan.json').read_text())
        direct, archive = [], []
        for row in plan['rows']:
            target = Path(row['out']).with_suffix('.o')
            (direct if row['source'].startswith(('platform/','src/linux_runtime/','web/')) else archive).append(target)
        library = linked/'game.a'; library.unlink(missing_ok=True)
        run('archive', [llvm_bin/'llvm-ar','rcs',library,*archive])
        run('link', [emxx,'-O1','-g','-pthread','-fwasm-exceptions','-sSUPPORT_LONGJMP=wasm',
            '--js-library',lighting,
            '-sUSE_SDL=2','-sLEGACY_GL_EMULATION=1','-sALLOW_MEMORY_GROWTH=1',
            '-sINITIAL_MEMORY=268435456','-sMAXIMUM_MEMORY=2147483648','-sSTACK_SIZE=8388608',
            # CString treats addresses below 64 KiB as Win32 resource IDs.
            '-sGLOBAL_BASE=65536',
            '-sPTHREAD_POOL_SIZE=4','-sMODULARIZE=1','-sEXPORT_NAME=createTitbit',
            '-sEXPORTED_FUNCTIONS=["_titbit_web_initialize","_titbit_web_frame","_titbit_web_check_script","_malloc","_free"]',
            '-sEXPORTED_RUNTIME_METHODS=["FS","ccall","cwrap","getExceptionMessage","HEAPU8"]',
            '-sFORCE_FILESYSTEM=1','-sEXIT_RUNTIME=0','-sASSERTIONS=2',
            *sorted(native.glob('*.o')),*direct,linked/'dispatch.o',library,*video_libraries,
            '-Wl,--error-limit=0','-o',args.out/'titbit.js'])
    for name in ('game.html', 'game.js', 'browser_start.scv', 'saves.js', 'assets.js', 'audio-worklet.js',
                 'bootstrap.js', 'isolation-worker.js', 'game-assets.json'):
        shutil.copy2(ROOT/'web'/name, args.out/name)
    print('Browser engine:', args.out)


if __name__ == '__main__': main()

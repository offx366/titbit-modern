#!/usr/bin/env python3
"""Build the native SDL/OpenGL/FFmpeg boundary as genuine ELF32 objects."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build'))/'native')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    packages=['sdl2','libavformat','libavcodec','libswscale','libswresample']
    prefix=os.environ.get('TITBIT_FFMPEG'); sdl=os.environ.get('TITBIT_SDL2')
    if sdl:      # static SDL2 (tools/build_sdl2_min.sh)
        packages.remove('sdl2')
    if prefix:   # minimal static FFmpeg (tools/build_ffmpeg_min.sh)
        packages=[p for p in packages if not p.startswith('lib')]
    pkg=subprocess.check_output(['pkg-config','--cflags',*packages],text=True) if packages else ''
    if sdl:
        pkg+=' -I'+str(Path(sdl)/'include/SDL2')+' -D_REENTRANT'
        pkg+=' -ffile-prefix-map='+str(Path(sdl).resolve())+'=sdl2-min'      # no per-user cache path in debug info
    if prefix:
        pkg+=' -I'+str(Path(prefix)/'include')
        pkg+=' -ffile-prefix-map='+str(Path(prefix).resolve())+'=ffmpeg-min'
    sources=['sdl_platform.c','win32_sdl.c','win32_kernel.c','win32_heap.c','win32_misc.c','win32_mixer.c','win32_host.c','gl_stdcall.c','avi_ffmpeg.c',
             'seer_call.S','ms_setjmp.S','main.c','ms_exception.cpp','crt_linux.c','crt_new.cpp','game_input_native.cpp']
    if (ROOT/'platform/ms_rtti.cpp').exists():sources.append('ms_rtti.cpp')
    for name in sources:
        command=['clang++-18' if name.endswith('.cpp') else 'clang-18','-m32',
                 '-D_FILE_OFFSET_BITS=64','-O2','-g','-ffile-prefix-map='+str(ROOT)+'=linux-port','-fno-omit-frame-pointer','-mstackrealign',
                 '-ffunction-sections','-fdata-sections',*shlex.split(pkg),
                 '-c',str(ROOT/'platform'/name),'-o',str(a.out/(Path(name).stem+'.o'))]
        result=subprocess.run(command,capture_output=True,text=True)
        (a.out/(name+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(name+': '+result.stderr[-4000:])
    print('Native ELF32 platform objects:',len(sources))


if __name__=='__main__':main()

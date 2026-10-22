"""Allowlisted launcher bundles; no original/game/mod art is included."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BUNDLE_VERSION='launcher-0.2.1'

# The minimal build (tools/build_linux.py --minimal) links SDL2, FFmpeg, GLU, zlib and
# libstdc++ statically. Anything else here means a build against system libraries,
# which then only starts on the distribution it was built on.
ALLOWED_NEEDED={'libGL.so.1','libm.so.6','libc.so.6','ld-linux.so.2'}


def linux_engine(path):
    """Release-ready game ELF: minimal dependencies, build-time debug info removed."""
    dynamic=subprocess.run(['readelf','-d',str(path)],capture_output=True,text=True,check=True).stdout
    needed={line.split('[',1)[1].split(']',1)[0] for line in dynamic.splitlines() if '(NEEDED)' in line}
    if needed-ALLOWED_NEEDED:
        raise ValueError('Game ELF needs system libraries '+', '.join(sorted(needed-ALLOWED_NEEDED))+
                         ': rebuild with tools/build_linux.py --minimal')
    with tempfile.TemporaryDirectory() as temporary:
        stripped=Path(temporary)/'titbit-game'
        subprocess.run(['strip','--strip-debug','--remove-section=.comment','-o',str(stripped),str(path)],check=True)
        return stripped.read_bytes()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--tools',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.engine.suffix.lower()=='.exe':
        return windows(a.engine,a.tools,a.out)
    files={'bin/titbit-game':a.engine,'bin/titbit-tools':a.tools,'README.md':ROOT/'docs/LAUNCHER.md',
           'THIRD_PARTY_NOTICES.md':ROOT/'THIRD_PARTY_NOTICES.md','config/assets.json':ROOT/'config/assets.json',
           'config/mods.json':ROOT/'config/mods.json'}
    for base,prefix in ((ROOT/'docs/licenses','docs/licenses'),(a.tools.parent/'tools-licenses','docs/licenses/runtime')):
        for path in base.rglob('*'):
            if path.is_file():files[prefix+'/'+path.relative_to(base).as_posix()]=path
    for name in ('src/seer/README.TXT','src/jpeg/README','src/native/app_module-CPL.TXT','editor/web/vendor/LICENSE','third_party/zlib-1.1.3/README'):
        files[name]=ROOT/name
    for path in (ROOT/'src/lanes').rglob('*LICENSE*'):
        if path.is_file():files[path.relative_to(ROOT).as_posix()]=path
    payloads={n:f.read_bytes()for n,f in files.items()}
    payloads['bin/titbit-game']=linux_engine(a.engine)
    payloads['Launch.sh']=b'#!/bin/sh\nset -eu\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport TITBIT_LINUX_GAME="$root/bin/titbit-game"\nexec "$root/bin/titbit-tools" launcher "$@"\n'
    payloads['LINUX.txt']=('Linux with glibc 2.38+ (Ubuntu 24.04+, Debian 13+, Fedora 39+).\n'
        'The game needs only 32-bit OpenGL, X11 and sound; video, SDL2 and the rest are built in.\n\n'
        'Ubuntu / Debian:\n'
        'sudo dpkg --add-architecture i386 && sudo apt update\n'
        'sudo apt install libgl1:i386 libgl1-mesa-dri:i386 libx11-6:i386 libxext6:i386 libxcursor1:i386 libxi6:i386 libxrandr2:i386 libpulse0:i386\n'
        '(with Steam installed they are usually already there)\n\n'
        './Launch.sh\n\nNative ELF32 game + bundled x86-64 launcher. No Python or VC6 required.\n'
        'Original game assets are imported from your copy. Widescreen art is an optional download.\n').encode()
    payloads['package.json']=json.dumps(dict(version=BUNDLE_VERSION,source='https://github.com/offx366/titbit-modern/tree/dev',
        sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        originalGameAssetsIncluded=False,generatedModArtIncluded=False)).encode()
    checks=''.join(hashlib.sha256(data).hexdigest()+'  '+n+'\n'for n,data in sorted(payloads.items()))
    payloads['SHA256SUMS.txt']=checks.encode()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('wb')as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0)as compressed,tarfile.open(fileobj=compressed,mode='w')as archive:
        for name,data in sorted(payloads.items()):
            if Path(name).suffix.lower()in('.ezd','.avi','.sav','.png','.tga','.titbitmod'):raise ValueError('Forbidden player data')
            entry=tarfile.TarInfo('Titbit/'+name);entry.size=len(data);entry.mtime=0
            entry.mode=0o755 if name in('bin/titbit-game','bin/titbit-tools','Launch.sh')else 0o644
            archive.addfile(entry,io.BytesIO(data))
    print(json.dumps(dict(path=str(a.out),sha256=hashlib.sha256(a.out.read_bytes()).hexdigest(),size=a.out.stat().st_size)))


def windows(engine,launcher,output):
    import shutil
    from tempfile import TemporaryDirectory
    # Tool set is deliberately enumerated. Never package a player's directory.
    files={'Titbit.exe':launcher,'bin/TitbitGame.exe':engine,'bin/TitbitStudio.exe':launcher.parent/'TitbitStudio.exe',
        'README.md':ROOT/'docs/LAUNCHER.md','THIRD_PARTY_NOTICES.md':ROOT/'THIRD_PARTY_NOTICES.md',
        'config/assets.json':ROOT/'config/assets.json','config/mods.json':ROOT/'config/mods.json'}
    for base,prefix in ((ROOT/'docs/licenses','docs/licenses'),):
        for path in base.rglob('*'):
            if path.is_file():files[prefix+'/'+path.relative_to(base).as_posix()]=path
    for name in ('src/seer/README.TXT','src/jpeg/README','src/native/app_module-CPL.TXT','editor/web/vendor/LICENSE','third_party/zlib-1.1.3/README'):
        files[name]=ROOT/name
    for path in (ROOT/'src/lanes').rglob('*LICENSE*'):
        if path.is_file():files[path.relative_to(ROOT).as_posix()]=path
    import PIL,PyInstaller
    files['docs/licenses/runtime/Python-LICENSE.txt']=Path(sys.base_prefix)/'LICENSE.txt'
    for base in (Path(PIL.__file__).parent.parent,Path(PyInstaller.__file__).parent.parent):
        for path in base.glob('*.dist-info/licenses/*'):
            if path.is_file()and path.parent.parent.name.lower().startswith(('pillow-','pyinstaller-')):
                files['docs/licenses/runtime/'+path.parent.parent.name+'-'+path.name]=path
    for path in (Path(sys.base_prefix)/'tcl').rglob('license.terms'):
        files['docs/licenses/runtime/'+path.parent.name+'-license.terms']=path
    payloads={n:f.read_bytes()for n,f in files.items()}
    payloads['НАЧНИТЕ ЗДЕСЬ.txt']=('Ядерный Титбит\n\nОткройте Titbit.exe.\nПри первом запуске укажите папку игры, диск или ISO.\nПо желанию: «Моды» → Widescreen → «Установить».\nНажмите «Играть». Настройки и Studio находятся там же.\n\nФайлы bin/ служебные. Python и VC6 не нужны.\nИнструкция: README.md\n').encode('utf-8-sig')
    payloads['package.json']=json.dumps(dict(version=BUNDLE_VERSION,source='https://github.com/offx366/titbit-modern/tree/dev',
        sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        originalGameAssetsIncluded=False,generatedModArtIncluded=False)).encode()
    payloads['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+n+'\n'for n,data in sorted(payloads.items())).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as archive:
        for name,data in sorted(payloads.items()):
            if Path(name).suffix.lower()in('.ezd','.avi','.sav','.png','.tga','.titbitmod'):raise ValueError('Forbidden player data')
            archive.writestr('Titbit/'+name,data)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),size=output.stat().st_size)))


if __name__=='__main__':main()

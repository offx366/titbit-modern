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

ROOT=Path(__file__).resolve().parents[1]
BUNDLE_VERSION='widescreen-0.1.1-gated'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--tools',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.engine.suffix.lower()=='.exe':
        return windows(a.engine,a.tools,a.out)
    files={'titbit':a.engine,'titbit-tools':a.tools,'README.md':ROOT/'docs/LAUNCHER.md',
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
    payloads['Launch.sh']=b'#!/bin/sh\nset -eu\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport TITBIT_LINUX_GAME="$root/titbit"\nexec "$root/titbit-tools" launcher "$@"\n'
    payloads['LINUX.txt']=('Ubuntu 24.04 x86-64:\n'
        'sudo dpkg --add-architecture i386\nsudo apt update\n'
        'sudo apt install libsdl2-2.0-0:i386 libavcodec60:i386 libavformat60:i386 libavutil58:i386 libswscale7:i386 libswresample4:i386 libgl1:i386 libglu1-mesa:i386 libstdc++6:i386\n'
        './Launch.sh\n\nNative ELF32 game + bundled x86-64 launcher. No Python or VC6 required.\n'
        'Original game assets are imported from your copy. Widescreen art is an optional download.\n').encode()
    payloads['package.json']=json.dumps(dict(version=BUNDLE_VERSION,source='https://github.com/offx366/titbit-modern/tree/widescreen-outpaint',
        sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        originalGameAssetsIncluded=False,generatedModArtIncluded=False)).encode()
    checks=''.join(hashlib.sha256(data).hexdigest()+'  '+n+'\n'for n,data in sorted(payloads.items()))
    payloads['SHA256SUMS.txt']=checks.encode()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('wb')as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0)as compressed,tarfile.open(fileobj=compressed,mode='w')as archive:
        for name,data in sorted(payloads.items()):
            if Path(name).suffix.lower()in('.ezd','.avi','.sav','.png','.tga','.titbitmod'):raise ValueError('Forbidden player data')
            entry=tarfile.TarInfo('TitbitLauncher/'+name);entry.size=len(data);entry.mtime=0
            entry.mode=0o755 if name in('titbit','titbit-tools','Launch.sh')else 0o644
            archive.addfile(entry,io.BytesIO(data))
    print(json.dumps(dict(path=str(a.out),sha256=hashlib.sha256(a.out.read_bytes()).hexdigest(),size=a.out.stat().st_size)))


def windows(engine,launcher,output):
    import shutil
    from tempfile import TemporaryDirectory
    # Tool set is deliberately enumerated. Never package a player's directory.
    files={'TitbitModern.exe':engine,'TitbitSettings.exe':engine.parent/'TitbitSettings.exe',
        'TitbitLauncher.exe':launcher,'TitbitSetup.exe':launcher.parent/'TitbitSetup.exe','TitbitStudio.exe':launcher.parent/'TitbitStudio.exe',
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
    payloads['НАЧНИТЕ ЗДЕСЬ.txt']=('Ядерный Титбит\n\nЗапустите TitbitLauncher.exe.\n«Файлы игры» — импорт вашей копии.\n«Моды» — установка Widescreen.\n«Игра» — запуск с модом или без него.\n\nПодробности: README.md\nPython и VC6 не требуются. Исходные ресурсы не входят в комплект.\n').encode('utf-8-sig')
    payloads['package.json']=json.dumps(dict(version=BUNDLE_VERSION,source='https://github.com/offx366/titbit-modern/tree/widescreen-outpaint',
        sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        originalGameAssetsIncluded=False,generatedModArtIncluded=False)).encode()
    payloads['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+n+'\n'for n,data in sorted(payloads.items())).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as archive:
        for name,data in sorted(payloads.items()):
            if Path(name).suffix.lower()in('.ezd','.avi','.sav','.png','.tga','.titbitmod'):raise ValueError('Forbidden player data')
            archive.writestr('TitbitLauncher/'+name,data)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),size=output.stat().st_size)))


if __name__=='__main__':main()

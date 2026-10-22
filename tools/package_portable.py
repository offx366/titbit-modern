"""Build self-contained Windows tools and a strictly allowlisted player ZIP."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

from project_icon import write_icon

BASE = Path(__file__).resolve().parents[1]
from project_version import VERSION, pyinstaller_version_file


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tools():
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise ValueError('Упаковка EXE выполняется на Windows x64.')
    try:
        versions = {n:importlib.metadata.version(n) for n in ('pyinstaller','Pillow')}
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError('Установите зависимости сборки: python -m pip install -r requirements-build.txt') from exc
    out = BASE/'build/portable-tools'; out.mkdir(parents=True, exist_ok=True)
    inputs = [BASE/'config/assets.json', BASE/'VERSION', BASE/'tools/project_version.py']
    inputs += [BASE/'tools'/n for n in ('titbit_setup.py','titbit_assets.py','titbit_launcher.py','titbit_mods.py','disc_image.py','project_icon.py')]
    inputs += list((BASE/'tools').glob('widescreen*.py')) + [BASE/'tools/widescreen_native_contours.json',BASE/'config/mods.json']
    inputs += [p for p in (BASE/'editor').rglob('*') if p.is_file()
               and not any(part in ('__pycache__','projects','TitbitStudio-projects') for part in p.relative_to(BASE/'editor').parts)
               and p.suffix.lower() in ('.py','.js','.json','.html','.css','.txt')]
    fingerprint = hashlib.sha256((json.dumps(versions, sort_keys=True)+sys.version+
                    ''.join(p.relative_to(BASE).as_posix()+sha(p) for p in sorted(inputs))).encode()).hexdigest()
    cached = out/'cache.json'
    if cached.exists():
        data = json.loads(cached.read_text())
        if data.get('fingerprint') == fingerprint and all((out/n).is_file() and sha(out/n)==v for n,v in data.get('files',{}).items()) and len(data.get('files',{}))==3:
            print('Launcher/Setup/Studio: verified build cache', flush=True)
            return out
    write_icon(out/'titbit-modern.ico')
    pyinstaller_version_file(out/'TitbitSetup.version','TitbitSetup.exe','Titbit game data import')
    pyinstaller_version_file(out/'TitbitStudio.version','TitbitStudio.exe','Titbit Studio scene editor')
    pyinstaller_version_file(out/'TitbitLauncher.version','TitbitLauncher.exe','Nuclear Titbit launcher and mods')
    for name, entry, extra in (
        ('TitbitSetup',BASE/'tools/titbit_setup.py', ['--version-file',str(out/'TitbitSetup.version'),'--paths',str(BASE/'tools'), '--add-data',str(BASE/'config/assets.json')+';config']),
        ('TitbitStudio',BASE/'editor/studio_launcher.py', ['--version-file',str(out/'TitbitStudio.version'),'--paths',str(BASE/'editor'), '--add-data',str(BASE/'editor/web')+';web']),
        ('TitbitLauncher',BASE/'tools/titbit_launcher.py', ['--version-file',str(out/'TitbitLauncher.version'),
            '--paths',str(BASE/'tools'),'--paths',str(BASE/'editor'),
            '--add-data',str(BASE/'config/assets.json')+';config','--add-data',str(BASE/'config/mods.json')+';config',
            '--add-data',str(BASE/'tools/widescreen_native_contours.json')+';tools',
            *[item for name in ('widescreen','widescreen_menu','widescreen_exits','widescreen_foreground','widescreen_occluders','widescreen_native_overlays','widescreen_native_masks','formats') for item in ('--hidden-import',name)]]),
    ):
        cmd = [sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--noupx',
               '--name',name,'--icon',str(out/'titbit-modern.ico'),'--distpath',str(out),
               '--workpath',str(out/'work'/name),'--specpath',str(out/'spec'),*extra,str(entry)]
        print('Building '+name+'…',flush=True)
        run = subprocess.run(cmd, cwd=BASE, capture_output=True)
        (out/(name+'.log')).write_bytes(run.stdout+run.stderr)
        if run.returncode:
            raise RuntimeError('PyInstaller failed: '+str(out/(name+'.log')))
    cached.write_text(json.dumps({'fingerprint':fingerprint,'files':{n:sha(out/n) for n in ('TitbitSetup.exe','TitbitStudio.exe','TitbitLauncher.exe')}},indent=2))
    return out


def assemble(game_build, tool_build, output, version=VERSION):
    game_build, tool_build, output = map(lambda p:Path(p).resolve(), (game_build,tool_build,output))
    # Do not glob the game directory: it may already contain the user's data/saves.
    sources = {n:game_build/n for n in ('TitbitModern.exe','TitbitSettings.exe')}
    sources.update({n:tool_build/n for n in ('TitbitSetup.exe','TitbitStudio.exe','TitbitLauncher.exe')})
    for name, path in sources.items():
        if not path.is_file() or path.read_bytes()[:2] != b'MZ':
            raise ValueError('Не найден собранный '+name)
    output.mkdir(parents=True,exist_ok=True)
    archive = output/f'TitbitModern-{version}-windows-x64.zip'
    with tempfile.TemporaryDirectory(prefix='titbit-package-',dir=output) as temp:
        package = Path(temp)/'TitbitModern'; package.mkdir()
        for name, path in sources.items():
            shutil.copy2(path, package/name)
        (package/'titbit_compat.ini').write_text('[compat]\ndisplay=fullscreen\nresolution=1024x768\naspect=fit\nsetup=modern\ncd=folder\nvideo=auto\nreplay=off\n',encoding='ascii')
        for name in ('README.md','THIRD_PARTY_NOTICES.md'):
            shutil.copy2(BASE/name,package/name)
        (package/'editor').mkdir()
        shutil.copy2(BASE/'editor/README.md',package/'editor/README.md')
        (package/'config').mkdir()
        shutil.copy2(BASE/'config/assets.json',package/'config/assets.json')
        shutil.copy2(BASE/'config/mods.json',package/'config/mods.json')
        shutil.copy2(BASE/'docs/LAUNCHER.md',package/'docs-launcher.md')
        docs = package/'docs';docs.mkdir()
        for name in ('GETTING_STARTED.md','ASSETS.md','BUILD.md','VALIDATION.md','VALIDATION-NO-VC6.md','VERIFY.md','validation.json','validation-no-vc6.json'):
            shutil.copy2(BASE/'docs'/name,docs/name)
        shutil.copytree(BASE/'docs/images',docs/'images')
        shutil.copytree(BASE/'docs/licenses',docs/'licenses')
        runtime = docs/'licenses/runtime'; runtime.mkdir()
        python_license = Path(sys.base_prefix)/'LICENSE.txt'
        if python_license.is_file():
            shutil.copy2(python_license,runtime/'Python-LICENSE.txt')
        import PIL
        for p in Path(PIL.__file__).parent.parent.glob('pillow-*.dist-info/licenses/*'):
            if p.is_file():shutil.copy2(p,runtime/('Pillow-'+p.name))
        for p in (Path(sys.base_prefix)/'tcl').rglob('license.terms'):
            shutil.copy2(p,runtime/(p.parent.name+'-license.terms'))
        import PyInstaller
        for p in Path(PyInstaller.__file__).parent.parent.glob('pyinstaller-*.dist-info/licenses/*'):
            if p.is_file():shutil.copy2(p,runtime/('PyInstaller-'+p.name))
        # The portable player archive has the same notices as the source tree.
        notices = ['src/seer/README.TXT','src/jpeg/README','src/native/app_module-CPL.TXT',
                   'editor/web/vendor/LICENSE','third_party/zlib-1.1.3/README']
        for name in notices:
            src=BASE/name
            if src.is_file():
                target=package/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        for p in (BASE/'src/lanes').rglob('*LICENSE*'):
            if p.is_file():
                target=package/p.relative_to(BASE);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        (package/'НАЧНИТЕ ЗДЕСЬ.txt').write_text('Ядерный Титбит · Лаунчер\n\n1. Распакуйте всю папку из ZIP.\n2. Откройте TitbitLauncher.exe. Вкладка «Файлы игры» — импорт вашей копии из папки, диска или ISO/IMG/CUE/CCD.\n3. На вкладке «Игра» запустите оригинал 4:3.\n4. По желанию: вкладка «Моды» → формат → «Скачать и установить». Затем выберите Widescreen на вкладке «Игра».\n\nИнструкция: docs-launcher.md. Python и VC6 не нужны. Исходные ассеты не входят в комплект.\nTitbitModern.exe — прямой запуск без лаунчера; TitbitSettings.exe — прежние настройки; TitbitStudio.exe — редактор.\n\nEXE не подписаны. Проверка файлов — docs/VERIFY.md.\n',encoding='utf-8-sig')
        try:
            commit=subprocess.check_output(['git','-C',str(BASE),'rev-parse','HEAD'],stderr=subprocess.DEVNULL).decode().strip()
            dirty=bool(subprocess.check_output(['git','-C',str(BASE),'status','--porcelain','--untracked-files=no']))
        except (OSError,subprocess.CalledProcessError):
            commit,dirty=None,None
        metadata={'version':version,'source':'https://github.com/offx366/titbit-modern',
                  'sourceCommit':commit,'sourceTreeDirty':dirty,
                  'executables':{n:sha(package/n) for n in sources},
                  'originalDataIncluded':False,'platform':'Windows 10/11 x64; game executable x86'}
        info=game_build/'build-info.json'
        if info.is_file():
            built=json.loads(info.read_text(encoding='utf-8'))
            metadata['reproducible']={'sourceDateEpoch':built.get('sourceDateEpoch'),
                                      'tools':built.get('tools'),'libraries':built.get('libraries'),
                                      'headers':built.get('headers'),
                                      'runtime':built.get('runtime'),'requiresVC6':built.get('requiresVC6',True)}
        (package/'package.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf8')
        paths=sorted(p for p in package.rglob('*') if p.is_file())
        for p in paths:
            if p.suffix.lower() in ('.ezd','.avi','.sav','.img','.iso','.cue','.ccd','.sub','.cab'):
                raise ValueError('Original game data cannot be packaged: '+p.name)
        (package/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(package).as_posix()}\n' for p in paths),encoding='utf8')
        temporary=archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(package.rglob('*')):
                if p.is_file():z.write(p,'TitbitModern/'+p.relative_to(package).as_posix())
        temporary.replace(archive)
    archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
    print('Portable package: '+str(archive),flush=True)
    return archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-build',type=Path,default=BASE/'build/modern-portable')
    parser.add_argument('--out',type=Path,default=BASE/'dist')
    parser.add_argument('--version',default=VERSION)
    args=parser.parse_args()
    if not args.version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-' for c in args.version):
        raise ValueError('Invalid package version')
    assemble(args.game_build,tools(),args.out,args.version)


if __name__=='__main__':
    main()

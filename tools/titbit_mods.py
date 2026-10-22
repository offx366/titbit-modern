"""Data-only mod packages, verified downloads and isolated game profiles.

No package-supplied code is executed. QUEST is assembled locally using the
launcher's versioned recipe, and original assets are never overwritten.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile

import titbit_assets as assets

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
RECIPE = 'isolated-background-native-overlays-v11'
MOD_ID = 'widescreen'
VERSION = '0.1.0'
RETAINED = ['sex_podval.XML', 'sex_podval_n.xml', 'sex_podval_divan.XML']
MAX_PACKAGE = 180 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def sha(path, cancel=None):
    return assets.hash_file(Path(path), cancel=cancel)


def all_mods():
    data = read_json(ROOT / 'config/mods.json')
    if data.get('schema') != 1:
        raise ValueError('Неподдерживаемый каталог модов')
    return data['mods']


def catalog():
    return all_mods()[MOD_ID]


def check_base(base, progress=None, cancel=None):
    # Fingerprints identify the supported release; they do not prove ownership.
    return assets.verify_install(base, progress, cancel)


@contextlib.contextmanager
def locked(store):
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    with (store / '.launcher.lock').open('a+b') as file:
        file.seek(0); file.write(b'\0'); file.flush(); file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Лаунчер или игра уже использует эту папку. Дождитесь завершения.') from exc
        try:
            yield
        finally:
            file.seek(0)
            if os.name == 'nt':
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file, fcntl.LOCK_UN)


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        secure_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def secure_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Для загрузки требуется HTTPS URL без учётных данных')


def download(record, cache, progress=None, cancel=None):
    """Pinned catalog, HTTPS including redirects, bounded streaming, atomic cache."""
    size, checksum = record['size'], record['sha256']
    if not isinstance(size, int) or not 0 < size <= MAX_PACKAGE or not re.fullmatch('[a-f0-9]{64}', checksum):
        raise ValueError('Некорректный размер или SHA256 в каталоге')
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    target = cache / (checksum + '.titbitmod')
    if target.is_file() and target.stat().st_size == size and sha(target, cancel) == checksum:
        return target
    errors = []
    opener = urllib.request.build_opener(HTTPSOnly())
    for url in record['urls']:
        assets.check_cancel(cancel); secure_url(url)
        partial = cache / (checksum + '.partial')
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'TitbitLauncher/1.0'})
            with opener.open(request, timeout=25) as response, partial.open('wb') as output:
                secure_url(response.url)
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) != size:
                    raise ValueError('Сервер вернул другой размер пакета')
                done = 0; digest = hashlib.sha256()
                while block := response.read(256 * 1024):
                    assets.check_cancel(cancel); done += len(block)
                    if done > size:
                        raise ValueError('Пакет больше указанного размера')
                    output.write(block); digest.update(block)
                    if progress: progress('Скачивание готовых widescreen-фонов', done, size)
            if done != size or digest.hexdigest() != checksum:
                raise ValueError('Скачанный пакет не прошёл проверку SHA256')
            assets.check_cancel(cancel)
            os.replace(partial, target)
            return target
        except assets.ImportCancelled:
            raise
        except (OSError, ValueError) as exc:
            errors.append(f'{urllib.parse.urlsplit(url).hostname}: {exc}')
        finally:
            partial.unlink(missing_ok=True)
    raise ValueError('Загрузка не удалась. Можно установить .titbitmod из файла.\n' + '\n'.join(errors))


def package_manifest(package):
    """Validate a constrained ZIP before any file is written or image decoded."""
    package = Path(package)
    if package.stat().st_size > MAX_PACKAGE:
        raise ValueError('Слишком большой пакет мода')
    with zipfile.ZipFile(package) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        if len(entries) > 50 or len(names) != len(set(n.casefold() for n in names)):
            raise ValueError('Повторяющиеся файлы или слишком много файлов в пакете')
        if sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise ValueError('Пакет превышает допустимый размер распаковки')
        for i in entries:
            p = PurePosixPath(i.filename)
            if ('\\' in i.filename or ':' in i.filename or p.is_absolute() or
                    '..' in p.parts or str(p) != i.filename or i.is_dir() or
                    stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1 or
                    i.file_size > 8 * 1024 * 1024):
                raise ValueError('Недопустимый файл пакета: ' + i.filename)
        if 'manifest.json' not in names or z.getinfo('manifest.json').file_size > 128 * 1024:
            raise ValueError('Нет корректного manifest.json')
        manifest = json.loads(z.read('manifest.json'))
        if (manifest.get('schema') != 1 or manifest.get('id') != MOD_ID or
                manifest.get('version') != VERSION or manifest.get('recipe') != RECIPE or
                manifest.get('baseSha256') != assets.manifest()['QUEST.ezd']['sha256'] or
                manifest.get('retainedScenes') != RETAINED):
            raise ValueError('Пакет несовместим с этой версией лаунчера')
        images = manifest.get('backgrounds', [])
        if len(images) != 38:
            raise ValueError('Нужен полный набор из 38 задников')
        ids = [row.get('id', '') for row in images]
        if len(set(ids)) != 38 or any(not re.fullmatch('[A-Za-z0-9_.-]{1,100}', x) for x in ids):
            raise ValueError('Некорректные идентификаторы задников')
        files = manifest.get('files', {})
        allowed = {'art/' + ident + '.png' for ident in ids} | {'art/menu.png'}
        if set(files) != allowed or set(names) != allowed | {'manifest.json'}:
            raise ValueError('Пакет содержит неизвестные файлы; код в модах не поддерживается')
        for name, record in files.items():
            if (z.getinfo(name).file_size != record['size'] or
                    not re.fullmatch('[a-f0-9]{64}', record['sha256']) or
                    hashlib.sha256(z.read(name)).hexdigest() != record['sha256']):
                raise ValueError('Повреждён файл мода: ' + name)
    return manifest


def create_package(work, output):
    """Maintainer command. Only accepted GENERATED art and small metadata enter ZIP."""
    import widescreen as wide
    work, output = Path(work), Path(output)
    source = read_json(work / 'manifest.json')
    retained = wide.original_scenes(work, source)
    required = wide.required_backgrounds(source, retained)
    images = []; paths = {}
    for row in source['textures']:
        if row['name'].casefold() not in required: continue
        proof = read_json(work / 'out' / (row['id'] + '.json'))
        path = work / 'out/16x9' / (row['id'] + '.png')
        if sha(path) != proof['variants']['16x9']['sha256']:
            raise ValueError('Изменился принятый фон: ' + row['name'])
        # Deliberate field allowlist: no local paths, original pixels or QA captures.
        images.append(dict(id=row['id'], sourceTextureSha256=row['sourceSha256'],
                           nativeForegroundScenes=proof.get('nativeForegroundScenes', []),
                           sourceAlignedSceneArt=proof.get('sourceAlignedSceneArt', False)))
        paths['art/' + row['id'] + '.png'] = path
    paths['art/menu.png'] = work / 'menu/background.png'
    menu = read_json(work / 'menu/accepted.json')
    menu = {k:menu[k] for k in ('recipe', 'sha256', 'sourceAtlasSha256', 'sourceItemsSha256')}
    manifest = dict(schema=1, id=MOD_ID, version=VERSION, recipe=RECIPE,
                    title='Ядерный Титбит · Widescreen', baseSha256=source['archiveSha256'],
                    retainedScenes=RETAINED, backgrounds=images, menu=menu,
                    generatedArt=True, originalGameDataIncluded=False,
                    files={n:dict(size=p.stat().st_size, sha256=sha(p)) for n,p in paths.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as z:
        payloads = {'manifest.json': json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()}
        payloads.update({n:p.read_bytes() for n,p in paths.items()})
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, (2026, 10, 22, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            z.writestr(info, payloads[name])
    package_manifest(output)
    return dict(size=output.stat().st_size, sha256=sha(output), images=len(images)+1)


def installed(store, ratio):
    if ratio not in ('16x9', '16x10'): raise ValueError('Неизвестный формат экрана')
    profile = Path(store) / 'profiles' / (MOD_ID + '-' + ratio)
    if profile.is_symlink() or profile.resolve().parent != profile.parent.resolve():
        raise ValueError('Профиль не должен быть ссылкой на другую папку')
    marker = profile / 'mod.json'
    if marker.is_file():
        data = read_json(marker)
        if data.get('recipe') == RECIPE and data.get('version') == VERSION and (profile/'QUEST.ezd').is_file():
            return profile
    return None


def install(package, base, store, ratio, progress=None, cancel=None):
    """All-or-nothing profile creation; caller holds locked(store)."""
    if ratio not in ('16x9', '16x10'): raise ValueError('Неизвестный формат экрана')
    base, store = Path(base).resolve(), Path(store).resolve()
    if installed(store, ratio):
        raise ValueError('Мод уже установлен для этого формата')
    if progress: progress('Проверка оригинальных файлов игры', 0, 0)
    check_base(base, progress, cancel)
    return install_verified(package, base, store, ratio, progress, cancel)


def install_verified(package, base, store, ratio, progress=None, cancel=None):
    # Private helper for GUI, which verifies originals before starting a download.
    from PIL import Image
    import widescreen as wide
    if ratio not in ('16x9','16x10'): raise ValueError('Неизвестный формат экрана')
    base, store = Path(base).resolve(), Path(store).resolve()
    metadata = package_manifest(package)
    parent = store / 'profiles'; parent.mkdir(parents=True, exist_ok=True)
    target = parent / (MOD_ID + '-' + ratio)
    if target.exists(): raise ValueError('Профиль уже существует; удалите мод через лаунчер')
    if shutil.disk_usage(parent).free < 650 * 1024 * 1024:
        raise ValueError('Для локальной сборки нужно 650 МиБ свободного места')
    with tempfile.TemporaryDirectory(prefix='.mod-stage-', dir=parent) as temp:
        work = Path(temp) / 'work'
        assets.check_cancel(cancel)
        if progress: progress('Чтение структуры локального QUEST.ezd', 0, 0)
        manifest = wide.extract(base / 'QUEST.ezd', work, export_sources=False)
        (work/'original-scenes.txt').write_text('\n'.join(RETAINED), encoding='utf-8')
        required = wide.required_backgrounds(manifest, wide.original_scenes(work, manifest))
        rows = {row['id']:row for row in manifest['textures'] if row['name'].casefold() in required}
        if set(rows) != {row['id'] for row in metadata['backgrounds']}:
            raise ValueError('Локальные сцены не соответствуют пакету')
        with zipfile.ZipFile(package) as z:
            for i, row in enumerate(metadata['backgrounds']):
                assets.check_cancel(cancel)
                native = rows[row['id']]
                if row['sourceTextureSha256'] != native['sourceSha256']:
                    raise ValueError('Исходная текстура изменилась: ' + native['name'])
                raw = z.read('art/' + row['id'] + '.png')
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'PNG' or image.size != (1366, 768):
                        raise ValueError('Неверный формат дорисованного фона')
                    image = image.convert('RGBA')
                    width = wide.RATIOS[ratio]; offset = (1366-width)//2
                    final = image.crop((offset, 0, offset+width, 768))
                    dest = work / 'out' / ratio / (row['id'] + '.png')
                    dest.parent.mkdir(parents=True, exist_ok=True); final.save(dest)
                wide.save(work/'out'/(row['id']+'.json'), dict(recipe=wide.RECIPE,
                    sourceArchiveSha256=manifest['archiveSha256'], sourceTextureSha256=native['sourceSha256'],
                    nativeForegroundScenes=row['nativeForegroundScenes'], sourceAlignedSceneArt=row['sourceAlignedSceneArt'],
                    variants={ratio:dict(sha256=sha(dest), originalCenterComposited=False)}))
                if progress: progress('Подготовка дорисованных фонов', i+1, len(rows))
            (work/'menu').mkdir()
            menu_bytes=z.read('art/menu.png')
            with Image.open(io.BytesIO(menu_bytes)) as menu:
                if menu.format!='PNG' or menu.size!=(1366,768):
                    raise ValueError('Неверный формат дорисованного меню')
            (work/'menu/background.png').write_bytes(menu_bytes)
            wide.save(work/'menu/accepted.json', metadata['menu'])
        assets.check_cancel(cancel)
        if progress: progress('Локальная сборка архива и проверка ресурсов. Отмена — после текущего этапа.', 0, 0)
        wide.pack(work, ratio, require_complete=True)
        assets.check_cancel(cancel)
        built = work / 'mod' / ratio
        proof = read_json(built/'proof.json')
        if not proof['originalUnchanged'] or not proof['completeRequestedWorldBackgrounds']:
            raise ValueError('Сборка мода не прошла проверку')
        write_json(built/'mod.json', dict(id=MOD_ID, version=VERSION, recipe=RECIPE, ratio=ratio,
                   packageSha256=sha(package), archiveSha256=proof['modSha256'],
                   baseSha256=manifest['archiveSha256']))
        os.rename(built, target)
    return target


def remove(store, ratio):
    """Remove only generated runtime files. Saves and user configuration survive."""
    profile = installed(store, ratio)
    if profile is None: raise ValueError('Мод не установлен')
    return retire_profile(store, profile)


def retire_profile(store, profile):
    profile = Path(profile)
    if profile.is_symlink() or profile.resolve().parent != (Path(store)/'profiles').resolve():
        raise ValueError('Неверная папка профиля')
    # Atomic retirement first: unknown files/config/saves remain in this backup.
    saves = Path(store)/'saves'; saves.mkdir(parents=True, exist_ok=True)
    backup = saves/(profile.name+'-'+str(time.time_ns()))
    os.rename(profile, backup)
    for name in ('QUEST.ezd', 'widescreen-scenes.txt', 'proof.json', 'mod.json', 'TitbitModern.exe'):
        (backup/name).unlink(missing_ok=True)
    for path in backup.iterdir():
        if path.suffix.casefold() == '.avi': path.unlink()
    return backup


def link_media(source, destination):
    if destination.is_symlink(): raise ValueError('Файл профиля является ссылкой: '+destination.name)
    if destination.exists():
        if sha(source) != sha(destination): raise ValueError('Файл профиля отличается: '+destination.name)
        return
    try: os.link(source, destination)
    except OSError: shutil.copy2(source, destination)


def prepare_launch(base, store, engine, mode, display='fullscreen', resolution='desktop', *, runtime_profile=None, seed_profiles=()):
    """Return argv/cwd/env without starting a process (also used by hidden QA)."""
    base, store, engine = Path(base).resolve(), Path(store).resolve(), Path(engine).resolve()
    if mode not in ('original', '16x9', '16x10'): raise ValueError('Неизвестный режим')
    if display not in ('windowed', 'fullscreen'): raise ValueError('Неверный режим окна')
    if resolution not in ('desktop', '1024x768', '1230x768', '1366x768', '1600x900', '1920x1080', '1920x1200', '2560x1440'):
        raise ValueError('Неподдерживаемое разрешение')
    original = base/'QUEST.ezd'; expected = assets.manifest()['QUEST.ezd']
    if not original.is_file() or sha(original) != expected['sha256']:
        raise ValueError('Сначала импортируйте и проверьте оригинальную копию игры')
    if not engine.is_file(): raise ValueError('Не найден движок игры: '+str(engine))
    if mode != 'original' and sha(engine) != catalog()['testedEngines']['windows' if os.name == 'nt' else 'linux']:
        raise ValueError('Для мода нужен движок из комплекта Widescreen 0.1.0. Обновите комплект лаунчера; старые версии игры не поддерживают широкое меню.')
    source_profile = store/'profiles/original' if mode == 'original' else installed(store, mode)
    if source_profile is None: raise ValueError('Сначала установите Widescreen')
    profile = Path(runtime_profile) if runtime_profile else source_profile
    if profile.is_symlink() or profile.resolve().parent != profile.parent.resolve():
        raise ValueError('Профиль не должен быть ссылкой на другую папку')
    profile.mkdir(parents=True, exist_ok=True)
    if mode == 'original': link_media(original, profile/'QUEST.ezd')
    else:
        marker = read_json(source_profile/'mod.json')
        if sha(source_profile/'QUEST.ezd') != marker['archiveSha256']:
            raise ValueError('Архив мода изменён; переустановите мод')
        if profile != source_profile:
            # Switch only generated files; keep one save location for both shapes.
            for name in ('QUEST.ezd', 'widescreen-scenes.txt'):
                target = profile/name
                if target.is_symlink(): raise ValueError('Файл профиля является ссылкой')
                if not target.exists() or sha(target) != sha(source_profile/name):
                    temporary = target.with_suffix(target.suffix+'.tmp')
                    temporary.unlink(missing_ok=True)
                    link_media(source_profile/name, temporary)
                    os.replace(temporary, target)
            write_json(profile/'mod.json', marker)
    for name in assets.manifest():
        if not name.lower().endswith('.avi'): continue
        source = base/name
        if not source.is_file() or source.stat().st_size != assets.manifest()[name]['size']:
            raise ValueError('Нет оригинального видео: '+name)
        link_media(source, profile/name)
    # Independent saves, seeded once from the imported game; never hardlink saves.
    if not (profile/'.saves-seeded').exists():
        backups = sorted(p for p in (store/'saves').glob(profile.name+'-*')
                         if p.name.rsplit('-',1)[0] == profile.name) if (store/'saves').exists() else []
        old = backups[-1] if backups else store/'saves'/profile.name
        # Existing variant saves win over the imported base; choose newest per slot.
        if old.is_dir():
            for source in old.glob('*.sav'):
                if not (profile/source.name).exists(): shutil.copy2(source, profile/source.name)
        seeds = [p for d in seed_profiles if Path(d).is_dir() for p in Path(d).glob('*.sav')]
        for source in sorted(seeds, key=lambda p:p.stat().st_mtime_ns, reverse=True):
            if not (profile/source.name).exists(): shutil.copy2(source, profile/source.name)
        for source_dir in (old, base):
            if source_dir.is_dir():
                for source in source_dir.glob('*.sav'):
                    if not (profile/source.name).exists(): shutil.copy2(source, profile/source.name)
        (profile/'.saves-seeded').touch()
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('TITBIT_COMPAT_') or key in ('TITBIT_WIDESCREEN', 'TITBIT_WIDESCREEN_SCENES'):
            env.pop(key)
    wide = mode != 'original'
    env.update(TITBIT_GAME=str(profile), TITBIT_WIDESCREEN_SCENES=str(profile/'widescreen-scenes.txt'))
    if os.name == 'nt':
        dest = profile/'TitbitModern.exe'
        if dest.is_symlink(): raise ValueError('EXE профиля является ссылкой')
        if not dest.exists() or sha(dest) != sha(engine): shutil.copy2(engine, dest)
        (profile/'titbit_compat.ini').write_text('[compat]\nsetup=modern\ncd=folder\nvideo=auto\n'
            f'display={display}\nresolution={resolution}\naspect={"widescreen" if wide else "fit"}\n'
            f'widescreen_ratio={mode.replace("x", ":")}\n', encoding='ascii')
        argv = [str(dest)]
    else:
        argv = [str(engine), '--data', str(profile), '--'+display]
        if wide: argv += ['--widescreen='+mode.replace('x', ':')]
    return dict(argv=argv, cwd=str(profile), env=env, profile=str(profile))


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('pack'); b.add_argument('--work', type=Path, required=True); b.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('inspect'); v.add_argument('package', type=Path)
    i = sub.add_parser('install'); i.add_argument('package', type=Path); i.add_argument('--data', type=Path, required=True)
    i.add_argument('--store', type=Path, required=True); i.add_argument('--ratio', choices=('16x9','16x10'), default='16x9')
    a = p.parse_args(argv)
    if a.command == 'pack': result = create_package(a.work, a.out)
    elif a.command == 'inspect': result = package_manifest(a.package)
    else:
        with locked(a.store): result = str(install(a.package, a.data, a.store, a.ratio, lambda n,d,t: print(n,d,t,flush=True)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

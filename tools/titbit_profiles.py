"""Launcher preferences, automatic viewport choice and enabled mod profiles."""
from __future__ import annotations

from pathlib import Path

import titbit_mods as mods


def preferences(store, data):
    path = Path(store)/'launcher.json'
    saved = mods.read_json(path) if path.is_file() else {}
    # Migrate the old mutually exclusive original/16x9/16x10 selector.
    enabled = saved.get('enabledMods')
    if enabled is None:
        enabled = ['widescreen'] if saved.get('mode') in ('16x9', '16x10') else []
    if not isinstance(enabled, list) or any(not isinstance(x, str) for x in enabled):
        raise ValueError('Повреждён список модов в launcher.json')
    return dict(data=saved.get('data', str(data)), enabledMods=list(dict.fromkeys(enabled)),
                display=saved.get('display', 'fullscreen'), resolution=saved.get('resolution', 'desktop'))


def automatic_ratio(width, height, resolution='desktop'):
    if resolution != 'desktop':
        width, height = map(int, resolution.split('x'))
    aspect = max(1, width)/max(1, height)
    return min(('16x9', '16x10'), key=lambda r: abs(aspect - (16/9 if r == '16x9' else 16/10)))


def has_widescreen(store):
    return any(mods.installed(store, r) for r in ('16x9', '16x10'))


def install_widescreen(base, store, ratio, package=None, progress=None, cancel=None):
    if package is None and mods.installed(store, ratio):
        return mods.installed(store, ratio)
    if package is None:
        import titbit_gate
        package = titbit_gate.obtain(mods.catalog(), base, Path(store)/'downloads', progress, cancel)
    else:
        mods.check_base(base, progress, cancel)
        # Keep verified offline imports too: another monitor needs no second download.
        from shutil import copyfile
        mods.package_manifest(package)
        record = mods.catalog()
        if mods.sha(package) != record['sha256']:
            raise ValueError('Неизвестная версия Widescreen')
        cache = Path(store)/'downloads'/(record['sha256']+'.titbitmod')
        cache.parent.mkdir(parents=True, exist_ok=True)
        if Path(package).resolve() != cache.resolve():
            temporary = cache.with_suffix('.partial')
            try:
                copyfile(package, temporary)
                if mods.sha(temporary, cancel) != record['sha256']:
                    raise ValueError('Повреждён пакет Widescreen')
                temporary.replace(cache)
            finally:
                temporary.unlink(missing_ok=True)
        package = cache
    if mods.installed(store, ratio):
        return mods.installed(store, ratio)
    return mods.install_verified(package, base, store, ratio, progress, cancel)


def prepare(base, store, engine, enabled, ratio, display='fullscreen', resolution='desktop', progress=None, cancel=None):
    """An ordered set, rather than an exclusive mode; recipes stay built into tools.

    New mod recipes can extend this dispatch without changing launcher preferences.
    Unknown recipes fail explicitly instead of launching with a mod silently omitted.
    """
    enabled = list(dict.fromkeys(enabled))
    unsupported = set(enabled) - {'widescreen'}
    if unsupported:
        raise ValueError('Для этих модов нужен новый лаунчер: '+', '.join(sorted(unsupported)))
    if not enabled:
        return mods.prepare_launch(base, store, engine, 'original', display, resolution)
    install_widescreen(base, store, ratio, progress=progress, cancel=cancel)
    # The active profile is independent of monitor shape, so saves follow the mod.
    variants = [mods.installed(store, r) for r in ('16x9', '16x10')]
    variants = [p for p in variants if p]
    return mods.prepare_launch(base, store, engine, ratio, display, resolution,
                               runtime_profile=Path(store)/'profiles/widescreen', seed_profiles=variants)


def remove_widescreen(store):
    removed = []
    for ratio in ('16x9', '16x10'):
        if mods.installed(store, ratio):
            removed.append(mods.remove(store, ratio))
    active = Path(store)/'profiles/widescreen'
    if active.exists():
        removed.append(mods.retire_profile(store, active))
    return removed

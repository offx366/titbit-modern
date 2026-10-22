#!/usr/bin/env python3
"""Stage only browser runtime files for a static host; never publish the build tree."""
import argparse
import json
from pathlib import Path
import shutil
import titbit_assets

RUNTIME = ('game.html', 'game.js', 'bootstrap.js', 'isolation-worker.js',
           'browser_start.scv', 'saves.js', 'assets.js', 'audio-worklet.js', 'titbit.js', 'titbit.wasm', 'game-assets.json')


def package(source, target, game_data=None):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target == source or source in target.parents or target in source.parents:
        raise ValueError('Publication directory must be separate from the build directory')
    missing = [name for name in RUNTIME if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError('Missing runtime files: ' + ', '.join(missing))
    files = []
    if game_data is not None:
        game_data = Path(game_data).resolve()
        titbit_assets.verify_install(game_data)
        files = [dict(name=name, url=f'assets/{name}', **record)
                 for name, record in titbit_assets.manifest().items()]
    # Refuse to upload leftovers from an unrelated or previous build.
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError('Publication directory must be empty')
    for name in RUNTIME:
        shutil.copyfile(source / name, target / name)
    shutil.copyfile(source / 'game.html', target / 'index.html')
    if files:
        (target / 'assets').mkdir()
        for file in files:
            shutil.copyfile(game_data / file['name'], target / 'assets' / file['name'])
    (target / 'game-assets.json').write_text(json.dumps(dict(version=1, files=files)) + '\n')
    (target / '.nojekyll').touch()
    print(f'Browser site: {target}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=Path(__file__).resolve().parents[1] / 'build/web/game')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--game-data', type=Path, help='Explicitly include verified original game files in the public site')
    args = parser.parse_args()
    package(args.build, args.out, args.game_data)

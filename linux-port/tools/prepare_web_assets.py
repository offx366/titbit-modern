#!/usr/bin/env python3
"""Optionally fetch user-supplied game data for a Pages build, then hash-check it."""
import argparse
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import titbit_assets

PROJECT = Path(__file__).resolve().parents[2]


def download(magnet, destination):
    if urlsplit(magnet).scheme != 'magnet' or any(c in magnet for c in '\r\n\0'):
        raise ValueError('TITBIT_GAME_MAGNET must be a single magnet URI')
    # Keep the secret out of command arguments, Nix derivations and subprocess
    # logs. No downloaded files or torrent metadata enter the dependency cache.
    environment = {k: v for k, v in os.environ.items() if k != 'TITBIT_GAME_MAGNET'}
    result = subprocess.run([
        'aria2c', '--no-conf=true', f'--dir={destination}', '--input-file=-',
        '--seed-time=0', '--bt-stop-timeout=120', '--stop=900',
        '--summary-interval=0', '--console-log-level=error', '--download-result=hide',
    ], input=magnet + '\n', text=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=environment, timeout=930, check=False)
    if result.returncode:
        raise RuntimeError('Game download failed. Check the magnet URI and availability of peers.')


def prepare(destination, source=None, magnet=None):
    if source is None and not magnet:
        if Path(destination).exists():
            raise ValueError('Remove existing game data before building without TITBIT_GAME_MAGNET')
        print('TITBIT_GAME_MAGNET is not set; keeping local file selection.')
        return
    with tempfile.TemporaryDirectory(prefix='titbit-web-assets-') as folder:
        temporary = Path(folder)
        if source is None:
            source = temporary / 'download'
            source.mkdir()
            download(magnet, source)
        # Reuse the existing disc/directory selector and importer. Neither the
        # installer nor any executable from the downloaded game is executed.
        importer = temporary / 'titbit-setup'
        importer.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                            shlex.quote(str(PROJECT / 'linux-port/tools/titbit_setup.py')) + ' "$@"\n')
        importer.chmod(0o700)
        spec = importlib.util.spec_from_file_location('titbit_data_prepare', PROJECT / 'nix/game-data/prepare.py')
        selector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(selector)
        selected = selector.select_source(str(importer), Path(source).resolve())
        with closing(titbit_assets.inspect_source(selected)) as plan:
            titbit_assets.install_assets(plan, destination)
        titbit_assets.verify_install(destination)
        print('Verified 19 original game files for the bundled site.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source', type=Path, help='Import a local directory/disc instead of downloading')
    args = parser.parse_args()
    try:
        prepare(args.out, args.source, os.environ.get('TITBIT_GAME_MAGNET'))
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + '\n')

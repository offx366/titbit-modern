#!/usr/bin/env python3
"""Serve a local browser build with the isolation required by WebAssembly threads."""
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    archive = None

    def do_GET(self):
        if self.path.split('?')[0] == '/local-game/videos.json' and self.archive:
            data = json.dumps(sorted(p.name for p in self.archive.parent.iterdir()
                                     if p.is_file() and p.suffix.lower() == '.avi')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def translate_path(self, path):
        if path.split('?')[0] == '/local-game/QUEST.ezd' and self.archive:
            return str(self.archive)
        if path.startswith('/local-game/') and self.archive:
            name = path.split('?')[0].removeprefix('/local-game/')
            for video in self.archive.parent.iterdir():
                if video.is_file() and video.suffix.lower() == '.avi' and video.name.lower() == name.lower():
                    return str(video)
        return super().translate_path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parents[1] / 'build/web/game')
    parser.add_argument('--archive', type=Path, help='Optional local QUEST.ezd for development')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if args.archive:
        Handler.archive = args.archive.resolve(strict=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(args.directory.resolve())))
    print(f'http://127.0.0.1:{args.port}/game.html', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

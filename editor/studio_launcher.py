"""TitbitStudio.exe: one double-click starts the scene editor.

Finds QUEST.ezd (remembered choice, next to the exe, the game folder, common
install places), asks once with a file dialog if none is found, starts the
editor server on a free local port, opens the browser and shows a small window
with "Open in browser" / "Stop". Projects are saved next to the exe in
TitbitStudio-projects/. The archive is only read.
"""
import json, os, pathlib, socket, sys, threading, webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox

APP = 'Титбит Studio'
# a windowed exe has no console: the HTTP server's request log would crash on
# sys.stderr = None, so give it a log file next to the exe instead
if sys.stderr is None or sys.stdout is None:
    try:
        _log = open(pathlib.Path(sys.executable).with_name('TitbitStudio.log'), 'a', encoding='utf-8', buffering=1)
    except OSError:
        _log = open(os.devnull, 'w')
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log
HERE = pathlib.Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
CONFIG = HERE/'TitbitStudio.json'
CANDIDATES = [HERE, HERE.parent, HERE/'game', HERE.parent/'build/modern-portable',
              HERE.parent/'build/modern', pathlib.Path.cwd(),
              pathlib.Path(r'C:\Games\Titbit'), pathlib.Path(r'C:\Games\Ядерный Титбит'),
              pathlib.Path(r'C:\Program Files (x86)\Buka\Titbit'), pathlib.Path(r'C:\Program Files\Buka\Titbit'),
              pathlib.Path(r'C:\Program Files (x86)\Бука\Ядерный Титбит'), pathlib.Path(r'C:\Program Files\Бука\Ядерный Титбит')]


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError:
        pass


def find_archive(cfg):
    remembered = cfg.get('archive')
    if remembered and pathlib.Path(remembered).is_file():
        return pathlib.Path(remembered)
    for d in CANDIDATES:
        for name in ('QUEST.ezd', 'quest.ezd'):
            if (d/name).is_file():
                return d/name
    for letter in 'DEFGHIJ':                    # the game CD in a drive
        p = pathlib.Path(f'{letter}:/QUEST.ezd')
        try:
            if p.is_file():
                return p
        except OSError:
            pass
    return None


def free_port(start=4318):
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise OSError('no free local port')


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=pathlib.Path,help='Original QUEST.ezd to open')
    args=parser.parse_args()
    root = tk.Tk()
    root.title(APP)
    root.resizable(False, False)
    cfg = load_config()
    archive = args.archive.resolve() if args.archive and args.archive.is_file() else find_archive(cfg)
    if archive is None:
        messagebox.showinfo(APP, 'Укажите файл QUEST.ezd из папки игры «Ядерный Титбит».\n'
                                 'Файл только читается и не изменяется.')
        chosen = filedialog.askopenfilename(title='Где QUEST.ezd?', filetypes=[('Архив игры', 'QUEST.ezd'), ('Все файлы', '*.*')])
        if not chosen:
            root.destroy()
            return
        archive = pathlib.Path(chosen)
    cfg['archive'] = str(archive)
    save_config(cfg)

    projects = HERE/'TitbitStudio-projects'
    projects.mkdir(exist_ok=True)
    os.environ['TITBIT_STUDIO_PROJECTS'] = str(projects)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import server                                  # after the env var: PROJECT is read at import
    try:
        app = server.Application(archive)
    except Exception as e:                         # wrong / damaged file: forget it, explain
        cfg.pop('archive', None)
        save_config(cfg)
        messagebox.showerror(APP, f'Не удалось открыть {archive}:\n{e}\n\nЗапустите ещё раз и выберите другой файл.')
        root.destroy()
        return
    port = free_port()
    httpd = server.ThreadingHTTPServer(('127.0.0.1', port), server.Handler)
    httpd.app = app
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{port}/'
    if os.environ.get('TITBIT_STUDIO_NO_BROWSER') != '1':
        webbrowser.open(url)

    tk.Label(root, text=f'{APP} работает', font=('Segoe UI', 12, 'bold')).pack(padx=24, pady=(18, 4))
    tk.Label(root, text=f'{url}\n{len(app.scenes)} сцен · {archive.name}\nПроекты: {projects}', justify='center').pack(padx=24)
    row = tk.Frame(root)
    row.pack(pady=16)
    tk.Button(row, text='Открыть в браузере', width=18, command=lambda: webbrowser.open(url)).pack(side='left', padx=6)

    def change_archive():
        cfg.pop('archive', None)
        save_config(cfg)
        messagebox.showinfo(APP, 'При следующем запуске будет предложено выбрать QUEST.ezd.')

    tk.Button(row, text='Другой QUEST.ezd…', width=18, command=change_archive).pack(side='left', padx=6)

    def stop():
        httpd.shutdown()
        root.destroy()

    tk.Button(root, text='Закрыть редактор', width=20, command=stop).pack(pady=(0, 18))
    root.protocol('WM_DELETE_WINDOW', stop)
    root.mainloop()


if __name__ == '__main__':
    main()

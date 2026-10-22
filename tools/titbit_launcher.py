"""Nuclear Titbit desktop launcher. Frozen builds need no installed Python."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import titbit_mods as mods
import titbit_assets as assets

BUNDLE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def defaults():
    if os.name == 'nt':
        return BUNDLE, BUNDLE/'TitbitLauncher-data', BUNDLE/'TitbitModern.exe'
    data = Path(os.environ.get('TITBIT_GAME', Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'titbit/game'))
    store = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'titbit/launcher'
    engine = Path(os.environ.get('TITBIT_LINUX_GAME', BUNDLE/'titbit'))
    return data, store, engine


class Launcher:
    def __init__(self, root, data, store, engine):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.store, self.engine = root, Path(store), Path(engine)
        self.events = queue.Queue(); self.cancel = threading.Event()
        self.busy = False; self.playing = False; self.closing = False
        prefs = mods.read_json(self.store/'launcher.json') if (self.store/'launcher.json').is_file() else {}
        self.data = tk.StringVar(value=prefs.get('data', str(data)))
        self.mode = tk.StringVar(value=prefs.get('mode', 'original'))
        self.display = tk.StringVar(value=prefs.get('display', 'fullscreen'))
        self.resolution = tk.StringVar(value=prefs.get('resolution', 'desktop'))
        if os.name != 'nt': self.resolution.set('desktop')
        self.source = tk.StringVar()
        self.status = tk.StringVar(value='Готов к запуску. Оригинальные данные хранятся отдельно от модов.')
        self.modstatus = tk.StringVar(); self.buttons = []; self.pages = {}
        self.bg, self.panel, self.ink, self.muted, self.gold = '#100d09', '#20190f', '#f6e6ba', '#b6a67d', '#ffb000'
        root.title('Ядерный Титбит · Лаунчер'); root.geometry('1000x760'); root.minsize(900, 710)
        self.icon=tk.PhotoImage(width=32,height=32)
        self.icon.put('#ffb000',to=(0,0,32,32));self.icon.put('#1b1004',to=(6,6,26,11));self.icon.put('#1b1004',to=(13,10,19,27))
        root.iconphoto(True,self.icon)
        root.configure(bg=self.bg); root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root); style.theme_use('clam')
        style.configure('.', background=self.bg, foreground=self.ink, font=('Segoe UI', 10))
        style.configure('TFrame', background=self.bg)
        style.configure('TLabel', background=self.bg, foreground=self.ink)
        style.configure('Muted.TLabel', foreground=self.muted)
        style.configure('Title.TLabel', font=('Segoe UI', 24, 'bold'), foreground=self.gold)
        style.configure('Head.TLabel', font=('Segoe UI', 15, 'bold'), foreground=self.gold)
        style.configure('TButton', padding=(15, 10), background='#34281a', foreground=self.ink, borderwidth=0)
        style.map('TButton', background=[('active','#61441b'),('disabled','#211c14')], foreground=[('disabled','#776c56')])
        style.configure('Play.TButton', font=('Segoe UI', 15, 'bold'), background=self.gold, foreground='#100d09', padding=(25,15))
        style.map('Play.TButton', background=[('active','#ffd166'),('disabled','#40341d')])
        style.configure('TRadiobutton', background=self.bg, foreground=self.ink, padding=6)
        style.map('TRadiobutton', background=[('active',self.panel)], indicatorcolor=[('selected',self.gold)])
        style.configure('TEntry', fieldbackground='#292216', foreground=self.ink, insertcolor=self.gold, padding=8)
        style.configure('TCombobox', fieldbackground='#292216', background='#34281a', foreground=self.ink, padding=7)
        style.map('TCombobox', fieldbackground=[('readonly','#292216')], foreground=[('readonly',self.ink)])
        style.configure('Horizontal.TProgressbar', background=self.gold, troughcolor=self.panel, borderwidth=0)
        root.option_add('*TCombobox*Listbox.background', '#292216')
        root.option_add('*TCombobox*Listbox.foreground', self.ink)
        header = tk.Canvas(root, height=144, bg='#291c07', highlightthickness=0)
        header.pack(fill='x'); header.bind('<Configure>', lambda e:self.draw_header(header,e.width))
        body = ttk.Frame(root, padding=(22,18)); body.pack(fill='both',expand=True)
        nav = ttk.Frame(body); nav.pack(side='left',fill='y',padx=(0,25))
        for key, title in [('game','01  ИГРА'),('mods','02  МОДЫ'),('files','03  ФАЙЛЫ ИГРЫ')]:
            ttk.Button(nav,text=title,command=lambda k=key:self.show(k),width=19).pack(fill='x',pady=(0,8))
        ttk.Label(nav,text='VZlab · Бука · 2003\nВосстановленные исходники',style='Muted.TLabel',wraplength=175).pack(side='bottom',anchor='w',pady=10)
        self.content = ttk.Frame(body); self.content.pack(side='left',fill='both',expand=True)
        for key in ('game','mods','files'): self.pages[key] = ttk.Frame(self.content)
        self.make_game(); self.make_mods(); self.make_files(); self.show('game')
        foot = ttk.Frame(root,padding=(22,0,22,15)); foot.pack(fill='x')
        self.progress = ttk.Progressbar(foot,mode='determinate'); self.progress.pack(fill='x',pady=(0,8))
        row = ttk.Frame(foot); row.pack(fill='x')
        ttk.Label(row,textvariable=self.status,wraplength=800,style='Muted.TLabel').pack(side='left')
        self.cancel_button = ttk.Button(row,text='Отмена',command=self.cancel.set,state='disabled')
        self.cancel_button.pack(side='right')
        self.mode.trace_add('write',lambda *_:self.refresh())
        self.refresh(); root.after(80,self.poll)

    def draw_header(self, canvas, width):
        canvas.delete('all')
        for x in range(0,width,32): canvas.create_line(x,0,x,144,fill='#3d2d0c')
        for y in range(0,145,32): canvas.create_line(0,y,width,y,fill='#3d2d0c')
        canvas.create_polygon(0,0,360,0,275,144,0,144,fill='#bd6d06',outline='')
        canvas.create_text(65,68,text='☢',font=('Segoe UI Symbol',76),fill='#1b1004')
        canvas.create_text(155,27,text='ЯДЕРНЫЙ',anchor='nw',font=('Segoe UI',20,'bold'),fill='#160e04')
        canvas.create_text(153,57,text='ТИТБИТ',anchor='nw',font=('Segoe UI',30,'bold'),fill='#160e04')
        canvas.create_text(width-28,42,text='КОНТРОЛЬ ЗАПУСКА',anchor='ne',font=('Consolas',19,'bold'),fill='#ffd160')
        canvas.create_text(width-28,77,text='ОРИГИНАЛ  /  МОДИФИКАЦИИ  /  РЕСУРСЫ',anchor='ne',font=('Consolas',11),fill='#c1a357')
        canvas.create_line(0,142,width,142,fill=self.gold,width=2)

    def button(self,parent,text,command,style=None):
        button = self.ttk.Button(parent,text=text,command=command,**({'style':style} if style else {}))
        self.buttons.append(button); return button

    def label(self,parent,text,style='TLabel',**kw):
        item = self.ttk.Label(parent,text=text,style=style,wraplength=640,**kw); item.pack(anchor='w',pady=(0,10)); return item

    def make_game(self):
        p = self.pages['game']; self.label(p,'Запуск игры','Title.TLabel')
        self.label(p,'Выберите оригинальную графику или установленный мод.','Muted.TLabel')
        for value, title in [('original','Оригинал · 4:3'),('16x9','Widescreen · 16:9'),('16x10','Widescreen · 16:10')]:
            self.ttk.Radiobutton(p,text=title,variable=self.mode,value=value).pack(anchor='w')
        row = self.ttk.Frame(p); row.pack(fill='x',pady=(18,5))
        resolutions=['desktop','1024x768','1230x768','1366x768','1600x900','1920x1080','1920x1200','2560x1440'] if os.name=='nt' else ['desktop']
        for label,var,values in [('Экран',self.display,['fullscreen','windowed']),('Разрешение',self.resolution,resolutions)]:
            cell=self.ttk.Frame(row);cell.pack(side='left',padx=(0,20))
            self.ttk.Label(cell,text=label,style='Muted.TLabel').pack(anchor='w',pady=(0,5))
            self.ttk.Combobox(cell,textvariable=var,values=values,state='readonly',width=22).pack()
        self.label(p,'fullscreen — безрамочный экран · windowed — окно\n'+
                   ('Linux: разрешение экрана системное; размер окна можно менять мышью.\n' if os.name!='nt' else '')+
                   'Сохранения каждого режима независимы. При первом запуске копируются ваши существующие .sav.','Muted.TLabel')
        self.play_button=self.button(p,'▶  ИГРАТЬ',self.play,'Play.TButton');self.play_button.pack(anchor='w',pady=(8,10))
        self.ttk.Label(p,textvariable=self.modstatus,foreground=self.gold,wraplength=630).pack(anchor='w')
        self.button(p,'Открыть Титбит Studio',self.studio).pack(anchor='w',pady=(15,0))

    def make_mods(self):
        p=self.pages['mods']; self.label(p,'Модификации','Title.TLabel')
        self.label(p,'WIDESCREEN  /  0.1.0','Head.TLabel')
        self.label(p,'Дорисованные локации и меню, расширенный обзор, курсор и переходы у краёв экрана. 16:9 и 16:10. Три согласованные сцены подвала остаются в 4:3.')
        record=mods.catalog()
        self.label(p,f'Загрузка: {record["size"]/1024/1024:.1f} МиБ · 39 изображений\nИсточник: GitHub Releases · offx366/titbit-modern\nПакет: SHA256 {record["sha256"][:20]}…','Muted.TLabel')
        self.label(p,'Установка проверяет локальную версию игры, скачивает готовые дорисованные фоны и собирает отдельный QUEST.ezd на вашем компьютере. Музыка и видео берутся из вашей копии. Интернет нужен только для загрузки.','Muted.TLabel')
        self.ttk.Label(p,text='Формат установки',style='Muted.TLabel').pack(anchor='w')
        self.ratio=self.tk.StringVar(value='16x9')
        self.ttk.Combobox(p,textvariable=self.ratio,values=['16x9','16x10'],state='readonly',width=16).pack(anchor='w',pady=(5,12))
        actions=self.ttk.Frame(p);actions.pack(anchor='w')
        self.button(actions,'Скачать и установить',lambda:self.install_mod(None)).pack(side='left',padx=(0,8))
        self.button(actions,'Из .titbitmod…',self.local_mod).pack(side='left')
        self.button(p,'Удалить мод выбранного формата',self.remove_mod).pack(anchor='w',pady=(12,10))
        self.label(p,'Оригинальный архив сохраняется. Удаление мода сохраняет ваши .sav в папке резервных профилей лаунчера. Пакет можно сохранить для офлайн-установки.','Muted.TLabel')

    def make_files(self):
        p=self.pages['files'];self.label(p,'Оригинальные ресурсы','Title.TLabel')
        self.label(p,'Нужна ваша копия игры: папка, диск, ISO / IMG / CUE / CCD. Подключать образ и запускать старый установщик не требуется.','Muted.TLabel')
        self.label(p,'Папка файлов игры')
        self.ttk.Entry(p,textvariable=self.data).pack(fill='x',pady=(0,8))
        self.button(p,'Выбрать папку данных…',self.choose_data).pack(anchor='w')
        self.label(p,'Источник для импорта')
        self.ttk.Entry(p,textvariable=self.source).pack(fill='x',pady=(0,8))
        actions=self.ttk.Frame(p);actions.pack(anchor='w')
        self.button(actions,'Папка / диск…',lambda:self.choose_source(False)).pack(side='left',padx=(0,8))
        self.button(actions,'Образ…',lambda:self.choose_source(True)).pack(side='left')
        actions=self.ttk.Frame(p);actions.pack(anchor='w',pady=12)
        self.button(actions,'Импортировать',self.import_data).pack(side='left',padx=(0,8))
        self.button(actions,'Проверить SHA256',self.verify_data).pack(side='left')
        self.label(p,'Проверка подтверждает совместимость файлов с версией 1.00. Содержимое вашей копии никуда не отправляется.','Muted.TLabel')

    def show(self,key):
        for p in self.pages.values(): p.pack_forget()
        self.pages[key].pack(fill='both',expand=True)

    def refresh(self):
        state=[]
        for ratio in ('16x9','16x10'):
            state.append(ratio.replace('x',':')+(' установлен' if mods.installed(self.store,ratio) else ' не установлен'))
        self.modstatus.set('Widescreen: '+' · '.join(state))

    def choose_data(self):
        from tkinter import filedialog
        path=filedialog.askdirectory(parent=self.root,title='Папка оригинальных файлов игры')
        if path:self.data.set(path)

    def choose_source(self,image):
        from tkinter import filedialog
        path=(filedialog.askopenfilename(parent=self.root,title='Образ диска',filetypes=[('Образы','*.iso *.img *.cue *.ccd'),('Все файлы','*')])
              if image else filedialog.askdirectory(parent=self.root,title='Ваша копия игры'))
        if path:self.source.set(path)

    def report(self,name,done,total):self.events.put(('progress',(name,done,total)))

    def persist(self):
        mods.write_json(self.store/'launcher.json',dict(data=self.data.get(),mode=self.mode.get(),display=self.display.get(),resolution=self.resolution.get()))

    def task(self, action, playing=False):
        if self.busy:return
        self.persist();self.busy=True;self.playing=playing;self.cancel.clear()
        self.status.set('Подготовка…');self.progress.configure(mode='indeterminate');self.progress.start()
        for b in self.buttons:b.configure(state='disabled')
        self.cancel_button.configure(state='disabled' if playing else 'normal')
        def work():
            try:
                with mods.locked(self.store):result=action()
                self.events.put(('done',str(result)))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def verify_data(self):
        base=self.data.get()
        self.task(lambda:mods.check_base(base,self.report,self.cancel) and 'Проверены все 19 файлов игры.')

    def import_data(self):
        source,base=self.source.get(),self.data.get()
        def work():
            plan=assets.inspect_source(source)
            try: assets.install_assets(plan,base,self.report,self.cancel)
            finally:plan.close()
            return 'Импорт завершён. Все 19 файлов проверены.'
        self.task(work)

    def local_mod(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(parent=self.root,title='Пакет мода',filetypes=[('Моды Титбита','*.titbitmod')])
        if path:self.install_mod(Path(path))

    def install_mod(self,package):
        base,ratio=self.data.get(),self.ratio.get()
        def work():
            if mods.installed(self.store,ratio):raise ValueError('Этот формат уже установлен.')
            mods.check_base(base,self.report,self.cancel)
            path=package or mods.download(mods.catalog(),self.store/'downloads',self.report,self.cancel)
            mods.install_verified(path,base,self.store,ratio,self.report,self.cancel)
            return 'Мод установлен: '+ratio.replace('x',':')+'. Выберите его на вкладке «Игра».'
        self.task(work)

    def remove_mod(self):
        from tkinter import messagebox
        ratio=self.ratio.get()
        if messagebox.askyesno('Удалить Widescreen '+ratio.replace('x',':')+'?', 'Будут удалены только файлы мода. Сохранения останутся в резервном профиле.',parent=self.root):
            self.task(lambda:mods.remove(self.store,ratio) and 'Мод удалён. Сохранения сохранены.')

    def play(self):
        base,mode,display,resolution=self.data.get(),self.mode.get(),self.display.get(),self.resolution.get()
        def work():
            launch=mods.prepare_launch(base,self.store,self.engine,mode,display,resolution)
            self.report('Игра запущена. Лаунчер дождётся выхода; профиль занят.',0,0)
            with (Path(launch['profile'])/'launcher-game.log').open('ab') as log:
                process=subprocess.Popen(launch['argv'],cwd=launch['cwd'],env=launch['env'],stdout=log,stderr=log)
                code=process.wait()
            if code:raise ValueError(f'Игра завершилась с кодом {code}. Подробности: {launch["profile"]}/launcher-game.log')
            return 'Игра закрыта. Сохранения остались в выбранном профиле.'
        self.task(work,playing=True)

    def studio(self):
        base=self.data.get()
        def work():
            if os.name=='nt':
                exe=BUNDLE/'TitbitStudio.exe'
                if not exe.is_file():raise ValueError('TitbitStudio.exe должен лежать рядом с лаунчером')
                command=[str(exe),'--archive',str(Path(base)/'QUEST.ezd')]
            else:
                command=[sys.executable,'studio','--archive',str(Path(base)/'QUEST.ezd')] if getattr(sys,'frozen',False) else [sys.executable,str(BUNDLE/'editor/start_studio.py'),'--archive',str(Path(base)/'QUEST.ezd')]
            subprocess.Popen(command,cwd=BUNDLE)
            return 'Studio запущена для оригинальной копии игры.'
        self.task(work)

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    name,done,total=value;self.status.set(name)
                    if total:
                        self.progress.stop();self.progress.configure(mode='determinate',maximum=total,value=done)
                    else:
                        self.progress.configure(mode='indeterminate');self.progress.start()
                else:
                    self.busy=False;self.playing=False;self.progress.stop();self.progress.configure(mode='determinate',value=0)
                    self.status.set(('Ошибка: ' if kind=='error' else '')+value)
                    for b in self.buttons:b.configure(state='normal')
                    self.cancel_button.configure(state='disabled');self.refresh()
                    if self.closing:self.root.destroy();return
        except queue.Empty:pass
        self.root.after(80,self.poll)

    def close(self):
        if self.busy:
            self.closing=True
            if self.playing:self.root.withdraw()
            else:self.cancel.set();self.status.set('Отмена. Ожидаю безопасного завершения текущего этапа…')
            return
        self.persist();self.root.destroy()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    data,store,engine=defaults()
    p.add_argument('--data',type=Path,default=data);p.add_argument('--store',type=Path,default=store);p.add_argument('--engine',type=Path,default=engine)
    p.add_argument('--check',action='store_true',help='Check local original data without opening a window')
    p.add_argument('--install-mod',type=Path,help='Install offline mod without opening a window')
    p.add_argument('--ratio',choices=('16x9','16x10'),default='16x9')
    p.add_argument('--report',type=Path,help='Save CLI result as JSON')
    a=p.parse_args(argv)
    if a.check or a.install_mod:
        code=0
        try:
            with mods.locked(a.store):
                result=(dict(installed=str(mods.install(a.install_mod,a.data,a.store,a.ratio))) if a.install_mod else mods.check_base(a.data))
        except Exception as exc:result={'error':str(exc)};code=1
        if a.report:mods.write_json(a.report,result)
        if sys.stdout is not None:print(json.dumps(result,ensure_ascii=False))
        return code
    import tkinter as tk
    root=tk.Tk();Launcher(root,a.data,a.store,a.engine);root.mainloop();return 0


if __name__=='__main__':raise SystemExit(main())

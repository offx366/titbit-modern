"""Single entry point for game import, launch, mods and Studio."""
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
import titbit_profiles as profiles
import titbit_assets as assets

BUNDLE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
if BUNDLE.name == 'bin' and getattr(sys, 'frozen', False):
    BUNDLE = BUNDLE.parent


def defaults():
    if os.name == 'nt':
        legacy = BUNDLE/'TitbitLauncher-data'
        store = legacy if legacy.is_dir() else BUNDLE/'data'
        data = BUNDLE if (BUNDLE/'QUEST.ezd').is_file() else store/'game'
        engine = BUNDLE/'bin/TitbitGame.exe'
        return data, store, engine if engine.is_file() else BUNDLE/'TitbitModern.exe'
    data = Path(os.environ.get('TITBIT_GAME', Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'titbit/game'))
    store = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'titbit/launcher'
    engine = Path(os.environ.get('TITBIT_LINUX_GAME', BUNDLE/'bin/titbit-game'))
    return data, store, engine if engine.is_file() else BUNDLE/'titbit'


class Launcher:
    def __init__(self, root, data, store, engine):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.store, self.engine = root, Path(store), Path(engine)
        self.events = queue.Queue(); self.cancel = threading.Event()
        self.busy = False; self.playing = False; self.closing = False
        prefs = profiles.preferences(store, data)
        self.data = tk.StringVar(value=prefs['data'])
        self.enabled = {key:tk.BooleanVar(value=key in prefs['enabledMods']) for key in mods.all_mods()}
        self.unknown = [key for key in prefs['enabledMods'] if key not in self.enabled]
        self.mod_order = prefs['enabledMods']
        self.display = tk.BooleanVar(value=prefs['display'] == 'fullscreen')
        self.resolution = tk.StringVar(value=prefs['resolution'] if os.name == 'nt' else 'desktop')
        self.source = tk.StringVar()
        self.status = tk.StringVar(value='Готово' if (Path(self.data.get())/'QUEST.ezd').is_file() else 'Выберите вашу копию игры')
        self.modstatus = tk.StringVar(); self.buttons = []; self.fields = []; self.pages = {}; self.modrows = {}
        self.bg, self.panel, self.ink, self.muted, self.gold = '#100d09', '#20190f', '#f6e6ba', '#b6a67d', '#ffb000'
        root.title('Ядерный Титбит'); root.geometry('840x610'); root.minsize(800, 580)
        self.icon=tk.PhotoImage(width=32,height=32)
        self.icon.put('#ffb000',to=(0,0,32,32));self.icon.put('#1b1004',to=(6,6,26,11));self.icon.put('#1b1004',to=(13,10,19,27))
        root.iconphoto(True,self.icon)
        root.configure(bg=self.bg); root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root); style.theme_use('clam')
        style.configure('.', background=self.bg, foreground=self.ink, font=('Segoe UI', 11))
        style.configure('TFrame', background=self.bg)
        style.configure('TLabel', background=self.bg, foreground=self.ink)
        style.configure('Muted.TLabel', foreground=self.muted)
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'), foreground=self.gold)
        style.configure('Head.TLabel', font=('Segoe UI', 15, 'bold'))
        style.configure('TButton', padding=(16, 10), background='#34281a', foreground=self.ink, borderwidth=0)
        style.map('TButton', background=[('active','#61441b'),('disabled','#211c14')], foreground=[('disabled','#776c56')])
        style.configure('Play.TButton', font=('Segoe UI', 20, 'bold'), background=self.gold, foreground='#100d09', padding=(50,18))
        style.map('Play.TButton', background=[('active','#ffd166'),('disabled','#40341d')])
        style.configure('TCheckbutton', background=self.bg, foreground=self.ink, padding=8)
        style.map('TCheckbutton', background=[('active',self.panel)], indicatorcolor=[('selected',self.gold)])
        style.configure('TEntry', fieldbackground='#292216', foreground=self.ink, insertcolor=self.gold, padding=8)
        style.configure('TCombobox', fieldbackground='#292216', background='#34281a', foreground=self.ink, padding=7)
        style.map('TCombobox', fieldbackground=[('readonly','#292216')], foreground=[('readonly',self.ink)])
        style.configure('Horizontal.TProgressbar', background=self.gold, troughcolor=self.panel, borderwidth=0)
        root.option_add('*TCombobox*Listbox.background', '#292216')
        root.option_add('*TCombobox*Listbox.foreground', self.ink)
        header = tk.Canvas(root, height=100, bg='#291c07', highlightthickness=0)
        header.pack(fill='x'); header.bind('<Configure>', lambda e:self.draw_header(header,e.width))
        body = ttk.Frame(root, padding=(28,18)); body.pack(fill='both',expand=True)
        nav = ttk.Frame(body); nav.pack(fill='x',pady=(0,22))
        for key, title in [('game','Игра'),('mods','Моды'),('settings','Настройки'),('files','Файлы игры')]:
            ttk.Button(nav,text=title,command=lambda k=key:self.show(k)).pack(side='left',padx=(0,8))
        self.content = ttk.Frame(body); self.content.pack(fill='both',expand=True)
        for key in ('game','mods','settings','files'): self.pages[key] = ttk.Frame(self.content)
        self.make_game(); self.make_mods(); self.make_settings(); self.make_files()
        self.show('game' if (Path(self.data.get())/'QUEST.ezd').is_file() else 'files')
        foot = ttk.Frame(root,padding=(28,0,28,20)); foot.pack(fill='x')
        self.progress = ttk.Progressbar(foot,mode='determinate'); self.progress.pack(fill='x',pady=(0,8))
        row = ttk.Frame(foot); row.pack(fill='x')
        ttk.Label(row,textvariable=self.status,wraplength=640,style='Muted.TLabel').pack(side='left')
        self.cancel_button = ttk.Button(row,text='Отмена',command=self.cancel.set,state='disabled')
        self.cancel_button.pack(side='right')
        self.refresh(); root.after(80,self.poll)

    def draw_header(self, canvas, width):
        canvas.delete('all')
        for x in range(0,width,32): canvas.create_line(x,0,x,100,fill='#3d2d0c')
        for y in range(0,101,32): canvas.create_line(0,y,width,y,fill='#3d2d0c')
        canvas.create_polygon(0,0,365,0,305,100,0,100,fill='#bd6d06',outline='')
        canvas.create_text(50,47,text='☢',font=('Segoe UI Symbol',53),fill='#1b1004')
        canvas.create_text(106,18,text='ЯДЕРНЫЙ',anchor='nw',font=('Segoe UI',17,'bold'),fill='#160e04')
        canvas.create_text(104,42,text='ТИТБИТ',anchor='nw',font=('Segoe UI',27,'bold'),fill='#160e04')
        canvas.create_text(width-28,45,text='VZlab / Бука / 2003',anchor='ne',font=('Consolas',12),fill='#c1a357')
        canvas.create_line(0,98,width,98,fill=self.gold,width=2)

    def button(self,parent,text,command,style=None):
        button = self.ttk.Button(parent,text=text,command=command,**({'style':style} if style else {}))
        self.buttons.append(button); return button

    def label(self,parent,text,style='TLabel',**kw):
        item = self.ttk.Label(parent,text=text,style=style,wraplength=735,**kw); item.pack(anchor='w',pady=(0,12)); return item

    def make_game(self):
        p=self.pages['game'];self.label(p,'Ядерный Титбит','Title.TLabel')
        self.ttk.Label(p,textvariable=self.modstatus,style='Muted.TLabel').pack(anchor='w',pady=(0,25))
        self.play_button=self.button(p,'▶  Играть',self.play,'Play.TButton');self.play_button.pack(anchor='w')
        self.button(p,'Открыть Studio',self.studio).pack(anchor='w',pady=(22,0))

    def make_mods(self):
        p=self.pages['mods'];self.label(p,'Моды','Title.TLabel')
        for key, record in mods.all_mods().items():
            row=self.ttk.Frame(p);row.pack(fill='x',pady=(0,18))
            self.ttk.Label(row,text=record.get('name',key),style='Head.TLabel').grid(row=0,column=0,sticky='w')
            self.ttk.Label(row,text=record.get('summary',''),style='Muted.TLabel',wraplength=520).grid(row=1,column=0,sticky='w',pady=(8,12))
            state=self.tk.StringVar()
            self.ttk.Label(row,textvariable=state,style='Muted.TLabel').grid(row=2,column=0,sticky='w')
            toggle=self.ttk.Checkbutton(row,text='Включён',variable=self.enabled[key],command=self.toggle_mod)
            toggle.grid(row=0,column=1,sticky='e');self.fields.append((toggle,'normal'))
            actions=self.ttk.Frame(row);actions.grid(row=1,column=1,rowspan=2,sticky='ne',padx=(16,0))
            install=self.button(actions,'Установить',lambda k=key:self.install_mod(None,k));install.pack(pady=(0,6))
            remove=self.button(actions,'Удалить',lambda k=key:self.remove_mod(k));remove.pack()
            row.columnconfigure(0,weight=1)
            self.modrows[key]=(state,toggle,install,remove)
        self.button(p,'Установить из файла…',self.local_mod).pack(anchor='w',pady=(8,0))

    def make_settings(self):
        p=self.pages['settings'];self.label(p,'Настройки','Title.TLabel')
        toggle=self.ttk.Checkbutton(p,text='Полный экран',variable=self.display)
        toggle.pack(anchor='w',pady=(0,18));self.fields.append((toggle,'normal'))
        if os.name=='nt':
            self.label(p,'Разрешение')
            values=['Автоматически','1024x768','1366x768','1600x900','1920x1080','1920x1200','2560x1440']
            self.resolution_label=self.tk.StringVar(value='Автоматически' if self.resolution.get()=='desktop' else self.resolution.get())
            box=self.ttk.Combobox(p,textvariable=self.resolution_label,values=values,state='readonly',width=24)
            box.pack(anchor='w');self.fields.append((box,'readonly'))
            box.bind('<<ComboboxSelected>>',lambda _:self.resolution.set('desktop' if self.resolution_label.get()=='Автоматически' else self.resolution_label.get()))
        self.label(p,'Alt+Enter / F11 — переключить полный экран в игре.','Muted.TLabel')

    def make_files(self):
        p=self.pages['files'];self.label(p,'Файлы игры','Title.TLabel')
        self.label(p,'Укажите установленную игру, диск или образ. Импорт выполняется здесь же.','Muted.TLabel')
        row=self.ttk.Frame(p);row.pack(anchor='w',pady=(6,20))
        self.button(row,'Папка / диск…',lambda:self.choose_source(False)).pack(side='left',padx=(0,10))
        self.button(row,'ISO / IMG…',lambda:self.choose_source(True)).pack(side='left')
        self.ttk.Label(p,textvariable=self.data,style='Muted.TLabel',wraplength=730).pack(anchor='w',pady=(0,12))
        row=self.ttk.Frame(p);row.pack(anchor='w')
        self.button(row,'Указать готовую папку…',self.choose_data).pack(side='left',padx=(0,10))
        self.button(row,'Проверить файлы',self.verify_data).pack(side='left')

    def show(self,key):
        for p in self.pages.values():p.pack_forget()
        self.pages[key].pack(fill='both',expand=True)

    def enabled_mods(self):
        selected = [key for key,var in self.enabled.items() if var.get()]+self.unknown
        return [k for k in self.mod_order if k in selected]+[k for k in selected if k not in self.mod_order]

    def selected_ratio(self):
        width,height=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        if os.name=='nt':
            # Use the monitor containing this window, including different DPI scales.
            import ctypes
            from ctypes import wintypes
            class MonitorInfo(ctypes.Structure):
                _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
            user=ctypes.windll.user32
            user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user.MonitorFromWindow.restype=wintypes.HANDLE
            user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
            info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
            if user.GetMonitorInfoW(user.MonitorFromWindow(self.root.winfo_id(),2),ctypes.byref(info)):
                width,height=info.rcMonitor.right-info.rcMonitor.left,info.rcMonitor.bottom-info.rcMonitor.top
        return profiles.automatic_ratio(width,height,self.resolution.get())

    def refresh(self):
        self.modstatus.set('Моды: '+', '.join(mods.all_mods().get(k,{}).get('name',k) for k in self.enabled_mods()) if self.enabled_mods() else 'Оригинальная версия')
        for key,(state,toggle,install,remove) in self.modrows.items():
            ready=profiles.has_widescreen(self.store) if key=='widescreen' else False
            state.set('Установлен' if ready else 'Не установлен')
            toggle.configure(state='normal' if ready and not self.busy else 'disabled')
            install.configure(state='normal' if not ready and not self.busy else 'disabled')
            remove.configure(state='normal' if ready and not self.busy else 'disabled')

    def toggle_mod(self):
        self.persist();self.refresh()

    def choose_data(self):
        from tkinter import filedialog
        path=filedialog.askdirectory(parent=self.root,title='Папка с QUEST.ezd и видео игры')
        if path:self.data.set(path);self.verify_data()

    def choose_source(self,image):
        from tkinter import filedialog
        path=(filedialog.askopenfilename(parent=self.root,title='Образ диска',filetypes=[('Образы','*.iso *.img *.cue *.ccd'),('Все файлы','*')])
              if image else filedialog.askdirectory(parent=self.root,title='Папка игры или диск'))
        if path:self.source.set(path);self.import_data()

    def report(self,name,done,total):self.events.put(('progress',(name,done,total)))

    def persist(self):
        mods.write_json(self.store/'launcher.json',dict(schema=2,data=self.data.get(),enabledMods=self.enabled_mods(),display='fullscreen' if self.display.get() else 'windowed',resolution=self.resolution.get()))

    def task(self, action, playing=False):
        if self.busy:return
        self.persist();self.busy=True;self.playing=playing;self.cancel.clear()
        self.status.set('Подготовка…');self.progress.configure(mode='indeterminate');self.progress.start()
        for b in self.buttons:b.configure(state='disabled')
        for field,_ in self.fields:field.configure(state='disabled')
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
            try:assets.install_assets(plan,base,self.report,self.cancel)
            finally:plan.close()
            self.events.put(('imported',None))
            return 'Игра готова к запуску'
        self.task(work)

    def local_mod(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(parent=self.root,title='Пакет мода',filetypes=[('Моды Титбита','*.titbitmod')])
        if path:self.install_mod(Path(path))

    def install_mod(self,package,key='widescreen'):
        if not (Path(self.data.get())/'QUEST.ezd').is_file():
            self.show('files');self.status.set('Сначала добавьте файлы игры');return
        base,ratio=self.data.get(),self.selected_ratio()
        def work():
            if key!='widescreen':raise ValueError('Обновите лаунчер для установки этого мода')
            profiles.install_widescreen(base,self.store,ratio,package,self.report,self.cancel)
            self.events.put(('enabled',(key,True)))
            return 'Widescreen установлен и включён'
        self.task(work)

    def remove_mod(self,key='widescreen'):
        from tkinter import messagebox
        if messagebox.askyesno('Удалить Widescreen?', 'Сохранения останутся. Мод можно установить повторно.',parent=self.root):
            def work():
                profiles.remove_widescreen(self.store)
                self.events.put(('enabled',(key,False)))
                return 'Мод удалён. Сохранения сохранены'
            self.task(work)

    def play(self):
        if not (Path(self.data.get())/'QUEST.ezd').is_file():
            self.show('files');self.status.set('Сначала добавьте файлы игры');return
        base,enabled,ratio=self.data.get(),self.enabled_mods(),self.selected_ratio()
        display,resolution='fullscreen' if self.display.get() else 'windowed',self.resolution.get()
        def work():
            launch=profiles.prepare(base,self.store,self.engine,enabled,ratio,display,resolution,self.report,self.cancel)
            self.report('Игра запущена',0,0)
            with (Path(launch['profile'])/'launcher-game.log').open('ab') as log:
                process=subprocess.Popen(launch['argv'],cwd=launch['cwd'],env=launch['env'],stdout=log,stderr=log)
                code=process.wait()
            if code:raise ValueError(f'Игра завершилась с кодом {code}. Журнал: {launch["profile"]}/launcher-game.log')
            return 'Игра закрыта'
        self.task(work,playing=True)

    def studio(self):
        base=self.data.get()
        def work():
            if os.name=='nt':
                exe=BUNDLE/'bin/TitbitStudio.exe'
                if not exe.is_file():exe=BUNDLE/'TitbitStudio.exe'
                if not exe.is_file():raise ValueError('Не найдена Studio в комплекте игры')
                command=[str(exe),'--archive',str(Path(base)/'QUEST.ezd')]
            else:
                command=[sys.executable,'studio','--archive',str(Path(base)/'QUEST.ezd')] if getattr(sys,'frozen',False) else [sys.executable,str(BUNDLE/'editor/start_studio.py'),'--archive',str(Path(base)/'QUEST.ezd')]
            subprocess.Popen(command,cwd=BUNDLE)
            return 'Studio запущена'
        self.task(work)

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='enabled':
                    key,enabled=value;self.enabled[key].set(enabled);self.persist();continue
                if kind=='imported':self.show('game');continue
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
                    for field,state in self.fields:field.configure(state=state)
                    self.cancel_button.configure(state='disabled');self.refresh()
                    if self.closing:self.root.destroy();return
        except queue.Empty:pass
        self.root.after(80,self.poll)

    def close(self):
        if self.busy:
            self.closing=True
            if self.playing:self.root.withdraw()
            else:self.cancel.set();self.status.set('Отмена…')
            return
        self.persist();self.root.destroy()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    data,store,engine=defaults()
    p.add_argument('--data',type=Path,default=data);p.add_argument('--store',type=Path,default=store);p.add_argument('--engine',type=Path,default=engine)
    p.add_argument('--check',action='store_true',help='Check local original data without opening a window')
    p.add_argument('--install-mod',type=Path,help='Install offline mod without opening a window')
    p.add_argument('--download-mod',action='store_true',help='Verify original files, request private download and install')
    p.add_argument('--source',type=Path,help='Import your ISO/disc/folder into --data before --download-mod')
    p.add_argument('--ratio',choices=('16x9','16x10'),default='16x9',help=argparse.SUPPRESS)
    p.add_argument('--report',type=Path,help='Save CLI result as JSON')
    a=p.parse_args(argv)
    if a.check or a.install_mod or a.download_mod:
        code=0
        try:
            with mods.locked(a.store):
                if a.download_mod or a.install_mod:
                    if a.source:
                        plan=assets.inspect_source(a.source)
                        try:assets.install_assets(plan,a.data)
                        finally:plan.close()
                    result=dict(installed=str(profiles.install_widescreen(a.data,a.store,a.ratio,a.install_mod)))
                else:result=mods.check_base(a.data)
        except Exception as exc:result={'error':str(exc)};code=1
        if a.report:mods.write_json(a.report,result)
        if sys.stdout is not None:print(json.dumps(result,ensure_ascii=False))
        return code
    import tkinter as tk
    root=tk.Tk();Launcher(root,a.data,a.store,a.engine);root.mainloop();return 0


if __name__=='__main__':raise SystemExit(main())

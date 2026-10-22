"""Exercise the actual launcher on a private Windows desktop; never starts game."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_setup_gui_hidden import assert_hidden_desktop,screenshot
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from titbit_launcher import Launcher


def main():
    p=argparse.ArgumentParser();p.add_argument('--desktop',required=True);p.add_argument('--data',required=True)
    p.add_argument('--store',required=True);p.add_argument('--engine',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();assert_hidden_desktop(a.desktop)
    import tkinter as tk
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    root=tk.Tk();app=Launcher(root,a.data,a.store,a.engine)
    result={'desktop':a.desktop,'screenshots':[]};stage=0;start=time.monotonic()
    def step():
        nonlocal stage
        try:
            if time.monotonic()-start>40:raise RuntimeError('GUI verification timed out')
            if stage<3:
                page=['game','mods','files'][stage];app.show(page);root.update()
                screenshot(root,out/(page+'.bmp'));result['screenshots'].append(page);stage+=1
            elif stage==3:
                app.verify_data();stage+=1
            elif not app.busy:
                result['status']=app.status.get()
                if not result['status'].startswith('Проверены все 19'):raise RuntimeError(result['status'])
                result['ok']=True;(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                root.destroy();return
            root.after(300,step)
        except Exception as exc:
            result.update(ok=False,error=repr(exc));(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');root.destroy()
    root.after(400,step);root.mainloop()


if __name__=='__main__':main()

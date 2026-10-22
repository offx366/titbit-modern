#!/usr/bin/env python3
"""Generate local Playwright MCP checks from a user's QUEST.ezd (no asset copy).

Run setup.js with browser_run_code_unsafe, then run batch.js repeatedly. The
Playwright page holds results in page.titbitQa; report.js returns the JSON report.
Each scene starts in a fresh engine, using its original incoming location where
available. This is a scene smoke test, not a complete puzzle playthrough.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'editor'))
from formats import Archive


def prepare(archive, out):
    archive = Archive(archive)
    base = (Path(__file__).resolve().parents[1]/'web/browser_start.scv').read_text()
    scenes = []
    for name in archive.names():
        if not name.lower().endswith('.xml'):
            continue
        root = ET.fromstring(archive.read(name).decode('utf-8-sig'))
        scripts = list(dict.fromkeys(e.get('scriptname') for section in root
            if section.tag in ('static_objects', 'dynamic_objects', 'interface_objects')
            for e in section.iter() if e.get('scriptname')))
        entries = []
        for script in scripts:
            text = archive.read(script).decode('cp1251', errors='replace')
            if re.search(r'queststate.lastlocation\s*=\s*queststate.activelocation', text):
                entries += re.findall(r'queststate.lastlocation\s*==\s*(\d+)', text)
        wear = not ('_n.' in name.lower() or name.lower() in
                    ('podvorotnia1.xml', 'club_bar011.xml', 'club_bar021.xml'))
        seed = (entries or ['9'])[0]
        bootstrap = base.replace('queststate.activelocation = 9;',
            f'queststate.activelocation = {seed}; queststate.quest_get_wear = {int(wear)};')
        bootstrap = bootstrap.replace('scene.Load("sumerki_entrance.XML");', f'scene.Load("{name}");')
        scenes.append(dict(name=name, scripts=scripts, bootstrap=bootstrap))
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(scenes=scenes, scripts=[n for n in archive.names() if n.lower().endswith('.scv')])
    setup = '''async(page)=>{
 const context=page.audioFixedContext || page.context();
 const p=await context.newPage(); await p.setViewportSize({width:1200,height:1150});
 await p.addInitScript(()=>{const connect=AudioNode.prototype.connect,gains=new WeakMap();
 AudioNode.prototype.connect=function(target,...args){if(target===this.context.destination){
 let gain=gains.get(this.context);if(!gain){gain=this.context.createGain();gain.gain.value=0;
 connect.call(gain,target);gains.set(this.context,gain);}target=gain;}
 return connect.call(this,target,...args);};});
 page.titbitQa={page:p,manifest:MANIFEST,results:[],scripts:[]};
 await p.route('**/game.js',async route=>{const response=await route.fetch();
  await route.fulfill({response,body:(await response.text()).replace("['startup.XML']","['browser_start.scv']")});});
 await p.route('**/browser_start.scv',r=>r.fulfill({status:200,contentType:'text/plain',body:page.titbitQa.bootstrap}));
 return {scenes:page.titbitQa.manifest.scenes.length,scripts:page.titbitQa.manifest.scripts.length};
}'''.replace('MANIFEST', json.dumps(manifest, ensure_ascii=False))
    (out/'setup.js').write_text(setup)
    batch = '''async(page)=>{
 const q=page.titbitQa,p=q.page,out=[];
 for(const s of q.manifest.scenes.slice(q.results.length,q.results.length+5)){
  q.bootstrap=s.bootstrap;let failure='';
  try{await p.goto('http://127.0.0.1:8000/game.html?local=1');
   await p.waitForFunction(()=>titbitFrames>180||document.querySelector('#status').textContent.startsWith('Ошибка'),null,{timeout:30000});
   await p.waitForTimeout(1200);
  }catch(e){failure=e.message;}
  const state=await p.evaluate(()=>({frames:window.titbitFrames,status:document.querySelector('#status').textContent,
    log:document.querySelector('#log').textContent}));
  const errors=state.log.match(/(?:RuntimeError|Aborted|unsupported|function signature mismatch|out of bounds|Error:)[^\\n]*/gi)||[];
  const missingScripts=s.scripts.filter(n=>!state.log.toLowerCase().includes(n.toLowerCase()+' compiled'));
  const r={scene:s.name,frames:state.frames,status:state.status,failure,errors,missingScripts};
  if(errors.length||failure||missingScripts.length)r.tail=state.log.slice(-2400);
  await p.locator('#canvas').screenshot({path:OUTPUT+'/scene-'+s.name.toLowerCase()+'.png'});
  q.results.push(r);out.push(r);
 }
 return out;
}'''.replace('OUTPUT', json.dumps(str(out.resolve())))
    (out/'batch.js').write_text(batch)
    (out/'scripts.js').write_text('''async(page)=>{
 const q=page.titbitQa,p=await q.page.context().newPage();
 await p.addInitScript(()=>{const connect=AudioNode.prototype.connect,gains=new WeakMap();
 AudioNode.prototype.connect=function(target,...args){if(target===this.context.destination){let gain=gains.get(this.context);
 if(!gain){gain=this.context.createGain();gain.gain.value=0;connect.call(gain,target);gains.set(this.context,gain);}
 target=gain;}return connect.call(this,target,...args);};});
 await p.goto('http://127.0.0.1:8000/game.html?local=1');
 await p.waitForFunction(()=>titbitFrames>120,null,{timeout:30000});
 q.scripts=await p.evaluate(names=>names.map(name=>{
  const ok=titbit.ccall('titbit_web_check_script','number',['string'],[name]);
  return {name,ok,log:ok?undefined:document.querySelector('#log').textContent.slice(-1800)};
 }),q.manifest.scripts);
 await p.close();
 return {checked:q.scripts.length,failed:q.scripts.filter(r=>!r.ok)};
}''')
    (out/'report.js').write_text('async(page)=>({scenes:page.titbitQa.results,scripts:page.titbitQa.scripts})')
    return len(scenes), len(manifest['scripts'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print('Scenes, scripts:', prepare(args.archive,args.out))

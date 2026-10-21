#!/usr/bin/env python3
"""Capture actual engine scenes on an owned Xvfb display; never opens the user's display.

A successful load is not visual approval: camera sweeps, animation/occlusion and
playable exits remain manual review items recorded explicitly in the report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]

def file_digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def write_json(path,value):
    path=Path(path)
    temporary=path.with_name(path.name+'.new')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def owned_file(directory,relative):
    if not relative or Path(relative).is_absolute():return None
    target=(directory/relative).resolve()
    if not target.is_relative_to(directory.resolve()):return None
    return target if target.is_file() else None


def resume_record(directory,inputs,scene):
    """Only a completed, fingerprinted attempt can be reused; old folders alone prove nothing."""
    marker=directory/'completed.json'
    try:
        record=json.loads(marker.read_text(encoding='utf-8'))
        if record.get('status')!='complete' or record.get('inputs')!=inputs or record.get('scene')!=scene:return None
        if record.get('processExitCode')!=0 or not record.get('runId'):return None
        report=owned_file(directory,record.get('report'))
        screenshot=owned_file(directory,record.get('screenshot'))
        if not report or not screenshot:return None
        if file_digest(report)!=record.get('reportSha256') or file_digest(screenshot)!=record.get('screenshotSha256'):return None
        evidence=json.loads(report.read_text(encoding='utf-8'))
        if not valid_evidence(evidence,inputs,scene):return None
        return record
    except (OSError,ValueError,TypeError):return None


def valid_evidence(evidence,inputs,scene):
    if not isinstance(evidence,dict):return False
    return (evidence.get('passed') is True and evidence.get('exitCode')==0 and
            evidence.get('executableSha256')==inputs['executableSha256'] and
            evidence.get('privateXvfb') is True and evidence.get('widescreen')==inputs['aspect'] and
            str(evidence.get('validationScene') or '').casefold()==scene.casefold() and
            evidence.get('requiredScenesLoaded') is True and
            scene.casefold() in {name.casefold() for name in evidence.get('scenesLoaded',[])})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--scenes',type=Path,required=True,help='One XML archive name per line: complete 70-scene inventory')
    p.add_argument('--allowlist',type=Path,required=True,help='Scenes with generated/background wings')
    p.add_argument('--aspect',choices=('16:9','16:10'),default='16:9')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--frames',type=int,default=8)
    p.add_argument('--timeout',type=int,default=90)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--unpainted-input',action='store_true',help='Preflight against original archive; generated wings are not present')
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    scenes=[line.strip() for line in a.scenes.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.startswith('#')]
    if not scenes:p.error('Scene inventory is empty')
    if a.frames<1 or a.timeout<1:p.error('--frames and --timeout must be positive')
    if len(set(s.casefold() for s in scenes))!=len(scenes):p.error('Duplicate scenes')
    archive=next((path for path in a.data.iterdir() if path.name.casefold()=='quest.ezd'),None)
    if not archive:p.error('QUEST.ezd missing from --data')
    inputs={'executableSha256':file_digest(a.exe),'archiveSha256':file_digest(archive),'allowlistSha256':file_digest(a.allowlist),
            'sceneInventorySha256':file_digest(a.scenes),'aspect':a.aspect,'frames':a.frames,'timeoutSeconds':a.timeout,
            'harnessSha256':file_digest(Path(__file__)),'probeSha256':file_digest(ROOT/'tools/headless_probe.py'),
            'unpaintedInput':a.unpainted_input}
    saved=a.out/'inputs.json'
    if a.resume and saved.exists() and json.loads(saved.read_text())!=inputs:
        p.error('--resume inputs changed; choose a new output directory')
    write_json(saved,inputs)
    rows=[];started=time.time()
    for index,scene in enumerate(scenes):
        directory=a.out/(str(index+1).zfill(2)+'-'+re.sub('[^a-zA-Z0-9_.-]','_',scene))
        directory.mkdir(parents=True,exist_ok=True)
        record=resume_record(directory,inputs,scene) if a.resume else None
        reused=record is not None
        if record:
            report=directory/record['report'];screenshot=directory/record['screenshot']
            evidence=json.loads(report.read_text(encoding='utf-8'))
            process_code=0;passed=True
        else:
            # Every attempt owns fresh paths. Interruptions cannot leave an old
            # successful report masquerading as a result for the new input set.
            run_id=uuid.uuid4().hex
            attempt=directory/'runs'/run_id;attempt.mkdir(parents=True,exist_ok=False)
            report=attempt/'report.json';screenshot=None
            record={'version':1,'status':'running','runId':run_id,'inputs':inputs,'scene':scene}
            write_json(directory/'completed.json',record)
            command=[sys.executable,str(ROOT/'tools/headless_probe.py'),'--data',str(a.data.resolve()),'--exe',str(a.exe.resolve()),
                     '--frames',str(a.frames),'--timeout',str(a.timeout),'--widescreen',a.aspect,'--scene',scene,
                     '--scene-allowlist',str(a.allowlist.resolve()),'--require-scene',scene,'--out',str(attempt)]
            try:process_code=subprocess.run(command,check=False).returncode
            except OSError as exc:
                process_code='launch failed';record['error']=str(exc)
            try:evidence=json.loads(report.read_text(encoding='utf-8'))
            except (OSError,ValueError):evidence={}
            images=sorted(attempt.glob('frame-*.ppm'))
            if images:
                # Lossless conversion of this attempt's GL readback only.
                from PIL import Image
                screenshot=attempt/'scene.png';Image.open(images[-1]).save(screenshot)
            passed=process_code==0 and screenshot is not None and valid_evidence(evidence,inputs,scene)
            record.update(status='complete' if passed else 'failed',processExitCode=process_code,
                          report=str(report.relative_to(directory)) if report.exists() else None,
                          reportSha256=file_digest(report) if report.exists() else None,
                          screenshot=str(screenshot.relative_to(directory)) if screenshot else None,
                          screenshotSha256=file_digest(screenshot) if screenshot else None)
            write_json(directory/'completed.json',record)
        row={'scene':scene,'loaded':evidence.get('requiredScenesLoaded',False),'passed':passed,
             'worldExpanded':evidence.get('worldExpanded',False),'exitCode':evidence.get('exitCode',process_code),
             'processExitCode':process_code,'runId':record['runId'],'resumed':reused,
             'nonblackPixels':evidence.get('images',[{}])[-1].get('nonblackPixels',0) if evidence.get('images') else 0,
             'screenshot':str(screenshot.relative_to(a.out)) if screenshot else None,
             'screenshotSha256':file_digest(screenshot) if screenshot else None,
             'unpaintedBackgroundWarning':a.unpainted_input,
             'edgeReview':'pending','cameraSweep':'not tested','animationAndOcclusion':'not tested',
             'evidence':str(report.relative_to(a.out)) if report.exists() else None}
        rows.append(row)
        summary={'version':1,'inputs':inputs,'unpaintedInput':a.unpainted_input,'privateXvfb':True,'aspect':a.aspect,'scope':'direct scene load and short real engine render, not gameplay completion',
                 'sceneCount':len(scenes),'completed':len(rows),'seconds':round(time.time()-started,2),'scenes':rows}
        (a.out/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        lines=['# Widescreen scene validation','',
               'Actual game frames captured on a private Xvfb display. Direct scene startup does not establish story/script state or prove gameplay completion.',
               '',f'Aspect: {a.aspect}. Captured {len(rows)} / {len(scenes)} scenes.',
               'Input contains original backgrounds; generated wings are absent.' if a.unpainted_input else 'Input archive fingerprint is recorded in inputs.json.',
               '', 'Edge geometry, moving cameras, character occlusion and scene animations require visual review; no scene is automatically marked visually approved.',
               '', '| Scene | Load | Wide world | Screenshot | Edge review |', '|---|---|---|---|---|']
        for r in rows:
            shot=f"[PNG]({r['screenshot']})" if r['screenshot'] else 'missing'
            lines.append(f"| {r['scene']} | {'pass' if r['passed'] else 'FAIL: '+str(r['exitCode'])} | {'yes' if r['worldExpanded'] else 'central fallback'} | {shot} | pending |")
        (a.out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(f'{len(rows)}/{len(scenes)} {scene}: {row["exitCode"]}, wide={row["worldExpanded"]}',flush=True)
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':raise SystemExit(main())

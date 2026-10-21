#!/usr/bin/env python3
"""Compile source-generated MSVC-layout LLVM IR to native ELF32 objects.

This stage consumes source-generated LLVM IR, translates Windows funclet EH to
DWARF, and generates ELF directly with Clang. No Windows SDK is needed.
"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'probes'))
import ms_eh_to_dwarf
import retarget_ir


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ir',type=Path,default=Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build'))/'ms-ir')
    p.add_argument('--out',type=Path,default=Path(os.environ.get('TITBIT_BUILD_DIR', ROOT/'build'))/'ms-elf')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--filter',default='')
    p.add_argument('--compiler',default='clang++-18')
    p.add_argument('--extra-ir',type=Path,action='append',default=[],
                   help='Additional source-generated IR outside the recipe report')
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    objdir=args.out/'objects';objdir.mkdir(exist_ok=True)
    compiler=shutil.which(args.compiler)
    if not compiler:p.error('Compiler missing: '+args.compiler)
    fingerprint=sha((Path(ms_eh_to_dwarf.__file__).read_bytes()+
                     Path(retarget_ir.__file__).read_bytes()+
                     Path(__file__).read_bytes()+
                     subprocess.check_output([compiler,'--version'])))
    report=json.loads((args.ir/'report.json').read_text())
    rows=[r for r in report['rows'] if r.get('status')=='compiled' and args.filter in r['source']]
    for extra in args.extra_ir:
        source=extra.name.removesuffix('.ll').replace('__','/')
        rows=[row for row in rows if row['source']!=source]
        rows.append({'source':source,'ir':str(extra.resolve())})
    start=time.monotonic()
    def one(row):
        if row['source']=='src/seer/callasm.c':
            return {'source':row['source'],'status':'replaced',
                    'replacement':'platform/seer_call.S',
                    'reason':'Native ELF32 cdecl/MS-thiscall argument-vector calls; stack and unwind tests in platform/'}
        key=row['source'].replace('/','__')
        ir=Path(row.get('ir',args.ir/(key+'.ll')))
        obj=objdir/(key+'.o')
        output=args.out/(key+'.ll')
        mapping=args.out/(key+'.symbols.json')
        cache=args.out/(key+'.cache.json')
        log=args.out/(key+'.log')
        result={'source':row['source'],'ir':str(ir),'object':str(obj),'symbols':str(mapping)}
        try:
            raw=ir.read_bytes()
            signature=sha(raw+fingerprint.encode())
            if cache.exists() and obj.exists():
                old=json.loads(cache.read_text())
                if old['signature']==signature and old['objectSha256']==sha(obj.read_bytes()):
                    return old['result']
            source=raw.decode()
            selections=[
                {'symbol':a or b,'selection':c} for a,b,c in re.findall(
                    r'^\$(?:"([^"]+)"|([^ ]+)) = comdat (largest|samesize|exactmatch)\b',source,re.MULTILINE)]
            dwarf=ms_eh_to_dwarf.convert(source)
            safe,names=retarget_ir.convert(dwarf)
            output.write_text(safe)
            mapping.write_text(json.dumps(names,indent=2))
            checked=subprocess.run(['opt-18','-passes=verify','-disable-output',str(output)],capture_output=True,text=True)
            if checked.returncode:
                log.write_text(checked.stdout+checked.stderr)
                return dict(result,status='error',category='verify',error=checked.stderr[-5000:])
            command=[compiler,'--target=i386-pc-windows-msvc-elf','-Wno-override-module',
                     '-O2','-ffile-prefix-map='+str(ROOT)+'=linux-port','-fno-omit-frame-pointer','-ffunction-sections','-fdata-sections',
                     '-mstack-alignment=16','-mstackrealign',
                     '-c',str(output),'-o',str(obj.with_suffix('.new.o'))]
            built=subprocess.run(command,capture_output=True,text=True)
            log.write_text(built.stdout+built.stderr)
            if built.returncode:
                obj.with_suffix('.new.o').unlink(missing_ok=True)
                return dict(result,status='error',category='codegen',error=built.stderr[-5000:])
            obj.with_suffix('.new.o').replace(obj)
            nm=subprocess.check_output(['nm','-g','-P',str(obj)],text=True)
            definitions={}
            undefined=[]
            for line in nm.splitlines():
                parts=line.split()
                if len(parts)<2:continue
                if parts[1]=='U':undefined.append(parts[0])
                else:definitions[parts[0]]=parts[1]
            result.update(status='compiled',sha256=sha(obj.read_bytes()),definitions=definitions,
                          undefined=undefined,exceptionTranslated=dwarf!=source,comdatSelections=selections)
            cache.write_text(json.dumps({'signature':signature,'objectSha256':result['sha256'],'result':result}))
            return result
        except Exception as exc:
            log.write_text(str(exc))
            return dict(result,status='error',category=type(exc).__name__,error=str(exc))
    done=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(one,row) for row in rows]
        for future in as_completed(futures):
            result=future.result();done.append(result)
            if result['status']=='replaced':continue
            if result['status']!='compiled':
                print('ERROR',result['source'],result['category'],result['error'][:300],flush=True)
            elif len(done)%25==0:print('ELF',len(done),'/',len(rows),flush=True)
    summary={name:sum(r['status']==name for r in done) for name in ('compiled','replaced','error')}
    result={'target':'i386-pc-windows-msvc-elf','seconds':round(time.monotonic()-start,2),
            'summary':summary,'rows':sorted(done,key=lambda row:row['source'])}
    (args.out/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(summary),flush=True)
    return int(summary['error']>0)


if __name__=='__main__':sys.exit(main())

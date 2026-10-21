#!/usr/bin/env python3
"""Run only on an owned, private Xvfb display, recording the actual GL frames."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',required=True,type=Path)
    p.add_argument('--exe',type=Path,default=ROOT/'titbit' if (ROOT/'titbit').is_file() else ROOT/'build/titbit',
                   help='Native ELF to test (packaged executable or main build)')
    p.add_argument('--widescreen',choices=('16:9','16:10'),help='Experimental horizontal scene expansion')
    p.add_argument('--scene',help='Validation-only direct XML startup (not normal gameplay)')
    p.add_argument('--scene-allowlist',type=Path,help='Newline list of scenes with generated wings')
    p.add_argument('--frames',type=int,default=50)
    p.add_argument('--timeout',type=int,default=60)
    p.add_argument('--actions',type=Path,help='Timed XTest key/click/capture actions on the private display')
    p.add_argument('--require-scene',action='append',default=[],help='Fail unless this XML scene was fully loaded; repeatable')
    p.add_argument('--stop-after-actions',action='store_true',help='Request a clean engine-loop exit after the last scripted action')
    p.add_argument('--gdb',action='store_true')
    p.add_argument('--audio',choices=('dummy','disk'),default='dummy')
    p.add_argument('--out',type=Path,default=ROOT/'build/headless-probe')
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    executable=a.exe.resolve();data=a.data.resolve()
    environment=dict(os.environ,SDL_VIDEODRIVER='x11',WAYLAND_DISPLAY='',
                     SDL_AUDIODRIVER=a.audio,LIBGL_ALWAYS_SOFTWARE='1',
                     TITBIT_TEST_FRAMES=str(a.frames),TITBIT_SCREENSHOT_DIR=str(a.out),
                     TITBIT_SCREENSHOT_FRAMES=','.join(map(str,sorted({1,min(20,a.frames),a.frames}))))
    if a.scene:
        environment['TITBIT_WIDESCREEN_VALIDATION']='1'
    if a.scene_allowlist:
        environment['TITBIT_WIDESCREEN_SCENES']=str(a.scene_allowlist.resolve())
    if a.audio=='disk':
        environment.update(SDL_DISKAUDIOFILE=str(a.out/'game.pcm'),SDL_DISKAUDIODELAY='10')
    stop_file=a.out/'test-stop.request'
    stop_file.unlink(missing_ok=True)
    if a.stop_after_actions:
        if not a.actions:p.error('--stop-after-actions requires --actions')
        environment['TITBIT_TEST_STOP_FILE']=str(stop_file)
    for path in a.out.glob('frame-*'):path.unlink()
    with (a.out/'xvfb.log').open('w') as errors:
        # WSLg mounts its filesystem socket directory read-only. Fixed display
        # numbers let Xvfb use Linux abstract sockets there; -displayfd can loop
        # indefinitely while probing the occupied WSLg display zero.
        display=None
        for candidate in range(99,160):
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                try:connection.connect('\0/tmp/.X11-unix/X'+str(candidate));continue
                except OSError:pass
            if Path('/tmp/.X'+str(candidate)+'-lock').exists():continue
            display=subprocess.Popen(['Xvfb',':'+str(candidate),'-nolisten','tcp','-screen','0',('1366x768x24' if a.widescreen=='16:9' else '1230x768x24' if a.widescreen else '1024x768x24')],
                                     stdout=errors,stderr=errors,text=True)
            deadline=time.monotonic()+5
            ready=False
            while time.monotonic()<deadline and display.poll() is None:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                    try:
                        connection.connect('\0/tmp/.X11-unix/X'+str(candidate))
                        # Parallel probes can race between selecting a free
                        # number and starting Xvfb. A listening socket alone
                        # might belong to another probe's server; only accept
                        # the display whose X lock contains our child's PID.
                        owner=int(Path('/tmp/.X'+str(candidate)+'-lock').read_text().strip())
                        if owner==display.pid and display.poll() is None:
                            ready=True;break
                    except (OSError,ValueError):pass
                    time.sleep(.05)
            if ready:break
            display.terminate();display.wait()
        if not display or not ready:raise RuntimeError('Private Xvfb did not start')
        process=None
        try:
            number=str(candidate)
            environment['DISPLAY']=':'+number
            start=time.monotonic()
            actions=json.loads(a.actions.read_text()) if a.actions else []
            performed=[]
            scenes=[];loading_scene=None;current_scene=None;scene_ready=0;partial=''
            with (a.out/'game.log').open('w') as log:
                command=[str(executable),'--data',str(data)]
                if a.widescreen:command+=['--windowed','--widescreen='+a.widescreen]
                if a.scene:command+=['--validate-scene',a.scene]
                if a.gdb:command=['gdb','--batch','-q','-ex','set pagination off','-ex','run',
                                 '-ex','thread apply all bt','-ex','info registers',
                                 # GDB's diagnostic commands fail after a normal exit.
                                 # Return the inferior's actual status when it exited;
                                 # a signal-stopped inferior remains alive for the
                                 # backtrace and is rejected by the signal check below.
                                 '-ex','python import gdb; gdb.execute("quit " + str(gdb.parse_and_eval("$_exitcode"))) if gdb.selected_inferior().pid == 0 else None',
                                 '--args',*command]
                process=subprocess.Popen(command,env=environment,
                    stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
                scene_log=(a.out/'game.log').open(errors='replace')
                while process.poll() is None and time.monotonic()-start<a.timeout:
                    # Use the engine's actual completed-load marker. Cold GL,
                    # GDB and archive initialization can delay the first frame;
                    # elapsed wall time alone does not identify the current UI.
                    try:partial+=scene_log.read()
                    except OSError as exc:
                        # WSL/DrvFS may report ENODATA while an empty/new log
                        # is being filled by another process. Retry only this
                        # transient EOF case, not arbitrary filesystem errors.
                        if exc.errno not in (errno.ENODATA,errno.EAGAIN):raise
                    lines=partial.split('\n');partial=lines.pop()
                    for line in lines:
                        line=line.strip()
                        if line.startswith('Start loading ') and line.strip().lower().endswith('.xml'):
                            loading_scene=line[len('Start loading '):].strip();current_scene=None
                        elif line.strip()=='Scene loaded' and loading_scene:
                            current_scene=loading_scene;loading_scene=None
                            scenes.append(current_scene);scene_ready=time.monotonic()
                    for index,action in enumerate(actions):
                        if index in performed or time.monotonic()-start<action['at']:continue
                        if action.get('whenScene') and (not current_scene or current_scene.casefold()!=action['whenScene'].casefold()
                                or time.monotonic()-scene_ready<action.get('sceneDelay',.5)):continue
                        kind=action['type']
                        if kind=='key':
                            subprocess.run(['xdotool','key',action['key']],env=environment,check=True)
                        elif kind=='click':
                            subprocess.run(['xdotool','mousemove','--sync',str(action['x']),str(action['y'])],env=environment,check=True)
                            # The original controller resolves the hovered object
                            # in its next rendered frame, then Click uses it.
                            time.sleep(.25)
                            button=str(action.get('button',1))
                            subprocess.run(['xdotool','mousedown',button],env=environment,check=True)
                            time.sleep(.1)
                            subprocess.run(['xdotool','mouseup',button],env=environment,check=True)
                        elif kind=='capture':
                            from PIL import ImageGrab
                            ImageGrab.grab(xdisplay=environment['DISPLAY']).save(a.out/(action['name']+'.png'))
                        else:raise ValueError('Unknown action type: '+kind)
                        performed.append(index)
                    if a.stop_after_actions and len(performed)==len(actions):stop_file.touch(exist_ok=True)
                    time.sleep(.05)
                scene_log.close()
                code=process.poll()
                if code is None:
                    os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=10);code='timeout'
            text=(a.out/'game.log').read_text(errors='replace')
            scenes=[];loading_scene=None
            for line in text.splitlines():
                if line.startswith('Start loading ') and line.strip().lower().endswith('.xml'):
                    loading_scene=line[len('Start loading '):].strip()
                elif line.strip()=='Scene loaded' and loading_scene:
                    scenes.append(loading_scene);loading_scene=None
            images=[json.loads(path.read_text()) for path in sorted(a.out.glob('frame-*.json'))]
            report={'executableSha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
                    'display':environment['DISPLAY'],'ownedXvfbPid':display.pid,'videoDriver':'x11','privateXvfb':True,'widescreen':a.widescreen,'validationScene':a.scene,
                    'stoppedAfterActions':a.stop_after_actions and stop_file.exists(),
                    'worldExpanded':bool(a.scene and 'Widescreen scene '+a.scene+': world enabled' in text),
                    'seconds':round(time.monotonic()-start,2),'exitCode':code,'framesRequested':a.frames,
                    'images':images,'log':str(a.out/'game.log')}
            report['actionsPerformed']=[actions[index] for index in performed]
            report['scenesLoaded']=scenes
            report['requiredScenes']=a.require_scene
            report['requiredScenesLoaded']=all(scene.casefold() in {s.casefold() for s in scenes} for scene in a.require_scene)
            report['passed']=(code==0 and bool(images) and len(performed)==len(actions)
                              and report['requiredScenesLoaded']
                              and 'file corrupt' not in text and 'received signal' not in text)
            (a.out/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps({key:report[key] for key in ('passed','exitCode','seconds','executableSha256','scenesLoaded','requiredScenesLoaded')},indent=2))
            print('Full report: '+str(a.out/'report.json'))
            return 0 if report['passed'] else 1
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
            display.terminate()
            try:display.wait(timeout=5)
            except subprocess.TimeoutExpired:display.kill();display.wait()


if __name__=='__main__':raise SystemExit(main())

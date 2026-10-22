#!/usr/bin/env python3
"""Render the actual legacy GL shader and check color-material pixels in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from patch_web_lighting import build

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <SDL.h>
#include <GL/gl.h>
#include <emscripten.h>
static unsigned sample(int lighting, int color_material) {
  GLfloat ambient[] = {1,1,1,1}, material[] = {.2,.2,.2,1};
  glDisable(GL_COLOR_MATERIAL);
  glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, material);
  glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient);
  if(lighting) glEnable(GL_LIGHTING); else glDisable(GL_LIGHTING);
  if(color_material) glEnable(GL_COLOR_MATERIAL);
  glColor4f(.5,.25,.75,1);
  glClear(GL_COLOR_BUFFER_BIT);
  glBegin(GL_TRIANGLES);
  glNormal3f(0,0,1);glVertex3f(-1,-1,0);
  glNormal3f(0,0,1);glVertex3f(1,-1,0);
  glNormal3f(0,0,1);glVertex3f(0,1,0);
  glEnd();
  unsigned char rgba[4];glReadPixels(8,8,1,1,GL_RGBA,GL_UNSIGNED_BYTE,rgba);
  return rgba[0]*65536u+rgba[1]*256u+rgba[2];
}
int main(void) {
  if(SDL_Init(SDL_INIT_VIDEO)) { EM_ASM({Module.probeFailure='SDL_Init failed';}); return 1; }
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,0);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,SDL_GL_CONTEXT_PROFILE_ES);
  SDL_Window *window=SDL_CreateWindow("probe",0,0,16,16,SDL_WINDOW_OPENGL);
  SDL_GLContext context=SDL_GL_CreateContext(window);
  if(!window||!context) { EM_ASM({Module.probeFailure='GL context failed';}); return 2; }
  glViewport(0,0,16,16);
  glMatrixMode(GL_PROJECTION);glLoadIdentity();
  glMatrixMode(GL_MODELVIEW);glLoadIdentity();
  unsigned unlit=sample(0,0),default_material=sample(1,0),color_material=sample(1,1);
  EM_ASM({Module.probeColors=Array.of($0,$1,$2);},unlit,default_material,color_material);
  return 0;
}
'''
JS = r'''
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.TITBIT_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,channel:'chromium',args:['--no-sandbox','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',message=>{if(message.type()==='error' && !message.text().startsWith('WARNING: using emscripten GL'))errors.push(message.text());});
  await page.goto(process.env.TITBIT_LIGHTING_PROBE_URL);
  await page.waitForFunction(()=>window.result || window.failure,null,{timeout:30000})
    .catch(error=>{throw new Error(JSON.stringify(errors)+' '+error.message);});
  assert.equal(await page.evaluate(()=>window.failure),undefined);
  const colors=(await page.evaluate(()=>window.result)).map(n=>[n>>16,(n>>8)&255,n&255]);
  const expected=[[127,63,191],[51,51,51],[127,63,191]];
  colors.forEach((rgb,i)=>rgb.forEach((v,j)=>assert.ok(Math.abs(v-expected[i][j])<=2,JSON.stringify({colors,expected}))));
  assert.deepEqual(errors,[]);
  console.log('WebGL color material:',JSON.stringify(colors),'unlit/default/color-tracked pixels passed.');
} finally {await browser.close();}
'''


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()

    def log_message(self, *_args):
        pass


def main():
    emcc = Path(shutil.which('emcc')).resolve()
    with tempfile.TemporaryDirectory(prefix='titbit-lighting-') as folder:
        folder = Path(folder)
        lighting = build(emcc.parents[1] / 'share/emscripten/src/lib/libglemu.js', folder / 'lighting.js')
        (folder / 'probe.c').write_text(C)
        environment = dict(os.environ, EM_CACHE=str(ROOT / 'build/web/game/emscripten-cache'))
        subprocess.run([str(emcc), '-pthread', '-sUSE_SDL=2', '-sLEGACY_GL_EMULATION=1',
                        '-sMODULARIZE=1', '-sEXPORT_NAME=createLightingProbe', '-sEXIT_RUNTIME=0',
                        '--js-library', str(lighting), str(folder / 'probe.c'), '-o', str(folder / 'probe.js')],
                       env=environment, check=True)
        (folder / 'index.html').write_text('<link rel="icon" href="data:,"><canvas id="canvas" width="16" height="16"></canvas>'
            '<script src="probe.js"></script><script>createLightingProbe({canvas:document.querySelector("canvas")})'
            '.then(module=>{window.result=module.probeColors;window.failure=module.probeFailure;})'
            '.catch(error=>window.failure=String(error));</script>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(folder)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            environment['TITBIT_LIGHTING_PROBE_URL'] = f'http://127.0.0.1:{server.server_port}/'
            subprocess.run(['node', '--input-type=module', '-e', JS], env=environment, check=True)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    main()

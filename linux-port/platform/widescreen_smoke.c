#define _POSIX_C_SOURCE 200809L
#include "titbit_platform.h"
#include "presentation.h"
#include <SDL.h>
#include <GL/gl.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#if defined(__i386__)
#define API __attribute__((stdcall))
#else
#define API
#endif
extern void API CompatSceneChanged(const char *);
extern double API CompatWorldAspect(double);
extern double API CompatWorldMouseX(double);
extern void API CompatBeginOverlay(void);
extern void API CompatEndOverlay(void);
extern void API CompatBeginCursorOverlay(void);
extern void API CompatEndCursorOverlay(void);
int main(void) {
 setenv("TITBIT_FULLSCREEN","0",1);setenv("TITBIT_WIDESCREEN","16:9",1);
 char path[]="/tmp/titbit-wide-XXXXXX";int fd=mkstemp(path);assert(fd>=0);
 FILE *file=fdopen(fd,"w");assert(file);fputs("test.xml\n",file);fclose(file);
 setenv("TITBIT_WIDESCREEN_SCENES",path,1);
 assert(tb_init());TBWindow *window=tb_window_create("Private widescreen test",1024,768,1);assert(window);
 void *ctx=tb_gl_context(window);assert(ctx&&tb_gl_make_current(window,ctx));tb_gl_viewport(0,0,1024,768);
 int vp[4];glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==171&&vp[2]==1024);
 CompatSceneChanged("menu.xml");assert(CompatWorldAspect(4.0/3)==4.0/3);
 glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==171&&vp[2]==1024);
 CompatSceneChanged("test.xml");assert(fabs(CompatWorldAspect(4.0/3)-1366.0/768)<1e-12);
 glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==0&&vp[2]==1366);
 assert(fabs(CompatWorldMouseX(1)-1024.0/1366)<1e-12);
 glDisable(GL_SCISSOR_TEST);CompatBeginOverlay();glGetIntegerv(GL_VIEWPORT,vp);
 assert(vp[0]==171&&vp[2]==1024&&glIsEnabled(GL_SCISSOR_TEST));
 CompatBeginOverlay();CompatEndOverlay();assert(glIsEnabled(GL_SCISSOR_TEST));
 glMatrixMode(GL_MODELVIEW);CompatBeginCursorOverlay();glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==0&&vp[2]==1366);
 double projection[16];glGetDoublev(GL_PROJECTION_MATRIX,projection);assert(fabs(projection[0]-2.0/1366)<1e-12);
 CompatEndCursorOverlay();glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==171&&vp[2]==1024);
 CompatEndOverlay();glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==0&&vp[2]==1366&&!glIsEnabled(GL_SCISSOR_TEST));
 CompatBeginOverlay();CompatBeginCursorOverlay();CompatSceneChanged("menu.xml");CompatEndCursorOverlay();CompatEndOverlay();
 glGetDoublev(GL_PROJECTION_MATRIX,projection);assert(fabs(projection[0]-1)<1e-12&&!glIsEnabled(GL_SCISSOR_TEST));
 CompatSceneChanged("test.xml");CompatWorldAspect(4.0/3);
 SDL_Event event={0};event.type=SDL_MOUSEMOTION;event.motion.windowID=SDL_GetWindowID(SDL_GL_GetCurrentWindow());event.motion.x=0;event.motion.y=384;
 assert(SDL_PushEvent(&event)==1);TBEvent out;int found=0;while(tb_poll_event(&out))if(out.message==0x200){assert(out.x==-171&&out.y==384);found=1;}assert(found);
 event.type=SDL_MOUSEBUTTONDOWN;event.button.windowID=SDL_GetWindowID(SDL_GL_GetCurrentWindow());event.button.button=SDL_BUTTON_LEFT;event.button.x=0;event.button.y=384;
 assert(SDL_PushEvent(&event)==1);found=0;while(tb_poll_event(&out))if(out.message==0x201){assert(out.x==-171&&out.y==384);found=1;}assert(found);
 event.type=SDL_MOUSEBUTTONUP;event.button.x=1365;assert(SDL_PushEvent(&event)==1);found=0;while(tb_poll_event(&out))if(out.message==0x202){assert(out.x==1194&&out.y==384);found=1;}assert(found);
 TBViewport world=tb_fit_viewport(1600,1200,1366,768);TBViewport canvas=world;
 canvas.width=(int64_t)world.width*1024/1366;canvas.x+=(world.width-canvas.width)/2;
 int lx,ly;assert(tb_map_world_mouse(canvas,world,world.x,world.top+world.height/2,1024,768,&lx,&ly)&&lx<0&&ly>=383&&ly<=384);
 assert(!tb_map_world_mouse(canvas,world,world.x,world.top-1,1024,768,&lx,&ly)&&lx==-1&&ly==-1);
 assert(!tb_map_world_mouse(canvas,world,world.x+world.width,world.top+1,1024,768,&lx,&ly)&&lx==-1&&ly==-1);
 CompatSceneChanged("menu.xml");assert(CompatWorldMouseX(1)==1);
 remove(path);tb_window_destroy(window);tb_shutdown();puts("PASS wide world, failclosed scenes, nested central UI scissor, left/right wing motion/buttons, letterboxes and picking aspect");return 0;
}

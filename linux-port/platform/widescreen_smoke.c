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
extern int API CompatBeginFullscreenEffect(float,float,float,float,float,float);
extern void API CompatEndFullscreenEffect(int);
static void rectangle(float x,float y,float width,float height) {
 glBegin(GL_QUADS);glVertex2f(x,y);glVertex2f(x+width,y);glVertex2f(x+width,y+height);glVertex2f(x,y+height);glEnd();
}
static unsigned red(int x,int y) {unsigned char pixel[4];glReadPixels(x,y,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);return pixel[0];}
static void white_frame(void) {glDisable(GL_SCISSOR_TEST);glClearColor(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT);glEnable(GL_SCISSOR_TEST);}
static void photometric_effect(void) {
 CompatSceneChanged("test.xml");CompatWorldAspect(4.0/3);
 glDisable(GL_DEPTH_TEST);glDisable(GL_TEXTURE_2D);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
 glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,1024,768,0,-10000,20000);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 assert(!CompatBeginFullscreenEffect(0,0,1024,768,.01f,.01f));
 glDisable(GL_SCISSOR_TEST);CompatBeginOverlay();
 int vp[4],scissor[4];glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==171&&vp[2]==1024);
 white_frame();int token=CompatBeginFullscreenEffect(0,0,1024,768,.01f,.01f);assert(token);
 glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==0&&vp[2]==1366);glColor4f(0,0,0,.5f);rectangle(0,0,1024,768);CompatEndFullscreenEffect(token);
 unsigned left=red(20,384),center=red(683,384),right=red(1340,384);assert(left>=126&&left<=129&&left==center&&center==right);
 glGetIntegerv(GL_VIEWPORT,vp);glGetIntegerv(GL_SCISSOR_BOX,scissor);assert(vp[0]==171&&vp[2]==1024&&scissor[0]==171&&scissor[2]==1024&&glIsEnabled(GL_SCISSOR_TEST));
 white_frame();token=CompatBeginFullscreenEffect(0,0,1024,768,1,1);assert(!token);rectangle(0,0,1024,768);CompatEndFullscreenEffect(token);
 assert(red(20,384)==255&&red(683,384)==center&&red(1340,384)==255);
 white_frame();token=CompatBeginFullscreenEffect(200,150,400,300,.01f,.01f);assert(!token);rectangle(200,150,400,300);CompatEndFullscreenEffect(token);
 assert(red(20,384)==255&&red(683,384)==center&&red(1340,384)==255);
 CompatBeginCursorOverlay();assert(!CompatBeginFullscreenEffect(0,0,1024,768,.01f,.01f));CompatEndCursorOverlay();
 token=CompatBeginFullscreenEffect(0,0,1024,768,.01f,.01f);assert(token);CompatSceneChanged("menu.xml");CompatEndFullscreenEffect(token);CompatEndOverlay();
 assert(!glIsEnabled(GL_SCISSOR_TEST));glGetIntegerv(GL_VIEWPORT,vp);assert(vp[0]==171&&vp[2]==1024);
 printf("PASS fullscreen swatch half-black left/center/right=%u/%u/%u; full-UV menu/dialog remain central; viewport/scissor restore including scene transition\n",left,center,right);
}
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
 photometric_effect();remove(path);tb_window_destroy(window);tb_shutdown();puts("PASS wide world, failclosed scenes, nested central UI scissor, left/right wing motion/buttons, letterboxes and picking aspect");return 0;
}

#define _XOPEN_SOURCE 700
#define _FILE_OFFSET_BITS 64
#include "titbit_platform.h"
#include "presentation.h"
#include <SDL.h>
#include <GL/gl.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>
#include <pthread.h>
#include <math.h>

struct TBWindow { SDL_Window *window; SDL_GLContext context; struct TBWindow *next;
 int logical_width,logical_height,presentation,viewport[4];int64_t relative_x,relative_y;
};
static TBWindow *windows;
static TBWindow *event_window(uint32_t id) {
 SDL_Window *native=id?SDL_GetWindowFromID(id):SDL_GL_GetCurrentWindow();
 for(TBWindow *w=windows;w;w=w->next)if(w->window&&w->window==native)return w;
 return NULL;
}
static void apply_viewport(void) {
 TBWindow *w=event_window(0);if(!w||!SDL_GL_GetCurrentContext())return;
 int width,height;SDL_GL_GetDrawableSize(w->window,&width,&height);
 TBViewport vp=tb_fit_viewport(width,height,w->logical_width,w->logical_height);
 if(vp.width<=0||vp.height<=0)return;
 int *v=w->viewport;
 glViewport(vp.x+(int64_t)v[0]*vp.width/w->logical_width,vp.y+(int64_t)v[1]*vp.height/w->logical_height,
            (int64_t)v[2]*vp.width/w->logical_width,(int64_t)v[3]*vp.height/w->logical_height);
}
void tb_gl_viewport(int x,int y,int width,int height) {
 TBWindow *w=event_window(0);if(!w){glViewport(x,y,width,height);return;}
 w->viewport[0]=x;w->viewport[1]=y;w->viewport[2]=width;w->viewport[3]=height;apply_viewport();
}
static TBViewport mouse_viewport(TBWindow *w) {
 int width,height;SDL_GetWindowSize(w->window,&width,&height);
 return tb_fit_viewport(width,height,w->logical_width,w->logical_height);
}
#ifndef __EMSCRIPTEN__
struct AudioItem { TBWaveHeader *header; unsigned offset; struct AudioItem *next; };
struct TBAudio { SDL_AudioDeviceID device; SDL_AudioSpec spec; struct AudioItem *first,*last; unsigned volume;
 FILE *capture_file;char *capture_base;unsigned capture_id,capture_peak;int capture_error;
 uint64_t capture_bytes,capture_samples,capture_nonzero;double capture_energy;struct TBAudio *capture_next;
};
static TBAudio *capture_devices;
static pthread_mutex_t capture_mutex=PTHREAD_MUTEX_INITIALIZER;
static unsigned capture_sequence;
static void audio_capture_shutdown(void);
static unsigned master_volume=65535;
static int master_mute;
#else
static void audio_capture_shutdown(void) {}
#endif
static TBInput input_state;
static int initialized;
static SDL_Surface *project_icon;
static SDL_Cursor *arrow_cursor;
const char *tb_error(void) { return SDL_GetError(); }
int tb_init(void) {
 if(initialized)return 1;
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS|SDL_INIT_TIMER)!=0)return 0;
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2);
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,1);
#ifdef __EMSCRIPTEN__
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2);
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,0);
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,SDL_GL_CONTEXT_PROFILE_ES);
#endif
 SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER,1);
 SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE,24);
 initialized=1;return 1;
}
void tb_shutdown(void) { audio_capture_shutdown();if(project_icon)SDL_FreeSurface(project_icon);project_icon=NULL;if(arrow_cursor)SDL_FreeCursor(arrow_cursor);arrow_cursor=NULL;if(initialized)SDL_Quit();initialized=0;memset(&input_state,0,sizeof(input_state)); }
TBWindow *tb_window_create(const char *title,int width,int height,int fullscreen) {
 TBWindow *w;
 if(!tb_init())return NULL;
 w=calloc(1,sizeof(*w));if(!w)return NULL;
 w->logical_width=width;w->logical_height=height;w->presentation=fullscreen;
 w->viewport[2]=width;w->viewport[3]=height;
 const char *preference=getenv("TITBIT_FULLSCREEN");
 int start_fullscreen=fullscreen&&(!preference||strcmp(preference,"0"));
#ifdef __EMSCRIPTEN__
 start_fullscreen=0;
 /* WinMM creates invisible message windows. Only the game window owns the
  * browser canvas; SDL would resize that same canvas for each helper HWND. */
 if(!fullscreen){w->next=windows;windows=w;return w;}
#endif
 unsigned window_flags=SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN|SDL_WINDOW_ALLOW_HIGHDPI;
#ifndef __EMSCRIPTEN__
 if(fullscreen)window_flags|=SDL_WINDOW_RESIZABLE;
#endif
 /* Browser CSS scales the presentation; retain the engine's 1024x768 input
  * and rendering coordinates. SDL probes CSS using a temporary 1x1 canvas. */
 if(start_fullscreen)window_flags|=SDL_WINDOW_FULLSCREEN_DESKTOP;
 w->window=SDL_CreateWindow(title,SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,width,height,window_flags);
 if(!w->window){free(w);return NULL;}w->next=windows;windows=w;return w;
}
void tb_window_destroy(TBWindow *w) { TBWindow **p=&windows;if(!w)return;while(*p&&*p!=w)p=&(*p)->next;if(*p)*p=w->next;if(w->context)SDL_GL_DeleteContext(w->context);SDL_DestroyWindow(w->window);free(w); }
int tb_window_show(TBWindow *w,int show) { if(!w)return 0;if(!w->window)return 1;if(show)SDL_ShowWindow(w->window);else SDL_HideWindow(w->window);return 1; }
int tb_window_move(TBWindow *w,int x,int y,int width,int height) {
 if(!w||width<=0||height<=0)return 0;
 if(!w->window)return 1;
 /* The reconstructed focus handler requests the desktop resolution. Keep
  * its logical game canvas separate from the user's window placement. */
 if(w->presentation)return 1;
 SDL_SetWindowPosition(w->window,x,y);SDL_SetWindowSize(w->window,width,height);return 1;
}
int tb_window_focus(TBWindow *w) {
 if(!w)return 0;
 if(!w->window)return 1;
 SDL_RaiseWindow(w->window);return SDL_SetWindowInputFocus(w->window)==0;
}
int tb_window_opengl(TBWindow *w) { return w&&(SDL_GetWindowFlags(w->window)&SDL_WINDOW_OPENGL)!=0; }
void *tb_project_icon(void) {
 if(project_icon)return project_icon;
 project_icon=SDL_CreateRGBSurface(0,32,32,32,0x00ff0000,0x0000ff00,0x000000ff,0xff000000);if(!project_icon)return NULL;
 SDL_FillRect(project_icon,NULL,0xffb9f46a);SDL_Rect bar={7,6,19,4},stem={14,10,5,17};
 SDL_FillRect(project_icon,&bar,0xff121a1e);SDL_FillRect(project_icon,&stem,0xff121a1e);return project_icon;
}
void *tb_arrow_cursor(void) { if(!tb_init())return NULL;if(!arrow_cursor)arrow_cursor=SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_ARROW);return arrow_cursor; }
void tb_window_icon(TBWindow *window,void *icon) { if(window&&window->window&&icon)SDL_SetWindowIcon(window->window,icon); }
int tb_display_mode(int index,int *width,int *height,int *refresh,int *bits) {
 SDL_DisplayMode mode;if(!tb_init())return 0;
 if((index<0?SDL_GetDesktopDisplayMode(0,&mode):SDL_GetDisplayMode(0,index,&mode))!=0)return 0;
 *width=mode.w;*height=mode.h;*refresh=mode.refresh_rate;*bits=SDL_BITSPERPIXEL(mode.format);return 1;
}
void tb_window_size(TBWindow *w,int *width,int *height) { if(w){if(w->presentation||!w->window){*width=w->logical_width;*height=w->logical_height;}else SDL_GetWindowSize(w->window,width,height);} }
void *tb_gl_context(TBWindow *w) { if(!w)return NULL;if(!w->context)w->context=SDL_GL_CreateContext(w->window);return w->context; }
int tb_gl_make_current(TBWindow *w,void *context) { int ok=SDL_GL_MakeCurrent(w?w->window:NULL,context)==0;if(ok&&context)apply_viewport();return ok; }
void tb_gl_delete_context(void *context) { TBWindow *w;for(w=windows;w;w=w->next)if(w->context==context)w->context=NULL;if(context)SDL_GL_DeleteContext(context); }
void *tb_gl_proc(const char *name) { return SDL_GL_GetProcAddress(name); }
static void capture_selected_frame(void);
void tb_swap(TBWindow *w) { if(w){capture_selected_frame();SDL_GL_SwapWindow(w->window);} }
int tb_cursor(int show) { return SDL_ShowCursor(show?SDL_ENABLE:SDL_DISABLE); }
uint64_t tb_counter(void) { return SDL_GetPerformanceCounter(); }
uint64_t tb_frequency(void) { return SDL_GetPerformanceFrequency(); }
uint32_t tb_milliseconds(void) { return SDL_GetTicks(); }
void tb_sleep(uint32_t ms) { SDL_Delay(ms); }

/* DirectInput DIK codes are PC set-1 scan codes, not SDL keycodes. */
static unsigned dik(SDL_Scancode s) {
 switch(s) {
 case SDL_SCANCODE_ESCAPE:return 1;case SDL_SCANCODE_BACKSPACE:return 14;case SDL_SCANCODE_TAB:return 15;
 case SDL_SCANCODE_RETURN:return 28;case SDL_SCANCODE_LCTRL:return 29;case SDL_SCANCODE_RCTRL:return 157;
 case SDL_SCANCODE_LSHIFT:return 42;case SDL_SCANCODE_RSHIFT:return 54;case SDL_SCANCODE_LALT:return 56;
 case SDL_SCANCODE_RALT:return 184;case SDL_SCANCODE_SPACE:return 57;case SDL_SCANCODE_CAPSLOCK:return 58;
 case SDL_SCANCODE_UP:return 200;case SDL_SCANCODE_LEFT:return 203;case SDL_SCANCODE_RIGHT:return 205;
 case SDL_SCANCODE_DOWN:return 208;case SDL_SCANCODE_HOME:return 199;case SDL_SCANCODE_END:return 207;
 case SDL_SCANCODE_PAGEUP:return 201;case SDL_SCANCODE_PAGEDOWN:return 209;case SDL_SCANCODE_INSERT:return 210;
 case SDL_SCANCODE_DELETE:return 211;
 case SDL_SCANCODE_MINUS:return 12;case SDL_SCANCODE_EQUALS:return 13;case SDL_SCANCODE_LEFTBRACKET:return 26;
 case SDL_SCANCODE_RIGHTBRACKET:return 27;case SDL_SCANCODE_SEMICOLON:return 39;case SDL_SCANCODE_APOSTROPHE:return 40;
 case SDL_SCANCODE_GRAVE:return 41;case SDL_SCANCODE_BACKSLASH:return 43;case SDL_SCANCODE_COMMA:return 51;
 case SDL_SCANCODE_PERIOD:return 52;case SDL_SCANCODE_SLASH:return 53;
 default:break;
 }
 if(s>=SDL_SCANCODE_1&&s<=SDL_SCANCODE_9)return 2+(s-SDL_SCANCODE_1);
 if(s==SDL_SCANCODE_0)return 11;
 if(s>=SDL_SCANCODE_F1&&s<=SDL_SCANCODE_F10)return 59+(s-SDL_SCANCODE_F1);
 if(s==SDL_SCANCODE_F11)return 87;
 if(s==SDL_SCANCODE_F12)return 88;
 if(s>=SDL_SCANCODE_A&&s<=SDL_SCANCODE_Z){static const uint8_t letters[]={30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44};return letters[s-SDL_SCANCODE_A];}
 return 0;
}
static unsigned vk(SDL_Keycode k) {
 if(k>='a'&&k<='z')return k-'a'+'A';
 if(k>='0'&&k<='9')return k;
 switch(k){case SDLK_ESCAPE:return 27;case SDLK_RETURN:return 13;case SDLK_SPACE:return 32;case SDLK_TAB:return 9;
 case SDLK_BACKSPACE:return 8;case SDLK_LEFT:return 37;case SDLK_UP:return 38;case SDLK_RIGHT:return 39;case SDLK_DOWN:return 40;
 case SDLK_LSHIFT:case SDLK_RSHIFT:return 16;case SDLK_LCTRL:case SDLK_RCTRL:return 17;case SDLK_LALT:case SDLK_RALT:return 18;default:break;}
 switch(k){case SDLK_HOME:return 36;case SDLK_END:return 35;case SDLK_PAGEUP:return 33;case SDLK_PAGEDOWN:return 34;case SDLK_INSERT:return 45;case SDLK_DELETE:return 46;
 case SDLK_SEMICOLON:return 186;case SDLK_EQUALS:return 187;case SDLK_COMMA:return 188;case SDLK_MINUS:return 189;case SDLK_PERIOD:return 190;case SDLK_SLASH:return 191;
 case SDLK_BACKQUOTE:return 192;case SDLK_LEFTBRACKET:return 219;case SDLK_BACKSLASH:return 220;case SDLK_RIGHTBRACKET:return 221;case SDLK_QUOTE:return 222;default:break;}
 if(k>=SDLK_F1&&k<=SDLK_F12)return 112+(k-SDLK_F1);
 return 0;
}
int tb_poll_event(TBEvent *out) {
 SDL_Event e;
 /* Resize and DPI changes must update GL before the next game frame even
  * though the original engine ignores WM_SIZE. */
 apply_viewport();
 while(SDL_PollEvent(&e)) {
  memset(out,0,sizeof(*out));out->time=e.common.timestamp;
  if(e.type==SDL_QUIT){out->message=0x12;return 1;}
  if(e.type==SDL_KEYDOWN||e.type==SDL_KEYUP){unsigned sc=dik(e.key.keysym.scancode);int down=e.type==SDL_KEYDOWN;
   TBWindow *w=event_window(e.key.windowID);
   if(w&&w->presentation&&(e.key.keysym.sym==SDLK_F11||(e.key.keysym.sym==SDLK_RETURN&&(e.key.keysym.mod&KMOD_ALT)))){
    if(down&&!e.key.repeat){uint32_t flags=SDL_GetWindowFlags(w->window);SDL_SetWindowFullscreen(w->window,(flags&SDL_WINDOW_FULLSCREEN)?0:SDL_WINDOW_FULLSCREEN_DESKTOP);apply_viewport();}
    continue;
   }
   if(sc)input_state.keys[sc]=down?0x80:0;
   out->wparam=vk(e.key.keysym.sym);
   if(!out->wparam&&e.key.keysym.scancode>=SDL_SCANCODE_A&&e.key.keysym.scancode<=SDL_SCANCODE_Z)out->wparam='A'+e.key.keysym.scancode-SDL_SCANCODE_A;
   if(!out->wparam)continue;
   out->message=down?0x100:0x101;
   out->lparam=(intptr_t)(1u|((sc&0xff)<<16)|(down?(e.key.repeat?0x40000000u:0):0xc0000000u));return 1;}
  if(e.type==SDL_MOUSEMOTION){TBWindow *w=event_window(e.motion.windowID);
   if(w&&w->presentation){TBViewport vp=mouse_viewport(w);int x,y;
    tb_map_mouse(vp,e.motion.x,e.motion.y,w->logical_width,w->logical_height,&x,&y);e.motion.x=x;e.motion.y=y;
    if(vp.width>0&&vp.height>0){w->relative_x+=(int64_t)e.motion.xrel*w->logical_width;w->relative_y+=(int64_t)e.motion.yrel*w->logical_height;
     e.motion.xrel=w->relative_x/vp.width;e.motion.yrel=w->relative_y/vp.height;w->relative_x%=vp.width;w->relative_y%=vp.height;}
   }
   input_state.dx+=e.motion.xrel;input_state.dy+=e.motion.yrel;
   out->message=0x200;out->x=e.motion.x;out->y=e.motion.y;out->lparam=(e.motion.x&65535)|((e.motion.y&65535)<<16);return 1;}
  if(e.type==SDL_MOUSEBUTTONDOWN||e.type==SDL_MOUSEBUTTONUP){unsigned button=e.button.button;int down=e.type==SDL_MOUSEBUTTONDOWN;
   TBWindow *w=event_window(e.button.windowID);if(w&&w->presentation){int x,y;
    int inside=tb_map_mouse(mouse_viewport(w),e.button.x,e.button.y,w->logical_width,w->logical_height,&x,&y);
    if(!inside&&down)continue;e.button.x=x;e.button.y=y;
   }
   if(button==SDL_BUTTON_LEFT)input_state.buttons[0]=down?0x80:0;
   if(button==SDL_BUTTON_RIGHT)input_state.buttons[1]=down?0x80:0;
   if(button==SDL_BUTTON_MIDDLE)input_state.buttons[2]=down?0x80:0;
   if(button!=SDL_BUTTON_LEFT&&button!=SDL_BUTTON_RIGHT&&button!=SDL_BUTTON_MIDDLE)continue;
   out->message=(button==SDL_BUTTON_LEFT?0x201:button==SDL_BUTTON_RIGHT?0x204:0x207)+(down?0:1);
   out->x=e.button.x;out->y=e.button.y;out->lparam=(e.button.x&65535)|((e.button.y&65535)<<16);return 1;}
  if(e.type==SDL_MOUSEWHEEL){input_state.wheel+=e.wheel.y*120;out->message=0x20a;out->wparam=(uint32_t)(e.wheel.y*120)<<16;return 1;}
  if(e.type==SDL_WINDOWEVENT){switch(e.window.event){
   case SDL_WINDOWEVENT_CLOSE:out->message=0x10;return 1;
   case SDL_WINDOWEVENT_FOCUS_LOST:memset(&input_state,0,sizeof(input_state));out->message=8;return 1;
   case SDL_WINDOWEVENT_FOCUS_GAINED:out->message=7;return 1;
   case SDL_WINDOWEVENT_SIZE_CHANGED:out->message=5;out->lparam=(e.window.data1&65535)|((e.window.data2&65535)<<16);return 1;
   default:break;}}
 }return 0;
}
void tb_input_read(TBInput *out,int reset) { *out=input_state;if(reset)input_state.dx=input_state.dy=input_state.wheel=0; }

#ifndef __EMSCRIPTEN__
static void audio_capture_report(TBAudio *audio,int closed) {
 if(!audio->capture_base)return;
 char path[4096];if(snprintf(path,sizeof(path),"%s.json",audio->capture_base)>=(int)sizeof(path))return;
 FILE *report=fopen(path,"wb");if(!report){fprintf(stderr,"Titbit: audio capture metadata failed: %s\n",path);return;}
 unsigned bits=SDL_AUDIO_BITSIZE(audio->spec.format);const char *driver=SDL_GetCurrentAudioDriver();
 fprintf(report,"{\"device\":%u,\"driver\":\"%s\",\"rate\":%d,\"channels\":%u,\"bits\":%u,\"format\":\"%s\",\"bytes\":%llu,\"samples\":%llu,\"nonZeroSamples\":%llu,\"peak\":%u,\"rms\":%.6f,\"writeError\":%s,\"closed\":%s}\n",
 audio->capture_id,driver?driver:"unknown",audio->spec.freq,audio->spec.channels,bits,bits==16?"S16LE":"U8",(unsigned long long)audio->capture_bytes,(unsigned long long)audio->capture_samples,(unsigned long long)audio->capture_nonzero,audio->capture_peak,audio->capture_samples?sqrt(audio->capture_energy/audio->capture_samples):0.0,audio->capture_error?"true":"false",closed?"true":"false");
 if(fclose(report)!=0)fprintf(stderr,"Titbit: audio metadata close failed\n");
}
static void audio_capture_open(TBAudio *audio) {
 const char *directory=getenv("TITBIT_AUDIO_CAPTURE_DIR");if(!directory||!*directory)return;
 if(mkdir(directory,0700)&&errno!=EEXIST){fprintf(stderr,"Titbit: audio capture directory failed: %s\n",directory);return;}
 audio->capture_id=__atomic_add_fetch(&capture_sequence,1,__ATOMIC_RELAXED);char base[4096],path[4096];
 if(snprintf(base,sizeof(base),"%s/device-%03u",directory,audio->capture_id)>=(int)sizeof(base)||snprintf(path,sizeof(path),"%s.pcm",base)>=(int)sizeof(path))return;
 audio->capture_base=strdup(base);audio->capture_file=fopen(path,"wb");
 if(!audio->capture_base||!audio->capture_file){if(audio->capture_file)fclose(audio->capture_file);free(audio->capture_base);audio->capture_base=NULL;audio->capture_file=NULL;fprintf(stderr,"Titbit: audio capture file open failed: %s\n",path);return;}
 setvbuf(audio->capture_file,NULL,_IOFBF,65536);pthread_mutex_lock(&capture_mutex);audio->capture_next=capture_devices;capture_devices=audio;pthread_mutex_unlock(&capture_mutex);
 audio_capture_report(audio,0);
}
static void audio_capture_finish(TBAudio *audio) {
 if(!audio->capture_file)return;
 if(fflush(audio->capture_file)!=0)audio->capture_error=1;
 if(fclose(audio->capture_file)!=0)audio->capture_error=1;
 audio->capture_file=NULL;audio_capture_report(audio,1);
}
static void audio_capture_shutdown(void) {
 pthread_mutex_lock(&capture_mutex);
 for(TBAudio *audio=capture_devices;audio;audio=audio->capture_next){SDL_LockAudioDevice(audio->device);audio_capture_finish(audio);SDL_UnlockAudioDevice(audio->device);}
 pthread_mutex_unlock(&capture_mutex);
}
static void audio_capture_pcm(TBAudio *audio,const Uint8 *stream,int length) {
 if(!audio->capture_file)return;
 size_t written=fwrite(stream,1,(size_t)length,audio->capture_file);audio->capture_bytes+=written;if(written!=(size_t)length)audio->capture_error=1;
 unsigned bits=SDL_AUDIO_BITSIZE(audio->spec.format);size_t samples=written/(bits/8);audio->capture_samples+=samples;
 for(size_t i=0;i<samples;i++){
  int sample;if(bits==16){int16_t word;memcpy(&word,stream+i*2,2);sample=word;}else sample=(int)stream[i]-128;
  unsigned magnitude=(unsigned)(sample<0?-sample:sample);if(magnitude>audio->capture_peak)audio->capture_peak=magnitude;if(magnitude)audio->capture_nonzero++;audio->capture_energy+=(double)sample*sample;
 }
}
static void audio_callback(void *userdata,Uint8 *stream,int length) {
 Uint8 *output=stream;int output_length=length;
 TBAudio *a=userdata;memset(stream,a->spec.silence,(size_t)length);
 while(length>0&&a->first){struct AudioItem *i=a->first;unsigned left=i->header->length-i->offset;
  unsigned take=left<(unsigned)length?left:(unsigned)length;
  unsigned master=__atomic_load_n(&master_volume,__ATOMIC_ACQUIRE);
  int volume=__atomic_load_n(&master_mute,__ATOMIC_ACQUIRE)?0:(int)((uint64_t)a->volume*master/65535);
  SDL_MixAudioFormat(stream,(Uint8*)i->header->data+i->offset,a->spec.format,take,volume);
  stream+=take;length-=(int)take;i->offset+=take;
  if(i->offset==i->header->length){i->header->flags=(i->header->flags&~TB_WAVE_INQUEUE)|TB_WAVE_DONE;a->first=i->next;if(!a->first)a->last=NULL;free(i);}
 }
 audio_capture_pcm(a,output,output_length);
}
TBAudio *tb_audio_open(unsigned rate,unsigned channels,unsigned bits) {
 SDL_AudioSpec want;TBAudio *a;
 if((bits!=8&&bits!=16)||(channels!=1&&channels!=2)||!rate){SDL_SetError("unsupported PCM format");return NULL;}
 if(SDL_InitSubSystem(SDL_INIT_AUDIO)!=0)return NULL;
 a=calloc(1,sizeof(*a));if(!a)return NULL;memset(&want,0,sizeof(want));
 want.freq=(int)rate;want.channels=(Uint8)channels;want.format=bits==16?AUDIO_S16LSB:AUDIO_U8;want.samples=1024;want.callback=audio_callback;want.userdata=a;
 a->volume=SDL_MIX_MAXVOLUME;a->device=SDL_OpenAudioDevice(NULL,0,&want,&a->spec,0);
 if(!a->device){fprintf(stderr,"Titbit: SDL audio open failed (driver=%s, %u Hz/%u channels/%u bits): %s\n",SDL_GetCurrentAudioDriver(),rate,channels,bits,SDL_GetError());free(a);return NULL;}audio_capture_open(a);SDL_PauseAudioDevice(a->device,0);return a;
}
int tb_audio_queue(TBAudio *a,TBWaveHeader *header) {
 struct AudioItem *i;if(!a||!header||!header->data||(header->flags&TB_WAVE_INQUEUE))return 0;
 i=calloc(1,sizeof(*i));if(!i)return 0;i->header=header;
 SDL_LockAudioDevice(a->device);header->flags=(header->flags&~TB_WAVE_DONE)|TB_WAVE_PREPARED|TB_WAVE_INQUEUE;
 if(a->last)a->last->next=i;else a->first=i;a->last=i;SDL_UnlockAudioDevice(a->device);return 1;
}
void tb_audio_reset(TBAudio *a) { struct AudioItem *i;if(!a)return;SDL_LockAudioDevice(a->device);
 while((i=a->first)){i->header->flags=(i->header->flags&~TB_WAVE_INQUEUE)|TB_WAVE_DONE;a->first=i->next;free(i);}a->last=NULL;SDL_UnlockAudioDevice(a->device); }
void tb_audio_close(TBAudio *a) {
 if(!a)return;tb_audio_reset(a);
 pthread_mutex_lock(&capture_mutex);SDL_CloseAudioDevice(a->device);audio_capture_finish(a);
 TBAudio **cursor=&capture_devices;while(*cursor&&*cursor!=a)cursor=&(*cursor)->capture_next;if(*cursor)*cursor=a->capture_next;
 pthread_mutex_unlock(&capture_mutex);free(a->capture_base);free(a);
}
int tb_audio_volume(TBAudio *a,unsigned v) { if(!a||v>128)return 0;SDL_LockAudioDevice(a->device);a->volume=v;SDL_UnlockAudioDevice(a->device);return 1; }
int tb_audio_devices(void) { if(SDL_InitSubSystem(SDL_INIT_AUDIO)!=0)return 0;return SDL_GetNumAudioDevices(0); }
unsigned tb_audio_master_get(void) { return __atomic_load_n(&master_volume,__ATOMIC_ACQUIRE); }
int tb_audio_master_set(unsigned volume) { if(volume>65535)return 0;__atomic_store_n(&master_volume,volume,__ATOMIC_RELEASE);return 1; }
int tb_audio_mute_get(void) { return __atomic_load_n(&master_mute,__ATOMIC_ACQUIRE); }
int tb_audio_mute_set(int mute) { __atomic_store_n(&master_mute,mute!=0,__ATOMIC_RELEASE);return 1; }

#endif

int tb_read_frame_pixels(unsigned char *rgba,size_t capacity,int *width,int *height) {
 SDL_Window *window=SDL_GL_GetCurrentWindow();int w,h;GLint old_buffer,old_pack,row_length,skip_rows,skip_pixels;GLboolean double_buffer;
 if(!window||!SDL_GL_GetCurrentContext()){SDL_SetError("no current game GL context");return 0;}
 SDL_GL_GetDrawableSize(window,&w,&h);if(w<=0||h<=0||w>16384||h>16384)return 0;
 if(width)*width=w;
 if(height)*height=h;
 if(!rgba)return capacity==0;
 if((size_t)w*(size_t)h>capacity/4){SDL_SetError("frame pixel buffer is too small");return 0;}
 while(glGetError()!=GL_NO_ERROR){}
 glGetIntegerv(GL_READ_BUFFER,&old_buffer);glGetIntegerv(GL_PACK_ALIGNMENT,&old_pack);glGetIntegerv(GL_PACK_ROW_LENGTH,&row_length);glGetIntegerv(GL_PACK_SKIP_ROWS,&skip_rows);glGetIntegerv(GL_PACK_SKIP_PIXELS,&skip_pixels);glGetBooleanv(GL_DOUBLEBUFFER,&double_buffer);
 glReadBuffer(double_buffer?GL_BACK:GL_FRONT);glPixelStorei(GL_PACK_ALIGNMENT,1);glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);
 glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,rgba);GLenum error=glGetError();
 glReadBuffer((GLenum)old_buffer);glPixelStorei(GL_PACK_ALIGNMENT,old_pack);glPixelStorei(GL_PACK_ROW_LENGTH,row_length);glPixelStorei(GL_PACK_SKIP_ROWS,skip_rows);glPixelStorei(GL_PACK_SKIP_PIXELS,skip_pixels);
 if(error){SDL_SetError("glReadPixels failed: 0x%x",error);return 0;}return 1;
}
int tb_capture_frame(const char *filename,TBFrameStats *stats) {
 int width,height;if(!filename||!tb_read_frame_pixels(NULL,0,&width,&height))return 0;
 size_t count=(size_t)width*height;unsigned char *pixels=malloc(count*4),*row=malloc((size_t)width*3);if(!pixels||!row){free(pixels);free(row);return 0;}
 if(!tb_read_frame_pixels(pixels,count*4,NULL,NULL)){free(pixels);free(row);return 0;}
 TBFrameStats result={width,height,count,0,0,0,0,0};unsigned char bins[32768]={0};uint64_t sums[3]={0};
 for(size_t i=0;i<count;i++){unsigned char *p=pixels+i*4;sums[0]+=p[0];sums[1]+=p[1];sums[2]+=p[2];if((unsigned)p[0]+p[1]+p[2]>12)result.nonblack++;unsigned bin=((unsigned)(p[0]>>3)<<10)|((unsigned)(p[1]>>3)<<5)|(p[2]>>3);if(!bins[bin]){bins[bin]=1;result.color_bins++;}}
 result.mean_red=(double)sums[0]/count;result.mean_green=(double)sums[1]/count;result.mean_blue=(double)sums[2]/count;
 FILE *file=fopen(filename,"wb");if(!file){free(pixels);free(row);return 0;}int ok=fprintf(file,"P6\n%d %d\n255\n",width,height)>0;
 for(int y=height-1;y>=0&&ok;y--){for(int x=0;x<width;x++)memcpy(row+x*3,pixels+((size_t)y*width+x)*4,3);ok=fwrite(row,1,(size_t)width*3,file)==(size_t)width*3;}
 if(fclose(file)!=0)ok=0;
 free(pixels);free(row);if(stats)*stats=result;return ok;
}
static void capture_selected_frame(void) {
 static int initialized;static const char *directory;static uint64_t selected[32],frame;static unsigned selected_count;
 if(!initialized){initialized=1;directory=getenv("TITBIT_SCREENSHOT_DIR");const char *list=getenv("TITBIT_SCREENSHOT_FRAMES");if(!list)list="100,300,1000";
  while(*list&&selected_count<32){char *end;unsigned long long number=strtoull(list,&end,10);if(end==list)break;if(number)selected[selected_count++]=(uint64_t)number;list=end;if(*list==',')list++;else if(*list)break;}}
 if(!directory||!*directory)return;
 frame++;int selected_frame=0;for(unsigned i=0;i<selected_count;i++)if(selected[i]==frame){selected_frame=1;break;}if(!selected_frame)return;
 if(mkdir(directory,0700)&&errno!=EEXIST){fprintf(stderr,"Titbit: screenshot directory failed: %s\n",directory);return;}
 char path[4096];if(snprintf(path,sizeof(path),"%s/frame-%08llu.ppm",directory,(unsigned long long)frame)>=(int)sizeof(path))return;
 TBFrameStats stats;if(!tb_capture_frame(path,&stats)){fprintf(stderr,"Titbit: screenshot failed: %s\n",tb_error());return;}
 if(snprintf(path,sizeof(path),"%s/frame-%08llu.json",directory,(unsigned long long)frame)>=(int)sizeof(path))return;
 FILE *report=fopen(path,"wb");if(report){fprintf(report,"{\"frame\":%llu,\"width\":%d,\"height\":%d,\"pixels\":%llu,\"nonblackPixels\":%llu,\"meanRGB\":[%.4f,%.4f,%.4f],\"colorBins\":%u}\n",(unsigned long long)frame,stats.width,stats.height,(unsigned long long)stats.pixels,(unsigned long long)stats.nonblack,stats.mean_red,stats.mean_green,stats.mean_blue,stats.color_bins);fclose(report);}
}

/* Windows resource paths are case insensitive and use backslashes. Resolve
 * each existing component against Linux's real directory entries, without
 * changing the current directory or creating alternate copies of assets. */
int tb_resolve_path(const char *source,char *out,size_t capacity,int existing) {
 char normal[PATH_MAX],result[PATH_MAX],*save=NULL,*part;size_t n;int absolute;
 if(!source||!out||!capacity)return 0;
 n=strlen(source);if(n>=sizeof(normal))return 0;
 memcpy(normal,source,n+1);for(size_t j=0;j<n;j++)if(normal[j]=='\\')normal[j]='/';
 if(n>1&&normal[1]==':'){SDL_SetError("Windows drive paths are not native Linux paths");return 0;}
 absolute=normal[0]=='/';strcpy(result,absolute?"/":".");part=strtok_r(normal,"/",&save);
 while(part){char chosen[NAME_MAX+1];DIR *dir;struct dirent *entry;int found=0;
  if(strlen(part)>NAME_MAX)return 0;
  strcpy(chosen,part);
  dir=opendir(result);if(dir){while((entry=readdir(dir)))if(strcmp(entry->d_name,part)==0){strcpy(chosen,entry->d_name);found=1;break;}
   if(!found){rewinddir(dir);while((entry=readdir(dir)))if(strcasecmp(entry->d_name,part)==0){strcpy(chosen,entry->d_name);found=1;break;}}closedir(dir);}
  if(!found&&existing&&strcmp(part,".")&&strcmp(part,"..")){SDL_SetError("path component missing: %s",part);return 0;}
  size_t used=strlen(result),add=strlen(chosen);if(used+add+2>=sizeof(result))return 0;
  if(used&&result[used-1]!='/')strcat(result,"/");
  strcat(result,chosen);part=strtok_r(NULL,"/",&save);
 }
 if(strlen(result)+1>capacity)return 0;
 strcpy(out,result);return 1;
}

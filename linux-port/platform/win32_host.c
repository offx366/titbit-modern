#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "titbit_platform.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/statvfs.h>
#ifndef __EMSCRIPTEN__
#include <sys/vfs.h>
#endif
#include <sys/stat.h>
#if defined(__i386__)
#define WAPI __attribute__((stdcall))
#else
#define WAPI
#endif
extern void WAPI SetLastError(uint32_t);
extern TBWindow *tb_win32_main_window(void);
static const struct {unsigned id;const char *text;} resource_strings[]={
#include "resource_strings.inc"
};
int WAPI LoadStringA(void *module,unsigned id,char *out,int capacity){
 (void)module;if(!out||capacity<=0){SetLastError(87);return 0;}
 for(unsigned i=0;i<sizeof(resource_strings)/sizeof(resource_strings[0]);i++)if(resource_strings[i].id==id){size_t size=strlen(resource_strings[i].text);if(size>=(size_t)capacity)size=(size_t)capacity-1;memcpy(out,resource_strings[i].text,size);out[size]=0;return (int)size;}
 out[0]=0;SetLastError(1814);return 0;
}
int WAPI ProbeEngineLoadStringA(void *module,unsigned id,char *out,int capacity){return LoadStringA(module,id,out,capacity);}
void *WAPI LoadIconA(void *module,const char *id){(void)module;if((uintptr_t)id!=128&&(uintptr_t)id!=202){SetLastError(1813);return NULL;}return tb_project_icon();}
void *WAPI LoadCursorA(void *module,const char *id){(void)module;if((uintptr_t)id!=0x7f00){SetLastError(1813);return NULL;}return tb_arrow_cursor();}
int32_t WAPI MessageBoxA(void *window,const char *message,const char *title,unsigned kind){(void)window;(void)kind;fprintf(stderr,"Titbit [%s]: %s\n",title?title:"error",message?message:"");SetLastError(50);return 0;/* Console error reporting in the Linux port; never block hidden tests. */}
int32_t WAPI CoInitialize(void *reserved){(void)reserved;return (int32_t)0x80004001u;/* COM is not implemented on Linux; Audiere selects waveOut. */}
int32_t WAPI CoCreateInstance(const void *clsid,void *outer,uint32_t context,const void *iid,void **out){(void)clsid;(void)outer;(void)context;(void)iid;if(out)*out=NULL;return (int32_t)0x80040154u;/* REGDB_E_CLASSNOTREG, allowing the existing device fallback. */}
void WAPI CoUninitialize(void){/* A failed CoInitialize creates no COM apartment to tear down. */}
int32_t WAPI ShellExecuteExA(void *request){(void)request;fprintf(stderr,"Titbit: external-document launch is unavailable in this native build\n");SetLastError(50);return 0;}
int WAPI wvsprintfA(char *out,const char *format,char *arguments){
 if(!out||!format){SetLastError(87);return 0;}
#if defined(__EMSCRIPTEN__)
 extern int tb_crt_vsnprintf(char *,size_t,const char *,const void *);
 int result=tb_crt_vsnprintf(out,1024,format,arguments);
 return result<0?0:result>1023?1023:result;
#elif defined(__i386__)
 va_list list;memcpy(&list,&arguments,sizeof(list));int result=vsnprintf(out,1024,format,list);return result<0?0:result>1023?1023:result;
#else
 (void)arguments;SetLastError(50);return 0;
#endif
}
int32_t WAPI EnumDisplaySettingsA(const char *device,uint32_t index,void *output){
 (void)device;if(!output){SetLastError(87);return 0;}uint8_t *mode=output;uint16_t size;memcpy(&size,mode+36,2);if(size<124){SetLastError(87);return 0;}
 int width,height,refresh,bits;if(!tb_display_mode((int32_t)index,&width,&height,&refresh,&bits))return 0;
 memset(mode,0,size);memcpy(mode,"SDL2 Linux display",19);memcpy(mode+36,&size,2);
 uint32_t fields=0x005c0000u;memcpy(mode+40,&fields,4);memcpy(mode+104,&bits,4);memcpy(mode+108,&width,4);memcpy(mode+112,&height,4);memcpy(mode+120,&refresh,4);return 1;
}
int32_t WAPI ChangeDisplaySettingsA(const void *input,uint32_t flags){
 /* Linux compatibility changes the application drawable only. It never
  * changes another application's desktop resolution or the user's monitor. */
 if(flags)return -4;
 if(!input)return 0;
 const uint8_t *mode=input;int width,height;memcpy(&width,mode+108,4);memcpy(&height,mode+112,4);
 if(width<=0||height<=0)return -2;
 TBWindow *window=tb_win32_main_window();if(!window)return 0;
 return tb_window_move(window,0,0,width,height)?0:-1;
}
#ifndef __EMSCRIPTEN__
uint32_t WAPI GetDriveTypeA(const char *root){char path[4096];struct statfs state;if(!root||!tb_resolve_path(root,path,sizeof(path),1)||statfs(path,&state)){SetLastError((uint32_t)errno);return 1;}if((unsigned long)state.f_type==0x9660)return 5;if((unsigned long)state.f_type==0x6969)return 4;if((unsigned long)state.f_type==0x01021994)return 6;return 3;}
int32_t WAPI GetVolumeInformationA(const char *root,char *label,uint32_t label_size,uint32_t *serial,uint32_t *maximum,uint32_t *flags,char *filesystem,uint32_t filesystem_size){
 char path[4096];struct statvfs volume;struct statfs fs;if(!root||!tb_resolve_path(root,path,sizeof(path),1)||statvfs(path,&volume)||statfs(path,&fs)){SetLastError((uint32_t)errno);return 0;}
 if(label&&label_size)label[0]=0;
 if(serial)*serial=(uint32_t)fs.f_fsid.__val[0];
 if(maximum)*maximum=(uint32_t)volume.f_namemax;
 if(flags)*flags=(volume.f_flag&ST_RDONLY)?0x80000u:0;
 if(filesystem&&filesystem_size)snprintf(filesystem,filesystem_size,"Linux-%lx",(unsigned long)fs.f_type);
 return 1;
}
#else
uint32_t GetDriveTypeA(const char *root){(void)root;return 3;}
int32_t GetVolumeInformationA(const char *root,char *label,uint32_t label_size,uint32_t *serial,uint32_t *maximum,uint32_t *flags,char *filesystem,uint32_t filesystem_size){
 (void)root;if(label&&label_size)*label=0;if(serial)*serial=0;if(maximum)*maximum=255;if(flags)*flags=0;
 if(filesystem&&filesystem_size)snprintf(filesystem,filesystem_size,"Browser");return 1;
}
#endif

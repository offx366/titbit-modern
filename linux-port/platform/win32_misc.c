#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <wctype.h>
#include <locale.h>
#include <iconv.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <dlfcn.h>
#include <sys/utsname.h>
#if defined(__i386__)
#define WAPI __attribute__((stdcall))
#else
#define WAPI
#endif
extern void WAPI SetLastError(uint32_t);
int WAPI lstrlenA(const char *text){return text?(int)strlen(text):0;}
int WAPI lstrcmpA(const char *a,const char *b){if(!a)a="";if(!b)b="";int result=strcmp(a,b);return result<0?-1:result>0?1:0;}
static unsigned char lower_byte(unsigned char c){if(c>='A'&&c<='Z')return c+32;if(c>=0xc0&&c<=0xdf)return c+32;if(c==0xa8)return 0xb8;return c;}
char *WAPI CharLowerA(char *text){if((uintptr_t)text<=0xffffu)return (char*)(uintptr_t)lower_byte((unsigned char)(uintptr_t)text);for(unsigned char *p=(unsigned char*)text;*p;p++)*p=lower_byte(*p);return text;}
char *WAPI CharNextA(const char *text){return (char*)(text&&*text?text+1:text);}
/* Game archive text is Windows-1251; report the locale attached to that data,
 * independently of the user's UTF-8 desktop locale. */
uint32_t WAPI GetThreadLocale(void){return 0x419;}
int32_t WAPI GetStringTypeExA(uint32_t locale,uint32_t kind,const char *text,int count,uint16_t *types){
 (void)locale;if(!text||!types||kind!=1||count< -1){SetLastError(87);return 0;}
 if(count==-1)count=(int)strlen(text)+1;
 locale_t unicode=newlocale(LC_CTYPE_MASK,"C.UTF-8",(locale_t)0);iconv_t conversion=iconv_open("WCHAR_T","CP1251");
 if(!unicode||conversion==(iconv_t)-1){if(unicode)freelocale(unicode);SetLastError(87);return 0;}
 for(int i=0;i<count;i++){
  wchar_t character=0;char *input=(char*)text+i,*output=(char*)&character;size_t input_size=1,output_size=sizeof(character);uint16_t flags=0;
  if(iconv(conversion,&input,&input_size,&output,&output_size)==(size_t)-1)character=(unsigned char)text[i];
  if(iswupper_l(character,unicode))flags|=1;
  if(iswlower_l(character,unicode))flags|=2;
  if(iswdigit_l(character,unicode))flags|=4;
  if(iswspace_l(character,unicode))flags|=8;
  if(iswpunct_l(character,unicode))flags|=16;
  if(iswcntrl_l(character,unicode))flags|=32;
  if(character==' '||character=='\t')flags|=64;
  if(iswxdigit_l(character,unicode))flags|=128;
  if(iswalpha_l(character,unicode))flags|=256;
  types[i]=flags;
 }
 iconv_close(conversion);freelocale(unicode);return 1;
}
void *WAPI GetCurrentProcess(void){return (void*)(intptr_t)-1;}
int32_t WAPI FlushInstructionCache(void *process,const void *base,size_t size){
 (void)process;if(!base&&size){SetLastError(87);return 0;}
 /* WebAssembly code is immutable and has no application-visible instruction cache. */
#ifndef __EMSCRIPTEN__
 if(base)__builtin___clear_cache((char*)base,(char*)base+size);
#endif
 return 1;
}
void WAPI DebugBreak(void){raise(SIGTRAP);}
void *WAPI GetModuleHandleA(const char *name){
#ifdef __EMSCRIPTEN__
 if(!name)return (void*)1;SetLastError(126);return NULL;
#else
 void *handle=dlopen(name,RTLD_NOW|RTLD_LOCAL|(name?RTLD_NOLOAD:0));if(!handle)SetLastError(126);return handle;
#endif
}
typedef struct {uint16_t year,month,weekday,day,hour,minute,second,milliseconds;} SystemTime;
void WAPI GetLocalTime(SystemTime *out){if(!out)return;struct timespec time;struct tm local;clock_gettime(CLOCK_REALTIME,&time);localtime_r(&time.tv_sec,&local);*out=(SystemTime){local.tm_year+1900,local.tm_mon+1,local.tm_wday,local.tm_mday,local.tm_hour,local.tm_min,local.tm_sec,time.tv_nsec/1000000};}
typedef struct {uint16_t architecture,reserved;uint32_t page;void *minimum,*maximum;uintptr_t cpu_mask;uint32_t processors,type,granularity;uint16_t level,revision;} SystemInfo;
void WAPI GetSystemInfo(SystemInfo *out){if(!out)return;memset(out,0,sizeof(*out));out->architecture=sizeof(void*)==4?0:9;out->page=(uint32_t)sysconf(_SC_PAGESIZE);out->minimum=(void*)(uintptr_t)0x10000;out->maximum=(void*)(uintptr_t)(sizeof(void*)==4?0xffff0000u:0x7fffffffffffULL);long processors=sysconf(_SC_NPROCESSORS_ONLN);out->processors=processors>0?(uint32_t)processors:1;out->cpu_mask=out->processors>=8*sizeof(uintptr_t)?UINTPTR_MAX:((uintptr_t)1<<out->processors)-1;out->type=586;out->granularity=0x10000;out->level=6;}
typedef struct {uint32_t size,major,minor,build,platform;char text[128];} Version;
int32_t WAPI GetVersionExA(Version *out){if(!out||out->size<sizeof(*out)){SetLastError(87);return 0;}struct utsname system;if(uname(&system)){SetLastError(87);return 0;}char *tail;out->major=(uint32_t)strtoul(system.release,&tail,10);out->minor=*tail=='.'?(uint32_t)strtoul(tail+1,&tail,10):0;out->build=*tail=='.'?(uint32_t)strtoul(tail+1,&tail,10):0;out->platform=4;snprintf(out->text,sizeof(out->text),"Linux %.120s",system.release);return 1;}

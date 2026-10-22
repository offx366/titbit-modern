/* Native Linux I/O behind the fixed VC6 FILE interface used by engine/STL.
 * No glibc FILE pointer is exposed to Windows-layout source code. */
#define _GNU_SOURCE
#include "titbit_platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <ctype.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>

const char titbit_empty_text[]="";
/* The engine's registration wrappers share this one-byte initialization guard.
 * It is separate from GNU libstdc++'s own locale initialization. */
unsigned char titbit_iostream_setup_guard;
static uint32_t random_state=1;
int tb_crt_rand(void){random_state=random_state*214013u+2531011u;return (int)((random_state>>16)&0x7fffu);}
void tb_crt_srand(unsigned seed){random_state=seed;}
static struct timespec clock_origin;
__attribute__((constructor)) static void init_clock(void){clock_gettime(CLOCK_MONOTONIC,&clock_origin);}
int32_t tb_crt_clock(void){struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);return (int32_t)((now.tv_sec-clock_origin.tv_sec)*1000+(now.tv_nsec-clock_origin.tv_nsec)/1000000);}

typedef struct {
    char *pointer;
    int count;
    char *base;
    int flags,descriptor,character,buffer_size;
    char *temporary;
} MSFile;
_Static_assert(sizeof(MSFile)==32,"VC6 FILE must stay 32 bytes");
typedef struct FileEntry {MSFile *view;FILE *native;struct FileEntry *next;} FileEntry;
static pthread_mutex_t file_lock=PTHREAD_MUTEX_INITIALIZER;
static FileEntry *files;
MSFile tb_crt_iob[20];
static FileEntry standard_files[3];
static FILE *native_file(MSFile *view) {
    if(!view)return NULL;
    pthread_mutex_lock(&file_lock);
    FileEntry *entry=files;
    while(entry&&entry->view!=view)entry=entry->next;
    FILE *result=entry?entry->native:NULL;
    pthread_mutex_unlock(&file_lock);
    if(!result)errno=EBADF;
    return result;
}
static void status(MSFile *view,FILE *file) {
    if(ferror(file))view->flags|=0x20;
    if(feof(file))view->flags|=0x10;
}
static MSFile *wrap(FILE *file,int flags) {
    if(!file)return NULL;
    MSFile *view=calloc(1,sizeof(*view));
    FileEntry *entry=malloc(sizeof(*entry));
    if(!view||!entry){free(view);free(entry);fclose(file);errno=ENOMEM;return NULL;}
    view->descriptor=fileno(file);view->flags=flags;
    entry->view=view;entry->native=file;
    pthread_mutex_lock(&file_lock);entry->next=files;files=entry;pthread_mutex_unlock(&file_lock);
    return view;
}
__attribute__((constructor)) static void init_standard_files(void) {
    FILE *native[3]={stdin,stdout,stderr};
    for(int i=0;i<3;++i){
        tb_crt_iob[i].descriptor=i;tb_crt_iob[i].flags=i?2:1;
        standard_files[i]=(FileEntry){&tb_crt_iob[i],native[i],files};files=&standard_files[i];
    }
}
MSFile *tb_crt_fopen(const char *name,const char *mode) {
    char path[4096];
    if(!tb_resolve_path(name,path,sizeof(path),mode[0]=='r')){errno=ENOENT;return NULL;}
    char binary_mode[8];unsigned n=0;
    for(const char *p=mode;*p&&n<sizeof(binary_mode)-1;++p)if(*p!='t')binary_mode[n++]=*p;
    binary_mode[n]=0;
    return wrap(fopen(path,binary_mode),strchr(mode,'+')?0x80:(mode[0]=='r'?1:2));
}
MSFile *tb_crt_tmpfile(void){return wrap(tmpfile(),0x80);}
int tb_crt_fclose(MSFile *view) {
    if(!view){errno=EINVAL;return EOF;}
    pthread_mutex_lock(&file_lock);
    FileEntry **next=&files;while(*next&&(*next)->view!=view)next=&(*next)->next;
    FileEntry *entry=*next;if(entry)*next=entry->next;
    pthread_mutex_unlock(&file_lock);
    if(!entry){errno=EBADF;return EOF;}
    int result=fclose(entry->native);
    if(view<tb_crt_iob||view>=tb_crt_iob+20){free(view);free(entry);}
    return result;
}
size_t tb_crt_fread(void *data,size_t size,size_t count,MSFile *view){FILE*f=native_file(view);if(!f)return 0;size_t n=fread(data,size,count,f);status(view,f);return n;}
size_t tb_crt_fwrite(const void *data,size_t size,size_t count,MSFile *view){FILE*f=native_file(view);if(!f)return 0;size_t n=fwrite(data,size,count,f);status(view,f);return n;}
int tb_crt_fseek(MSFile *view,long offset,int origin){FILE*f=native_file(view);if(!f)return -1;int result=fseek(f,offset,origin);if(!result)view->flags&=~0x10;view->count=0;return result;}
long tb_crt_ftell(MSFile *view){FILE*f=native_file(view);return f?ftell(f):-1;}
int tb_crt_fflush(MSFile *view){if(!view)return fflush(NULL);FILE*f=native_file(view);return f?fflush(f):EOF;}
int tb_crt_fgetc(MSFile *view){FILE*f=native_file(view);if(!f)return EOF;int c=fgetc(f);status(view,f);return c;}
int tb_crt_fputc(int c,MSFile *view){FILE*f=native_file(view);if(!f)return EOF;int result=fputc(c,f);status(view,f);return result;}
char *tb_crt_fgets(char *data,int count,MSFile *view){FILE*f=native_file(view);if(!f)return NULL;char*result=fgets(data,count,f);status(view,f);return result;}
int tb_crt_fputs(const char *data,MSFile *view){FILE*f=native_file(view);if(!f)return EOF;return fputs(data,f);}
int tb_crt_ungetc(int c,MSFile *view){FILE*f=native_file(view);if(!f)return EOF;int result=ungetc(c,f);if(result!=EOF)view->flags&=~0x10;return result;}
int tb_crt_setvbuf(MSFile *view,char *buffer,int mode,size_t size){FILE*f=native_file(view);if(!f)return -1;int native_mode=mode==4?_IONBF:(mode==0x40?_IOLBF:_IOFBF);return setvbuf(f,buffer,native_mode,size);}
#ifndef __EMSCRIPTEN__
int tb_crt_vfprintf(MSFile *view,const char *format,va_list arguments){FILE*f=native_file(view);return f?vfprintf(f,format,arguments):-1;}
int tb_crt_fprintf(MSFile *view,const char *format,...){va_list args;va_start(args,format);int n=tb_crt_vfprintf(view,format,args);va_end(args);return n;}
#else
FILE *tb_crt_native_file(void *view){return native_file((MSFile*)view);}
#endif
int tb_crt_feof(MSFile *view){return (view->flags&0x10)!=0;}
int tb_crt_ferror(MSFile *view){return (view->flags&0x20)!=0;}
int tb_crt_fileno(MSFile *view){return view?view->descriptor:-1;}
int tb_crt_fgetpos(MSFile *view,int64_t *position){FILE*f=native_file(view);if(!f)return -1;off_t n=ftello(f);if(n<0)return -1;*position=n;return 0;}
int tb_crt_fsetpos(MSFile *view,const int64_t *position){FILE*f=native_file(view);if(!f)return -1;int result=fseeko(f,*position,SEEK_SET);if(!result){view->flags&=~0x10;view->count=0;}return result;}
int tb_crt_filbuf(MSFile *view){return tb_crt_fgetc(view);}
int tb_crt_flsbuf(int c,MSFile *view){return tb_crt_fputc(c,view);}
long tb_crt_filelength(int descriptor){struct stat st;return fstat(descriptor,&st)?-1:(long)st.st_size;}
typedef struct {uint32_t device;uint16_t inode,mode;int16_t links,uid,gid;uint16_t padding;uint32_t rdevice;int32_t size,atime,mtime,ctime;} MSStat;
_Static_assert(sizeof(MSStat)==36,"VC6 stat must stay 36 bytes");
int tb_crt_stat(const char *name,MSStat *out){char path[4096];struct stat st;if(!tb_resolve_path(name,path,sizeof(path),1)||stat(path,&st))return -1;*out=(MSStat){st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_uid,st.st_gid,0,st.st_rdev,st.st_size,st.st_atim.tv_sec,st.st_mtim.tv_sec,st.st_ctim.tv_sec};return 0;}
int *tb_crt_errno(void){return &errno;}
int tb_crt_mb_cur_max=1;
static unsigned short ctypes[257];
unsigned short *tb_crt_pctype=ctypes+1;
__attribute__((constructor)) static void init_ctype(void){for(int c=0;c<256;++c){unsigned mask=0;if(isupper(c))mask|=1;if(islower(c))mask|=2;if(isdigit(c))mask|=4;if(isspace(c))mask|=8;if(ispunct(c))mask|=16;if(iscntrl(c))mask|=32;if(c==' '||c=='\t')mask|=64;if(isxdigit(c))mask|=128;if(isalpha(c))mask|=256;ctypes[c+1]=mask;}}
int tb_crt_isctype(int c,int mask){return c>=-1&&c<256?tb_crt_pctype[c]&mask:0;}
size_t tb_crt_wcslen(const uint16_t *s){const uint16_t*p=s;while(*p)++p;return p-s;}
char *tb_crt_itoa(int value,char *out,int base){if(base<2||base>36){errno=EINVAL;*out=0;return out;}char tmp[35];unsigned n=0,v=(unsigned)value;int negative=value<0&&base==10;if(negative)v=0-v;do{unsigned d=v%(unsigned)base;tmp[n++]=(char)(d<10?'0'+d:'a'+d-10);v/=base;}while(v);char*p=out;if(negative)*p++='-';while(n)*p++=tmp[--n];*p=0;return out;}
int64_t __attribute__((stdcall)) _alldiv(int64_t a,int64_t b){return a/b;}
uint64_t __attribute__((stdcall)) _aulldiv(uint64_t a,uint64_t b){return a/b;}

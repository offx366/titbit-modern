/* Convert the engine's MS x86 packed va_list to the native Wasm libc layout.
 * Native platform code continues to use its own ordinary C varargs ABI. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <ctype.h>

_Static_assert(sizeof(va_list)==sizeof(void*), "Wasm32 pointer va_list required");
extern FILE *tb_crt_native_file(void *);
typedef struct {char *format;unsigned char *arguments;} FormatArgs;
static int add_argument(unsigned char *to,size_t *used,const unsigned char **from,unsigned size) {
    unsigned alignment=size==8?8:4;
    *used=(*used+alignment-1)&~(size_t)(alignment-1);
    memcpy(to+*used,*from,size);*used+=size;*from+=(size+3)&~3u;return 1;
}
static FormatArgs convert_format(const char *format,const void *arguments) {
    FormatArgs result={0};if(!format){errno=EINVAL;return result;}
    size_t length=strlen(format),written=0,used=0;
    result.format=malloc(length+1);result.arguments=malloc(length*16+16);
    if(!result.format||!result.arguments)goto fail;
    const unsigned char *from=arguments;
    for(size_t i=0;i<length;i++) {
        result.format[written++]=format[i];
        if(format[i]!='%')continue;
        if(format[i+1]=='%'){result.format[written++]=format[++i];continue;}
        int wide=0;
        for(++i;i<length;++i) {
            char c=format[i];
            if(c=='$'){errno=EINVAL;goto fail;}
            if(c=='*')add_argument(result.arguments,&used,&from,4);
            if(c=='I'&&format[i+1]=='6'&&format[i+2]=='4') {
                result.format[written++]='l';result.format[written++]='l';i+=2;wide=1;continue;
            }
            if(c=='l'&&format[i+1]=='l') {
                result.format[written++]='l';result.format[written++]='l';++i;wide=1;continue;
            }
            if(c=='j')wide=1;
            if(c=='L')continue; // MS x86 long double is the ordinary 64-bit double.
            result.format[written++]=c;
            if(strchr("aAeEfFgG",c)){add_argument(result.arguments,&used,&from,8);break;}
            if(strchr("diouxX",c)){add_argument(result.arguments,&used,&from,wide?8:4);break;}
            if(strchr("cspn",c)){add_argument(result.arguments,&used,&from,4);break;}
        }
    }
    result.format[written]=0;return result;
fail:
    free(result.format);free(result.arguments);result.format=NULL;result.arguments=NULL;return result;
}
static va_list native_list(void *pointer) {va_list list;memcpy(&list,&pointer,sizeof(list));return list;}
int tb_crt_vsnprintf(char *out,size_t capacity,const char *format,void *arguments) {
    FormatArgs converted=convert_format(format,arguments);if(!converted.format)return -1;
    int result=vsnprintf(out,capacity,converted.format,native_list(converted.arguments));
    free(converted.format);free(converted.arguments);return result;
}
int tb_crt_vsprintf(char *out,const char *format,void *arguments) {
    FormatArgs converted=convert_format(format,arguments);if(!converted.format)return -1;
    int result=vsprintf(out,converted.format,native_list(converted.arguments));
    free(converted.format);free(converted.arguments);return result;
}
int tb_crt_vprintf(const char *format,void *arguments) {
    FormatArgs converted=convert_format(format,arguments);if(!converted.format)return -1;
    int result=vprintf(converted.format,native_list(converted.arguments));
    free(converted.format);free(converted.arguments);return result;
}
int tb_crt_vfprintf(void *view,const char *format,void *arguments) {
    FILE *file=tb_crt_native_file(view);if(!file)return -1;
    FormatArgs converted=convert_format(format,arguments);if(!converted.format)return -1;
    int result=vfprintf(file,converted.format,native_list(converted.arguments));
    free(converted.format);free(converted.arguments);return result;
}
int titbit_va_tb_crt_printf(const char *format,void *args){return tb_crt_vprintf(format,args);}
int titbit_va_tb_crt_sprintf(char *out,const char *format,void *args){return tb_crt_vsprintf(out,format,args);}
int titbit_va_tb_crt_snprintf(char *out,size_t capacity,const char *format,void *args){return tb_crt_vsnprintf(out,capacity,format,args);}
int titbit_va_tb_crt_fprintf(void *view,const char *format,void *args){return tb_crt_vfprintf(view,format,args);}
// scanf variadics contain only 32-bit destination pointers in both ABIs.
int titbit_va_tb_crt_sscanf(const char *text,const char *format,void *args){return vsscanf(text,format,native_list(args));}
int titbit_va_tb_crt_fscanf(void *view,const char *format,void *args){FILE*f=tb_crt_native_file(view);return f?vfscanf(f,format,native_list(args)):-1;}
int titbit_va_tb_crt_scanf(const char *format,void *args){return vscanf(format,native_list(args));}

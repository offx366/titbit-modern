#ifndef TITBIT_PORTABLE_SETJMP_H
#define TITBIT_PORTABLE_SETJMP_H
typedef int jmp_buf[16];
#include <titbit_crt.h>
TB_EXTERN_C_BEGIN
#ifdef TITBIT_WASM_SOURCE
int setjmp(jmp_buf) __attribute__((returns_twice));
void longjmp(jmp_buf,int) __attribute__((noreturn));
#else
int _setjmp3(jmp_buf,int,...);void longjmp(jmp_buf,int);
#endif
TB_EXTERN_C_END
#ifndef TITBIT_WASM_SOURCE
#define setjmp(b) _setjmp3(b,0)
#endif
#endif

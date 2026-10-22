#ifndef TITBIT_PORTABLE_STDARG_H
#define TITBIT_PORTABLE_STDARG_H
typedef __builtin_va_list va_list;
#define _VA_LIST_DEFINED
#define va_start(ap,last) __builtin_va_start(ap,last)
#define va_end(ap) __builtin_va_end(ap)
/* SeeR takes the address of va_arg: retain the x86 slot lvalue. Slots are
 * only 4-byte aligned, including double/int64; do not promise natural alignment
 * to the optimizer when dereferencing a slot. */
#define va_arg(ap,type) (*(type __unaligned *)(((ap)+=((sizeof(type)+3)&~3))-((sizeof(type)+3)&~3)))
#define va_copy(dst,src) ((dst)=(src))
#endif

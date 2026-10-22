#ifndef TITBIT_WEB_VARARGS_PROBE_H
#define TITBIT_WEB_VARARGS_PROBE_H
#include <stdarg.h>

struct WebSlots { int first; double second; int third; };
struct WebLeft { int left; };
struct WebRight { int value; int add(int x) { return value + x; } };
struct WebMember : WebLeft, WebRight {};
typedef int (*WebVariadic)(int, ...);
extern "C" {
int web_scan_varargs(int tag, ...);
int web_scan_copy(int tag, ...);
int web_scan_struct(int tag, ...);
int web_scan_empty(int tag, ...);
int web_scan_recursive(int depth, ...);
double web_scan_double(int tag, ...);
int web_scan_member(int tag, ...);
WebSlots web_return_struct(int tag, ...);
extern WebVariadic volatile web_varargs_pointer;
}
#endif

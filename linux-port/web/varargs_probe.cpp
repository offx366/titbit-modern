#include "varargs_probe.h"

// The caller is in a separate translation unit: no frontend constant folding
// or inlining can hide a disagreement about argument slots or Wasm signatures.
extern "C" int web_scan_varargs(int tag, ...) {
    va_list args;
    va_start(args, tag);
    int first = va_arg(args, int);
    double second = va_arg(args, double);
    const char *third = va_arg(args, const char *);
    __int64 fourth = va_arg(args, __int64);
    int *fifth = (int *)&va_arg(args, int);
    va_end(args);
    if (first != 17) return 1;
    if (second != 42.5) return 2;
    if (*third != 'q') return 3;
    if (fourth != 0x1234567812345678LL) return 4;
    if (*fifth != 29) return 5;
    return 0;
}

static int scan_forwarded(va_list args) {
    int *first = (int *)&va_arg(args, int);
    double second = va_arg(args, double);
    int third = va_arg(args, int);
    return *first == 17 && second == 42.5 && third == 29 ? 0 : 1;
}

extern "C" int web_scan_copy(int tag, ...) {
    va_list args, copy;
    va_start(args, tag);
    va_copy(copy, args);
    int result = scan_forwarded(copy);
    result |= scan_forwarded(args); // The original list must remain unconsumed.
    va_end(copy);
    va_end(args);
    return result;
}

extern "C" int web_scan_struct(int tag, ...) {
    va_list args;
    va_start(args, tag);
    int first = va_arg(args, int);
    WebSlots value = va_arg(args, WebSlots);
    int last = va_arg(args, int);
    va_end(args);
    return first == 17 && value.first == 3 && value.second == 42.5 &&
        value.third == 7 && last == 29 ? 0 : 1;
}

extern "C" int web_scan_empty(int tag, ...) {
    va_list args;
    va_start(args, tag);
    va_end(args);
    return tag == 1 ? 0 : 1;
}

extern "C" int web_scan_recursive(int depth, ...) {
    va_list args;
    va_start(args, depth);
    int first = va_arg(args, int);
    // Consume double after returning: nested frames must not overwrite ours.
    int nested = depth ? web_scan_recursive(depth - 1, first + 1, 42.5) : 0;
    double second = va_arg(args, double);
    va_end(args);
    return nested || first + depth != 25 || second != 42.5;
}

extern "C" double web_scan_double(int tag, ...) {
    va_list args;
    va_start(args, tag);
    int first = va_arg(args, int);
    double second = va_arg(args, double);
    va_end(args);
    return first + second;
}

extern "C" WebSlots web_return_struct(int tag, ...) {
    va_list args;
    va_start(args, tag);
    WebSlots value = va_arg(args, WebSlots);
    va_end(args);
    return value;
}

extern "C" int web_scan_member(int tag, ...) {
    va_list args;
    va_start(args, tag);
    typedef int (WebMember::*Method)(int);
    Method method = va_arg(args, Method);
    WebMember *object = va_arg(args, WebMember *);
    va_end(args);
    return (object->*method)(5) == 42 ? 0 : 1;
}

extern "C" {
WebVariadic volatile web_varargs_pointer = web_scan_varargs;
}

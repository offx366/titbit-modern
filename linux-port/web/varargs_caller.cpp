#include "varargs_probe.h"

extern "C" int probe_varargs() {
    int result = web_scan_varargs(1, 17, 42.5, "quest", 0x1234567812345678LL, 29);
    if (result) return result;
    result = web_varargs_pointer(1, 17, 42.5, "quest", 0x1234567812345678LL, 29);
    if (result) return 10 + result;
    if (web_scan_copy(1, 17, 42.5, 29)) return 20;
    WebSlots slots = {3, 42.5, 7};
    if (web_scan_struct(1, 17, slots, 29)) return 21;
    if (web_scan_empty(1)) return 22;
    if (web_scan_recursive(8, 17, 42.5)) return 23;
    if (web_scan_double(1, 17, 42.5) != 59.5) return 24;
    WebSlots returned = web_return_struct(1, slots);
    if (returned.first != 3 || returned.second != 42.5 || returned.third != 7) return 25;
    WebMember member;
    member.left = -1;
    member.value = 37;
    int (WebMember::*method)(int) = &WebRight::add;
    if (web_scan_member(1, method, &member)) return 26;
    // More than the module's stack size if buffers accumulate inside the loop.
    for (int i = 0; i < 50000; ++i) {
        if (web_varargs_pointer(1, 17, 42.5, "quest", 0x1234567812345678LL, 29)) return 27;
    }
    return 0;
}

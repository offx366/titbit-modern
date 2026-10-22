// Compiler experiment, independent of the game and of Windows SDK headers.
// Native Linux main calls this with the plain C ABI.
struct Vec { float x, y, z; };
struct Base {
    int id;
    virtual ~Base() {}
    virtual int value() { return id; }
};
struct Derived : Base {
    Vec pos;
    Derived() { id=31; pos.x=1;pos.y=2;pos.z=3; }
    virtual int value() { return id+int(pos.x+pos.y+pos.z); }
};
struct __declspec(align(8)) Aligned { char c; double d; };
struct Mixed { char c; double d; int i; };
__declspec(noinline) int __stdcall stdcall_add(int a,int b) { return a+b; }
__declspec(noinline) int __thiscall explicit_thiscall_add(Base* b,int n) { return b->id+n; }
__declspec(noinline) int virtual_value(Base *p) { return p->value(); }
extern "C" int probe_run() {
    Derived d;
    Base *p=&d;
    if (sizeof(void*)!=4 || sizeof(long)!=4 || sizeof(Base)!=8 || sizeof(Derived)!=20)
        return 1;
    if (virtual_value(p)!=37) return 2;
    if (stdcall_add(3,4)!=7) return 3;
    if (explicit_thiscall_add(p,5)!=36) return 4;
    Mixed mixed;
    mixed.c=1;
    mixed.d=42;
    mixed.i=123;
    volatile int runtime_offset=8;
    if (*(double*)((char*)&mixed+runtime_offset)!=42) return 5;
    if (sizeof(Mixed)!=24) return 6;
    return 0;
}
// Give Microsoft scalar deleting destructors a native implementation.
void operator delete(void*) noexcept {}

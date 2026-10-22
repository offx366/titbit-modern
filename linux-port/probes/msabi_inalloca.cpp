extern "C" int native_stack_align();
extern "C" {int live_words;int inalloca_alignment_errors;}
struct Word {
    int value;
    __declspec(noinline) Word(int v):value(v) {++live_words;}
    __declspec(noinline) Word(const Word& w):value(w.value) {++live_words;}
    __declspec(noinline) ~Word() {--live_words;}
};
struct Large {
    int x,y,z;
    Large(int a,int b,int c):x(a),y(b),z(c) {}
    __declspec(noinline) Large(const Large& v):x(v.x),y(v.y),z(v.z) {}
    __declspec(noinline) ~Large() {}
};
class Receiver {
    int magic;
public:
    Receiver():magic(100) {}
    __declspec(noinline) Word small(Word first,int n,Word last) {
#ifndef TITBIT_WASM_PROBE
        inalloca_alignment_errors+=native_stack_align()!=0;
#endif
        return Word(magic+first.value+n+last.value);
    }
    __declspec(noinline) Large large(Word first,Large second,double d) {
#ifndef TITBIT_WASM_PROBE
        inalloca_alignment_errors+=native_stack_align()!=0;
#endif
        return Large(first.value+second.x,second.y+int(d),second.z+magic);
    }
};
extern "C" int probe_inalloca() {
    live_words=inalloca_alignment_errors=0;
    int failed=0;
    {
        Receiver receiver;
        Word a(2),b(3);
        Word result=receiver.small(a,5,b);
        if(result.value!=110)failed=1;
        Large large=receiver.large(result,Large(7,8,9),42.0);
        if(large.x!=117 || large.y!=50 || large.z!=109)failed=2;
    }
    if(live_words!=0)failed=3;
    if(inalloca_alignment_errors)failed=4;
    return failed;
}

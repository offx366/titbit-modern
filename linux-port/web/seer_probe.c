/* Run the original SeeR Executor in Wasm. This harness is not the game runtime. */
#define INTERNAL_FILE
#include "../src/seer/seer.h"
#include "../src/seer/internal.h"
#include "../src/seer/code.h"

scInstance *scActual_Instance;
int scErrorNo, scParamCount;
scFunctionDispatcher scUserFunctionDispatcher[SC_MAX_FUNCTION_DISPATCHERS];
static unsigned char code[512];
static double storage[512]; /* double alignment, 256 registers then stack */
static scInstance instance;
static int position, callback_count;

void *memcpy(void *to, const void *from, unsigned size) {
    unsigned char *d = to;
    const unsigned char *s = from;
    while (size--) *d++ = *s++;
    return to;
}

/* These paths need instance management in the eventual game port. A probe
 * must fail explicitly if it accidentally reaches an unsupported path. */
void scRuntime_Error(char *message, ...) { (void)message; scErrorNo = scErr_Runtime; }
scInstance *scFork_Instance(scInstance *i) { (void)i; __builtin_trap(); }
void scFree_Instance(scInstance *i) { (void)i; __builtin_trap(); }
int scLaunch_Instance_GOTO(scInstance *i, int speed, int address) {
    (void)i; (void)speed; (void)address; __builtin_trap();
}
int scVCall_Instance(scInstance *i, int address, int size, int *params) {
    (void)i; (void)address; (void)size; (void)params; __builtin_trap();
}

__declspec(noinline) static int add(int a, int b) { return a + b; }
__declspec(noinline) static double scale(double value, int factor) { return value * factor; }

/* A typed adapter reads packed SeeR slots. Never call a Wasm table entry
 * through a guessed function type: Wasm checks signatures at runtime. */
static void dispatch(int *result, void *function, int *params, int bytes, unsigned options) {
    ++callback_count;
    if (function == (void *)&add && bytes == 8 && options == 8) {
        *result = add(params[0], params[1]);
    } else if (function == (void *)&scale && bytes == 12 && options == (12 | scDispatch_Double)) {
        double value;
        memcpy(&value, params, 8);
        value = scale(value, params[2]);
        memcpy(result, &value, 8);
    } else {
        scErrorNo = scErr_Runtime;
        __builtin_trap();
    }
}

static void word(int value) { memcpy(code + position, &value, 4); position += 4; }
static void real(double value) { memcpy(code + position, &value, 8); position += 8; }
static void begin(void) {
    int i;
    for (i = 0; i < 512; ++i) { code[i] = 0; storage[i] = 0; }
    instance.code = (char *)code;
    instance.data_stack = (char *)storage;
    instance.flags.forkno = instance.flags.paused = 0;
    ((int *)storage)[regSS] = (int)((char *)storage + 1024);
    ((int *)storage)[regSP] = ((int *)storage)[regCP] = 2048;
    /* Keep import addresses outside the program's instruction bytes. */
    ((int *)code)[hdrImportedOffset] = 480;
    position = 80;
    ((int *)storage)[regIP] = position;
    scErrorNo = callback_count = 0;
    scUserFunctionDispatcher[0] = dispatch;
}

int probe_seer(void) {
    int result, first;
    begin();
    word(opvcpuMOV | (1 << 8)); word(6);  /* a0 = 6 */
    word(opvcpuMUL | (1 << 8)); word(7);  /* a0 *= 7 */
    word(opvcpuRET);
    result = Executor(&instance, -1);
    if (result != 1 || scErrorNo || ((int *)storage)[0] != 42) return 1;

    begin();
    memcpy(code + 480, &(void *){(void *)&add}, 4);
    word(opvcpuPUSH); word(19);
    word(opvcpuPUSH); word(23);
    word(opvcpuCALLEX); word(0); word(8);
    word(opvcpuRET);
    result = Executor(&instance, -1);
    if (result != 1 || scErrorNo || ((int *)storage)[0] != 42 || callback_count != 1) return 2;
    if (((int *)storage)[regSP] != 2048) return 3;

    begin();
    memcpy(code + 480, &(void *){(void *)&scale}, 4);
    word(opvcpuPUSH); word(4);
    word(opvcpuDPUSH); real(10.5);
    word(opvcpuCALLEX); word(0); word(12 | scDispatch_Double);
    word(opvcpuRET);
    result = Executor(&instance, -1);
    if (result != 1 || scErrorNo || storage[0] != 42.0 || callback_count != 1) return 4;
    if (((int *)storage)[regSP] != 2048) return 5;

    begin();
    word(opvcpuMOV | (1 << 8)); word(17);
    word(opvcpuEXPR);
    word(opvcpuADD | (1 << 8)); word(25);
    word(opvcpuRET);
    first = Executor(&instance, 1);
    if (first != 0 || ((int *)storage)[0] != 17) return 6;
    result = Executor(&instance, -1);
    if (result != 1 || scErrorNo || ((int *)storage)[0] != 42) return 7;

    begin();
    word(255); /* a malformed opcode must report an interpreter error */
    if (Executor(&instance, -1) != -1 || scErrorNo != scErr_Runtime) return 8;
    return 0;
}

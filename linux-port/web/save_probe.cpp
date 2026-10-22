// The original engine serializer runs unchanged. Browser I/O is supplied by
// four typed host imports; persistence is awaited by the JS controller.
#include "../src/lanes/engine41/quest_state.h"
static_assert(sizeof(QuestState) == 408, "Original save format must remain unchanged");

// The original destructor is empty/shared. This probe has process-lifetime
// state and needs no native exit-handler registry.
QuestState::~QuestState() {}
extern "C" int atexit(void (*)()) { return 0; }
extern "C" void *memset(void *to, int value, unsigned count) {
    unsigned char *data = (unsigned char *)to;
    while (count--) *data++ = (unsigned char)value;
    return to;
}
extern "C" void *memcpy(void *to, const void *from, unsigned count) {
    unsigned char *data = (unsigned char *)to;
    const unsigned char *source = (const unsigned char *)from;
    while (count--) *data++ = *source++;
    return to;
}

extern "C" unsigned save_state_address() { return (unsigned)&g_005024b0; }
extern "C" unsigned save_state_size() { return sizeof(g_005024b0); }
extern "C" void save_state_reset() { memset(&g_005024b0, 0, sizeof(g_005024b0)); }
extern "C" int save_write() { return g_005024b0.SaveGame_0041e590("browser.sav"); }
extern "C" int save_read() { return g_005024b0.LoadGame_0041e5e0("browser.sav"); }

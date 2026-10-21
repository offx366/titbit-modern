// Linux startup uses the reconstructed scene/game loop and SDL platform APIs.
// Compile this file with the same Microsoft object ABI as the engine.
#include "../src/native/engine_string.h"
#include "../src/native/picking_control_interfaces.h"

extern "C" {
int CreateGameWindow(const char *, int, int);
int InitGameInput(void *, void *);
void ShutdownGameWindow();
void CloseApp();
void ShellExecuteScriptRegistrationTarget(const char *);
void RunGameFrame();
void scAdd_External_Symbol(char *, void *);
int tb_linux_poll();
void tb_linux_report(unsigned frames);
unsigned tb_linux_frame_limit();
int tb_linux_has_assets();
int tb_linux_test_stop();
const char *tb_linux_start_scene();
}
extern bool gameActive;
extern int displayWidth, displayHeight;
extern void *gameWindow;
int SetArchiveRoot(const char *);
int MountArchive(const char *);

extern "C" int titbit_linux_run() {
    if (!tb_linux_has_assets()) return 2;
    displayWidth = 1024;
    displayHeight = 768;
    if (!CreateGameWindow("Ядерный титбит", displayWidth, displayHeight)) return 3;
    if (!InitGameInput(0, gameWindow)) return 4;
    scAdd_External_Symbol((char *)"CloseApp", (void *)&CloseApp);
    scAdd_External_Symbol((char *)"ShellExecute", (void *)&ShellExecuteScriptRegistrationTarget);
    SetArchiveRoot("./");
    if (!MountArchive("QUEST.EZD")) return 5;
    picking_scene.Load(ObservedString(tb_linux_start_scene()));
    unsigned frames = 0, limit = tb_linux_frame_limit();
    while (tb_linux_poll()) {
        if (gameActive) {
            RunGameFrame();
            ++frames;
            if ((limit && frames >= limit) || tb_linux_test_stop()) break;
        }
    }
    tb_linux_report(frames);
    ShutdownGameWindow();
    return 0;
}

// Microsoft-layout engine boundary; the browser owns the event/frame loop.
#include "../src/native/engine_string.h"
#include "../src/native/picking_control_interfaces.h"
#include <string.h>
extern "C" {
int CreateGameWindow(const char *, int, int);
int InitGameInput(void *, void *);
void CloseApp();
void ShellExecuteScriptRegistrationTarget(const char *);
void RunGameFrame();
void SetGameSpeed(float);
void scAdd_External_Symbol(char *, void *);
void titbit_linux_initialize_pod_globals();
int tb_linux_poll();
void tb_web_phase(const char *);
}
extern bool gameActive;
extern int displayWidth, displayHeight;
extern void *gameWindow;
int SetArchiveRoot(const char *);
int MountArchive(const char *);
class BrowserSceneView {public: void AddObject_00425860(void *,int);};
void *CreateGameObject_0040ecd0(int,const char *,float,float,float,float,float,float);

// Use the engine's compiler/instance linker for script QA without sending any
// game events. The exact holder layout is shared with engine41/script_objects.
class ScriptHolder {
public:
    void *program, *instance;
    int handlers[13];
    ScriptHolder();
    virtual ~ScriptHolder();
    bool Compile_0041a7f0(ObservedString file);
};
extern "C" int titbit_web_check_script(const char *file) {
    ScriptHolder script;
    return script.Compile_0041a7f0(ObservedString(file)) ? 1 : 0;
}

extern "C" int titbit_web_initialize(const char *scene) {
    tb_web_phase("Инициализация движка");
    titbit_linux_initialize_pod_globals();
    displayWidth = 1024; displayHeight = 768;
    if (!CreateGameWindow("Ядерный Титбит", displayWidth, displayHeight)) return 3;
    if (!InitGameInput(0, gameWindow)) return 4;
    scAdd_External_Symbol((char *)"CloseApp", (void *)&CloseApp);
    scAdd_External_Symbol((char *)"ShellExecute", (void *)&ShellExecuteScriptRegistrationTarget);
    SetArchiveRoot("/game/");
    tb_web_phase("Открытие QUEST.ezd");
    if (!MountArchive("/game/QUEST.ezd")) return 5;
    tb_web_phase("Загрузка сцены");
    // Restore the original Buka -> VZ Lab -> intro -> menu startup sequence.
    // The explicit bootstrap entry is reserved for the scene QA harness.
    const bool bootstrap = scene && !strcmp(scene, "browser_start.scv");
    picking_scene.Load(ObservedString(bootstrap ? "menu.xml" : (scene ? scene : "startup.XML")));
    if (bootstrap) {
        void *object=CreateGameObject_0040ecd0(1,"browser_start.scv",0,0,0,0,0,0);
        ((BrowserSceneView *)&picking_scene)->AddObject_00425860(object,2);
    }
    SetGameSpeed(1);
    gameActive = true;
    tb_web_phase("Сцена загружена");
    return 0;
}
extern "C" void titbit_web_frame() {
    if (tb_linux_poll() && gameActive) RunGameFrame();
}

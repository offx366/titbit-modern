#include "titbit_platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

typedef struct { void *window; unsigned message,wparam; int lparam; unsigned time; int x,y; } GameMessage;
#if defined(__i386__)
#define WAPI __attribute__((stdcall))
#else
#define WAPI
#endif
extern int titbit_linux_run(void);
extern void titbit_linux_initialize_pod_globals(void);
extern int WAPI PeekMessageA(GameMessage *,void *,unsigned,unsigned,unsigned);
extern int WAPI TranslateMessage(const GameMessage *);
extern int WAPI DispatchMessageA(const GameMessage *);
int tb_linux_poll(void) {
    GameMessage message;
    while (PeekMessageA(&message,0,0,0,1)) {
        if (message.message==0x12) return 0;
        TranslateMessage(&message);
        DispatchMessageA(&message);
    }
    return 1;
}
int tb_linux_test_stop(void) {
    const char *path=getenv("TITBIT_TEST_STOP_FILE");
    return path && *path && access(path,F_OK)==0;
}
unsigned tb_linux_frame_limit(void) {
    const char *value=getenv("TITBIT_TEST_FRAMES");
    return value ? (unsigned)strtoul(value,0,10) : 0;
}
int tb_linux_has_assets(void) {
    char path[4096];
    if (tb_resolve_path("QUEST.EZD",path,sizeof(path),1)) return 1;
    fprintf(stderr,"QUEST.EZD is missing. Import your game files with tools/import_assets.sh.\n");
    return 0;
}
void tb_linux_report(unsigned frames) {
    fprintf(stderr,"Titbit Linux: completed %u game frames\n",frames);
}
const char *tb_linux_start_scene(void) {
    const char *allowed=getenv("TITBIT_WIDESCREEN_VALIDATION");
    const char *scene=getenv("TITBIT_VALIDATE_SCENE");
    return allowed && !strcmp(allowed,"1") && scene && *scene ? scene : "startup.XML";
}
int main(int argc,char **argv) {
    for(int i=1;i<argc;++i) {
        if(!strcmp(argv[i],"--data") && i+1<argc) {
            if(chdir(argv[++i])) {perror("--data");return 2;}
        } else if(!strcmp(argv[i],"--windowed")) {
            setenv("TITBIT_FULLSCREEN","0",1);
        } else if(!strcmp(argv[i],"--fullscreen")) {
            setenv("TITBIT_FULLSCREEN","1",1);
        } else if(!strcmp(argv[i],"--widescreen") || !strcmp(argv[i],"--widescreen=16:9")) {
            setenv("TITBIT_WIDESCREEN","16:9",1);
        } else if(!strcmp(argv[i],"--widescreen=16:10")) {
            setenv("TITBIT_WIDESCREEN","16:10",1);
        } else if(!strcmp(argv[i],"--validate-scene") && i+1<argc) {
            const char *allowed=getenv("TITBIT_WIDESCREEN_VALIDATION");
            const char *scene=argv[++i];size_t n=strlen(scene);
            if(!allowed || strcmp(allowed,"1") || n<5 || n>240 || strchr(scene,'/') || strchr(scene,'\\') || strchr(scene,':') || strcasecmp(scene+n-4,".xml")) {
                fprintf(stderr,"--validate-scene requires TITBIT_WIDESCREEN_VALIDATION=1 and a plain XML archive name\n");return 2;
            }
            setenv("TITBIT_VALIDATE_SCENE",scene,1);
        } else if(!strcmp(argv[i],"--help")) {
            puts("titbit [--data GAME_DIRECTORY] [--windowed | --fullscreen] [--widescreen[=16:9|16:10]]\nF11 / Alt+Enter: toggle fullscreen");return 0;
        } else {fprintf(stderr,"Unknown argument: %s\n",argv[i]);return 2;}
    }
    if (!tb_init()) {fprintf(stderr,"SDL: %s\n",tb_error());return 1;}
    titbit_linux_initialize_pod_globals();
    int result=titbit_linux_run();
    tb_shutdown();
    return result;
}

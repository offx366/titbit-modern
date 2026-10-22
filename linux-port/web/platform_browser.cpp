#include "../platform/titbit_platform.h"
#include <emscripten.h>
#include <cstdio>
#include <cstdlib>
#include <exception>

extern "C" {
struct Message {void *window;unsigned message,wparam;int lparam;unsigned time;int x,y;};
int PeekMessageA(Message *,void *,unsigned,unsigned,unsigned);
int TranslateMessage(const Message *);
int DispatchMessageA(const Message *);
int tb_linux_poll() {
    Message message;
    while(PeekMessageA(&message,nullptr,0,0,1)) {
        if(message.message==0x12)return 0;
        TranslateMessage(&message);DispatchMessageA(&message);
    }
    return 1;
}
EM_JS(void,tb_web_phase,(const char *text),{
    if (Module.onPhase) Module.onPhase(UTF8ToString(text));
});
void tb_seer_dispatch_error(void *function,int bytes,int needed,const char *name) {
    std::fprintf(stderr,"SeeR callback %s (%p): %d bytes supplied, %d required\n",name,function,bytes,needed);
    std::abort();
}
bool titbit_native_uncaught_exception(){return std::uncaught_exceptions()!=0;}
int _msvc_regEDX;
}

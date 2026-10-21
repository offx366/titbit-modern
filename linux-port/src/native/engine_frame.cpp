/* Exploratory source frame caller. External object declarations do not define
 * storage or assert complete native object sizes. Unbuilt subjects stay external. */
#include "picking_control_state.h"
#include "picking_control_interfaces.h"
struct Rect {long left,top,right,bottom;};
extern Rect gameRect;
extern void *gameDC;
class RenderContext;
extern RenderContext renderContext;
void __cdecl PickingTrace(const char *,...);
extern "C" {
__declspec(dllimport) void __stdcall glDisable(unsigned);
__declspec(dllimport) void __stdcall glClear(unsigned);
__declspec(dllimport) void __stdcall glEnable(unsigned);
__declspec(dllimport) void __stdcall glMatrixMode(unsigned);
__declspec(dllimport) void __stdcall glLoadIdentity();
__declspec(dllimport) void __stdcall glPushMatrix();
__declspec(dllimport) void __stdcall glPopMatrix();
__declspec(dllimport) void __stdcall glFlush();
__declspec(dllimport) int __stdcall SwapBuffers(void *);
void __stdcall gluPerspective(double,double,double,double);
/* Single ECX argument is the observed machine ABI; no native class name or
 * extra EDX argument is asserted for these still-unbuilt methods. */
void __fastcall ApplyGameView(RenderContext *);
void __fastcall RenderGameScene(ObservedPickingScene *);
#ifdef TITBIT_COMPAT
#include "../compat/compat.h"
#endif
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "widescreen_hooks.h"
#endif
void __cdecl RunGameFrame() {
#ifdef TITBIT_COMPAT
 CompatBeginFrame();
#endif
 PickingTrace("begin draw");
 glDisable(0xb71);
 glClear(0x100);
 glEnable(0xb71);
 glMatrixMode(0x1701);
 glLoadIdentity();
 double aspect = (float)(gameRect.right-gameRect.left)/(float)(gameRect.bottom-gameRect.top);
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 aspect = CompatWorldAspect(aspect);
#endif
 gluPerspective((double)*(const float*)((const char*)&renderContext+0xec008),aspect,1,2000);
 glMatrixMode(0x1700);
 glPushMatrix();
 ApplyGameView(&renderContext);
 pickingControl.Update();
 RenderGameScene(&picking_scene);
 glPopMatrix();
 glFlush();
 if(!*(const unsigned*)&picking_scene)SwapBuffers(gameDC);
 PickingTrace("EndDraw");
}
}

typedef void *HWND;typedef void *HINSTANCE;typedef unsigned WPARAM;typedef unsigned LPARAM;typedef long LRESULT;
struct Rect {long left,top,right,bottom;};
extern "C" {
__declspec(dllimport) LRESULT __stdcall DefWindowProcA(HWND,unsigned,WPARAM,LPARAM);
__declspec(dllimport) void __stdcall PostQuitMessage(int);
__declspec(dllimport) int __stdcall ShowWindow(HWND,int);
__declspec(dllimport) int __stdcall MoveWindow(HWND,int,int,int,int,int);
bool __cdecl InitGameDisplay();void __cdecl RestoreGameDisplay();void __cdecl SetGameSpeed(float);
int __cdecl InitGameInput(HINSTANCE,HWND);void __cdecl ReleaseGameInput();
void __cdecl RestoreGameAudio();void __cdecl PauseGameAudio();
}
#ifdef TITBIT_COMPAT
#include "../compat/compat.h"   /* windowed/borderless: no maximise/move/minimise on focus changes (src/compat/README.md) */
#endif
extern bool gameActive;extern unsigned char keyStates[256];extern Rect gameRect;
extern HINSTANCE gameInstance;extern int displayWidth,displayHeight;
#include "picking_control_state.h"
extern "C" LRESULT __stdcall GameWindowProc(HWND window,unsigned message,WPARAM wparam,LPARAM lparam){
 switch(message){
 case 6:gameActive=(unsigned short)wparam!=0;return 0;
 case 0x10:PostQuitMessage(0);return 0;
 case 0x100:pickingControl.Key(wparam);keyStates[wparam]=1;return 0;
 case 7:InitGameDisplay();ShowWindow(window,3);MoveWindow(window,0,0,displayWidth,displayHeight,1);SetGameSpeed(1);InitGameInput(gameInstance,window);RestoreGameAudio();return 0;
 case 8:RestoreGameDisplay();ShowWindow(window,2);SetGameSpeed(0);ReleaseGameInput();PauseGameAudio();
 case 5:return 0;
 case 0x101:keyStates[wparam]=0;return 0;
 case 0x112:switch(wparam){case 0xf140:case 0xf170:return 0;}break;
 case 0x200:
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  // Win32 mouse coordinates are signed 16-bit values. Wide-world positions
  // left of the central UI canvas are negative, not coordinates near 65535.
  pickingControl.mouse_x=(short)(lparam&0xffff);
  pickingControl.mouse_y=gameRect.bottom-(short)(lparam>>16)-gameRect.top;
#else
  pickingControl.mouse_x=lparam&0xffff;pickingControl.mouse_y=gameRect.bottom-(lparam>>16)-gameRect.top;
#endif
  return 0;
 case 0x201:pickingControl.Click(8);return 0;
 case 0x202:pickingControl.Click(9);return 0;
 case 0x204:pickingControl.Key(2);return 0;
 }
 return DefWindowProcA(window,message,wparam,lparam);
}

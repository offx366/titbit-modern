/* Exercise the actual game WndProc's signed-coordinate path without a window.
 * The fixtures below satisfy its unrelated focus/audio/input branches only;
 * they are test-only and are never linked into the game. */
#define TITBIT_WIDESCREEN_HOOKS
#include "../../native/window_callbacks.cpp"
bool gameActive;
unsigned char keyStates[256];
Rect gameRect = {0,0,1024,768};
HINSTANCE gameInstance;
int displayWidth=1024,displayHeight=768;
ObservedPickingControl pickingControl;
ObservedPickingControl::ObservedPickingControl() {}
ObservedPickingControl::~ObservedPickingControl() {}
void ObservedPickingControl::Click(unsigned) {}
void ObservedPickingControl::Key(int) {}
extern "C" {
bool __cdecl InitGameDisplay(){return true;}
void __cdecl RestoreGameDisplay(){}
void __cdecl SetGameSpeed(float){}
int __cdecl InitGameInput(HINSTANCE,HWND){return 0;}
void __cdecl ReleaseGameInput(){}
void __cdecl RestoreGameAudio(){}
void __cdecl PauseGameAudio(){}
}
int main() {
 GameWindowProc(0,0x200,0,((unsigned)384 << 16) | (unsigned short)-171);
 if (pickingControl.mouse_x != -171 || pickingControl.mouse_y != 384) return 1;
 GameWindowProc(0,0x200,0,((unsigned)384 << 16) | 1195);
 if (pickingControl.mouse_x != 1195 || pickingControl.mouse_y != 384) return 2;
 GameWindowProc(0,0x200,0,((unsigned)200 << 16) | 512);
 if (pickingControl.mouse_x != 512 || pickingControl.mouse_y != 568) return 3;
 return 0;
}

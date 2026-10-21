/* Non-game Win32/OpenGL integration. MUST run on a hidden desktop. */
#define WINVER 0x0500
#define TITBIT_COMPAT_IMPLEMENTATION
#include <windows.h>
#include <GL/gl.h>
#include "../compat.h"
#pragma intrinsic(memset)
static int failures, mouse_x, mouse_y;
#define CHECK(x) do { if (!(x)) ++failures; } while(0)
static LRESULT CALLBACK Proc(HWND window, UINT message, WPARAM a, LPARAM b) {
 if (message == WM_MOUSEMOVE) { mouse_x = (short)LOWORD(b); mouse_y = (short)HIWORD(b); }
 return DefWindowProcA(window,message,a,b);
}
int main() {
 // Refuse even the test window on an interactive desktop.
 char name[256]; DWORD needed;
 HDESK desk = GetThreadDesktop(GetCurrentThreadId());
 if (!GetUserObjectInformationA(desk,UOI_NAME,name,sizeof(name),&needed) ||
     lstrcmpiA(name,"default") == 0) return 99;
 SetEnvironmentVariableA("TITBIT_WIDESCREEN_VALIDATION",0);
 SetEnvironmentVariableA("TITBIT_VALIDATE_SCENE","getto_bomj_n.xml");
 CHECK(lstrcmpA(CompatInitialScene(),"startup.XML")==0);
 SetEnvironmentVariableA("TITBIT_WIDESCREEN_VALIDATION","1");
 CHECK(lstrcmpA(CompatInitialScene(),"getto_bomj_n.xml")==0);
 SetEnvironmentVariableA("TITBIT_VALIDATE_SCENE","../menu.xml");
 CHECK(lstrcmpA(CompatInitialScene(),"startup.XML")==0);
 SetEnvironmentVariableA("TITBIT_WIDESCREEN_VALIDATION",0);
 SetEnvironmentVariableA("TITBIT_COMPAT_DISPLAY","windowed");
 SetEnvironmentVariableA("TITBIT_COMPAT_RESOLUTION","1600x900");
 SetEnvironmentVariableA("TITBIT_COMPAT_ASPECT","widescreen");
 SetEnvironmentVariableA("TITBIT_COMPAT_WIDESCREEN_RATIO","16:9");
 SetEnvironmentVariableA("TITBIT_WIDESCREEN_SCENES",0);
 HANDLE file=CreateFileA("widescreen-scenes.txt",GENERIC_WRITE,0,0,CREATE_ALWAYS,0,0);
 DWORD written; WriteFile(file,"street.XML\n",11,&written,0);CloseHandle(file);
 WNDCLASSA wc;ZeroMemory(&wc,sizeof(wc));wc.style=CS_OWNDC;wc.lpfnWndProc=Proc;
 wc.hInstance=GetModuleHandleA(0);wc.lpszClassName="OpenGL";RegisterClassA(&wc);
 HWND window=(HWND)CompatCreateWindowExA(0,"OpenGL","Widescreen test",WS_POPUP,
                                      0,0,1600,900,0,0,wc.hInstance,0);
 CHECK(window != 0);
 RECT client;GetClientRect(window,&client);
 CHECK(client.right==1600 && client.bottom==900);
 HDC dc=GetDC(window);PIXELFORMATDESCRIPTOR pf;ZeroMemory(&pf,sizeof(pf));
 pf.nSize=sizeof(pf);pf.nVersion=1;pf.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL|PFD_DOUBLEBUFFER;
 pf.iPixelType=PFD_TYPE_RGBA;pf.cColorBits=32;pf.cDepthBits=24;
 int format=ChoosePixelFormat(dc,&pf);CHECK(format!=0);CHECK(SetPixelFormat(dc,format,&pf));
 HGLRC gl=wglCreateContext(dc);CHECK(gl!=0);CHECK(wglMakeCurrent(dc,gl));
 CompatSceneChanged("mainmenu.XML");CompatBeginFrame();
 CHECK(CompatWorldAspect(4.0/3.0)==4.0/3.0);
 int view[4];glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 CompatSceneChanged("locations\\STREET.xml");CompatBeginFrame();
 CHECK(CompatWorldAspect(4.0/3.0)==16.0/9.0);
 glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==0 && view[2]==1600 && view[3]==900);
 CHECK(CompatBeginFullscreenEffect(0,0,1024,768,0.01f,0.01f)==0); // world pass
 CHECK(CompatWorldMouseX(1.0)==0.75);
 glClearColor(0,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
 CompatBeginOverlay();glGetIntegerv(GL_VIEWPORT,view);
 CHECK(view[0]==200 && view[2]==1200 && view[3]==900);
 glClearColor(1,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 unsigned char pixel[4];glReadPixels(0,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
 CHECK(pixel[0]==0 && pixel[2]==255);
 glReadPixels(800,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
 CHECK(pixel[0]==255 && pixel[2]==0);
 glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,1024,768,0,-10000,20000);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 CHECK(CompatBeginFullscreenEffect(0,0,1024,768,1,1)==0); // regular full-screen menu
 CHECK(CompatBeginFullscreenEffect(0,0,400,300,0.01f,0.01f)==0); // dialog
 glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 CompatEndOverlay();glClearColor(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT);CompatBeginOverlay();
 int effect=CompatBeginFullscreenEffect(0,0,1024,768,0.01f,0.01f);CHECK(effect==1);
 glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glColor4f(0,0,0,0.5f);
 glBegin(GL_TRIANGLE_STRIP);glVertex2f(1024,0);glVertex2f(0,0);glVertex2f(1024,768);glVertex2f(0,768);glEnd();
 CompatEndFullscreenEffect(effect);glDisable(GL_BLEND);glFinish();
 glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 glReadPixels(80,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);CHECK(pixel[0]>=126 && pixel[0]<=129);
 unsigned char center[4],right[4];glReadPixels(800,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,center);
 glReadPixels(1520,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,right);
 CHECK(center[0]==pixel[0] && right[0]==pixel[0]);
 CompatBeginCursorOverlay();
 glColor3f(0,1,0);glBegin(GL_QUADS);
 glVertex2f(-110,380);glVertex2f(-90,380);glVertex2f(-90,388);glVertex2f(-110,388);glEnd();
 glFinish();glReadPixels(80,450,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
 CHECK(pixel[0]==0 && pixel[1]==255 && pixel[2]==0);
 CompatEndCursorOverlay();glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 double projection[16];glGetDoublev(GL_PROJECTION_MATRIX,projection);
 CHECK(projection[0]==2.0/1024.0 && projection[12]==-1.0);
 CompatEndOverlay();glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==0 && view[2]==1600);
 SendMessageA(window,WM_MOUSEMOVE,0,MAKELPARAM(800,450));CHECK(mouse_x==512 && mouse_y==384);
 SendMessageA(window,WM_MOUSEMOVE,0,MAKELPARAM(0,450));CHECK(mouse_x<0 && mouse_y==384);
 SetEnvironmentVariableA("TITBIT_COMPAT_WIDESCREEN_RATIO","16:10");
 CompatBeginFrame();CHECK(CompatWorldAspect(4.0/3.0)==16.0/10.0);
 glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==80 && view[2]==1440 && view[3]==900);
 CompatBeginOverlay();glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 CompatBeginCursorOverlay();
 CompatSceneChanged("minigame.XML");
 CompatEndCursorOverlay();
 glGetDoublev(GL_PROJECTION_MATRIX,projection);
 CHECK(projection[0]==2.0/1024.0 && projection[12]==-1.0);
 CompatEndOverlay();
 CompatSceneChanged("minigame.XML");CompatBeginFrame();
 CHECK(CompatWorldAspect(4.0/3.0)==4.0/3.0);
 glGetIntegerv(GL_VIEWPORT,view);CHECK(view[0]==200 && view[2]==1200);
 CHECK(glGetError()==GL_NO_ERROR);
 wglMakeCurrent(0,0);wglDeleteContext(gl);ReleaseDC(window,dc);DestroyWindow(window);
 DeleteFileA("widescreen-scenes.txt");
 return failures;
}

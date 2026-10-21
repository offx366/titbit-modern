// Exploratory actual WinMain candidate. Unresolved subjects stay external.
// Setup dialog248 bytes is a stack-layout hypothesis, not recovered identity.
#include "setup_dialog.h"
#include <commctrl.h>
#include <string.h>
#define LoadStringA ProbeEngineLoadStringA
#include "engine_string.h"
#undef LoadStringA
#include "picking_control_interfaces.h"
#pragma intrinsic(memcmp)
extern "C" {
int __cdecl CheckGameDisc();
bool __cdecl InitGameDisplay();
int __cdecl CreateGameWindow(const char*,int,int);
int __cdecl InitGameInput(HINSTANCE,HWND);
void __cdecl ShutdownGameWindow();
void __cdecl CloseApp();
void __cdecl ShellExecuteScriptRegistrationTarget();
void __cdecl RunGameFrame();
void __cdecl scAdd_External_Symbol(char*,void*);
}
int SetArchiveRoot(const char*);
int MountArchive(const char*);
extern HWND gameWindow;
extern int displayWidth,displayHeight;
extern bool gameActive;
#ifdef TITBIT_COMPAT
#include "../compat/compat.h"
#endif
// Source-backed ordinary out-of-line ABI boundaries; no template specializations.
void __fastcall SourceDestroyNotifyArray(ATL::CSimpleArray<HWND>* value) {value->RemoveAll();}
void __fastcall SourceClearMessageLoopMap(ATL::CSimpleMap<DWORD,WTL::CMessageLoop*>* value) {value->RemoveAll();}
extern "C" HRESULT __stdcall SourceAtlModuleTerm(ATL::_ATL_MODULE*);
// Authored observed older cleanup. No WTL7.5 lock or pointer clearing invented.
inline void WTL::CAppModule::Term() {
 if(m_pSettingChangeNotify != NULL) {
  if(m_pSettingChangeNotify->GetSize()>0)
   ::DestroyWindow((*m_pSettingChangeNotify)[0]);
  if(m_pSettingChangeNotify){SourceDestroyNotifyArray(m_pSettingChangeNotify);::operator delete(m_pSettingChangeNotify);}
 }
 if(m_pMsgLoopMap){SourceClearMessageLoopMap(m_pMsgLoopMap);::operator delete(m_pMsgLoopMap);}
 SourceAtlModuleTerm(this);
}
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show) {
 CoInitialize(0);
 INITCOMMONCONTROLSEX icc;
 icc.dwSize=sizeof(icc);icc.dwICC=ICC_BAR_CLASSES;
 InitCommonControlsEx(&icc);
 HWND existing=FindWindowA("OpenGL","Titbit");
 if(existing){ShowWindow(existing,1);return 0;}
 if(CheckGameDisc()==1)return 0;
 gameModule.Init(0,instance,0);
#ifdef TITBIT_COMPAT
 if(!CompatPrepareGame(&displayWidth,&displayHeight)) {
#endif
 SetupDialogProbe setup;
 setup.option=memcmp(command,"/s",3)==0;
 if(setup.DoModal()!=1)return 1;
 if(!InitGameDisplay())return 1;
#ifdef TITBIT_COMPAT
 }
#endif
 if(CreateGameWindow("Titbit",displayWidth,displayHeight)) {
  InitGameInput(instance,gameWindow);
  scAdd_External_Symbol("CloseApp",(void*)&CloseApp);
  scAdd_External_Symbol("ShellExecute",(void*)&ShellExecuteScriptRegistrationTarget);
  SetArchiveRoot(".\\");
  MountArchive("QUEST.EZD");
#ifdef TITBIT_COMPAT
  picking_scene.Load(ObservedString(CompatInitialScene()));
#else
  picking_scene.Load(ObservedString("startup.XML"));
#endif
  MSG message;
  for(;;) {
   if(PeekMessageA(&message,0,0,0,PM_REMOVE)) {
    if(message.message==WM_QUIT)break;
    TranslateMessage(&message);DispatchMessageA(&message);
   }else if(gameActive)RunGameFrame();
  }
  ShutdownGameWindow();
  gameModule.Term();
  CoUninitialize();
 }
 return 0;
}

/* No window is created. A visible-desktop process must not bypass startup. */
#define TITBIT_COMPAT_IMPLEMENTATION
#include <windows.h>
#include "../compat.h"
int main() {
 char name[256];DWORD needed;
 if (!GetUserObjectInformationA(GetThreadDesktop(GetCurrentThreadId()),UOI_NAME,
                               name,sizeof(name),&needed) || lstrcmpiA(name,"default") != 0) return 99;
 SetEnvironmentVariableA("TITBIT_WIDESCREEN_VALIDATION","1");
 SetEnvironmentVariableA("TITBIT_VALIDATE_SCENE","getto_bomj.XML");
 return lstrcmpA(CompatInitialScene(),"startup.XML") == 0 ? 0 : 1;
}

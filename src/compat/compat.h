/* Modern-Windows compatibility layer (TITBIT_COMPAT builds only).
 *
 * The original sources include this header right AFTER their own Win32/VfW
 * prototypes, inside `#ifdef TITBIT_COMPAT`. The macros below then redirect the
 * later calls to the Compat* replacements in src/compat/*.cpp; game logic is
 * unchanged. The original build never defines TITBIT_COMPAT.
 *
 * Plain C types only: the game units use their own Win32 typedefs (some do not
 * include <windows.h>), so nothing here may depend on windows.h types.
 * See src/compat/README.md for every switch.
 */
#ifndef TITBIT_COMPAT_H
#define TITBIT_COMPAT_H

#ifdef __cplusplus
extern "C" {
#endif

/* Video (compat_video.cpp): VfW frame decompression without installed codecs. */
void *__stdcall CompatAVIStreamGetFrameOpen(void *stream, void *wanted_format);
void *__stdcall CompatAVIStreamGetFrame(void *frames, long position);
long __stdcall CompatAVIStreamGetFrameClose(void *frames);

/* CD check (compat_cd.cpp): the install folder stands in for the game CD. */
int __stdcall CompatGetVolumeInformationA(const char *root, char *label, unsigned long label_size,
                                          unsigned long *serial, unsigned long *max_component,
                                          unsigned long *flags, char *fs_name, unsigned long fs_size);
unsigned __stdcall CompatGetDriveTypeA(const char *root);

/* Display (compat_display.cpp): no forced mode switch, windowed/borderless window. */
long __stdcall CompatChangeDisplaySettingsA(void *mode, unsigned long flags);
void *__stdcall CompatCreateWindowExA(unsigned long ex_style, const char *class_name, const char *title,
                                      unsigned long style, int x, int y, int width, int height,
                                      void *parent, void *menu, void *instance, void *param);
int __stdcall CompatMoveWindow(void *window, int x, int y, int width, int height, int repaint);
int __stdcall CompatShowWindow(void *window, int command);
void __stdcall CompatPlatformStartup(void);
int __stdcall CompatPrepareGame(int *width, int *height);
void __stdcall CompatGameCanvas(int *width, int *height);
void __stdcall CompatGLViewport(int x, int y, int width, int height);
void __stdcall CompatBeginFrame(void);
/* Experimental world-only widescreen. The scene allowlist is supplied by the
 * local outpaint mod; menus/minigames without an entry retain the 4:3 canvas. */
void __stdcall CompatSceneChanged(const char *path);
double __stdcall CompatWorldAspect(double original_aspect);
double __stdcall CompatWorldMouseX(double original_ndc);
void __stdcall CompatBeginOverlay(void);
void __stdcall CompatEndOverlay(void);
void __stdcall CompatBeginCursorOverlay(void);
void __stdcall CompatEndCursorOverlay(void);
float __stdcall CompatOverlayMouseX(const char *name, float central_x);
void __stdcall CompatBeginInventoryOverlay(void);
void __stdcall CompatEndInventoryOverlay(void);
int __stdcall CompatBeginFullscreenEffect(float x, float y, float width, float height,
                                          float uv_width, float uv_height);
void __stdcall CompatEndFullscreenEffect(int expanded);
/* Development validation only: gated scene entry on a hidden desktop. */
const char *__stdcall CompatInitialScene(void);

/* Test support (compat_replay.cpp): deterministic record/replay, run before the
 * program entry point; does nothing unless the replay setting is record/play. */
void __stdcall CompatStartup(void);

/* Master slider (compat_volume.cpp): the game's current-process audio session. */
int __cdecl CompatGetMasterVolume(void);
int __cdecl CompatSetMasterVolume(int percent);

#ifdef __cplusplus
}
#endif

#ifndef TITBIT_COMPAT_IMPLEMENTATION
#define AVIStreamGetFrameOpen CompatAVIStreamGetFrameOpen
#define AVIStreamGetFrame CompatAVIStreamGetFrame
#define AVIStreamGetFrameClose CompatAVIStreamGetFrameClose
#define GetVolumeInformationA CompatGetVolumeInformationA
#define GetDriveTypeA CompatGetDriveTypeA
#define ChangeDisplaySettingsA CompatChangeDisplaySettingsA
#define CreateWindowExA CompatCreateWindowExA
#define MoveWindow CompatMoveWindow
#define ShowWindow CompatShowWindow
#define glViewport CompatGLViewport
#endif

#endif

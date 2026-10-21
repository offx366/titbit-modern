/* World presentation hooks, implemented by the platform, no game ABI/layout
 * changes. Linux enables only these hooks, not the Win32 compat wrappers. */
#ifndef TITBIT_WIDESCREEN_HOOKS_H
#define TITBIT_WIDESCREEN_HOOKS_H
extern "C" {
void __stdcall CompatSceneChanged(const char *path);
double __stdcall CompatWorldAspect(double original_aspect);
double __stdcall CompatWorldMouseX(double original_ndc);
void __stdcall CompatBeginOverlay(void);
void __stdcall CompatEndOverlay(void);
void __stdcall CompatBeginCursorOverlay(void);
void __stdcall CompatEndCursorOverlay(void);
/* The inventory keeps its original script-local coordinates and animation,
 * but is docked at the actual wide canvas edge. Other windows stay central. */
float __stdcall CompatOverlayMouseX(const char *name, float central_x);
void __stdcall CompatBeginInventoryOverlay(void);
void __stdcall CompatEndInventoryOverlay(void);
int __stdcall CompatBeginFullscreenEffect(float x, float y, float width, float height,
                                          float uv_width, float uv_height);
void __stdcall CompatEndFullscreenEffect(int expanded);
}
#endif

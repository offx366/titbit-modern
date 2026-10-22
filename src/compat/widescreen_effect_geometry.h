/* Pure classification of an atlas-swatch fullscreen lighting plane. No names,
 * script state, texture contents or game object layouts are assumed here. */
#ifndef TITBIT_WIDESCREEN_EFFECT_GEOMETRY_H
#define TITBIT_WIDESCREEN_EFFECT_GEOMETRY_H
static inline float CompatEffectAbs(float v) { return v < 0 ? -v : v; }
/* Mod-only menu atlases use an exact integer-raster UV width. Native menu
 * textures use du=1 or .382 and cannot accidentally enable this presentation. */
static inline int CompatIsWideMenuBackground(const float *m, float x, float y,
                                             float width, float height, float du, float dv) {
 if (!(CompatEffectAbs(CompatEffectAbs(du)-1366.0f/2048.0f)<0.000001f ||
       CompatEffectAbs(CompatEffectAbs(du)-1230.0f/2048.0f)<0.000001f) ||
     CompatEffectAbs(CompatEffectAbs(dv)-.75f)>0.000001f) return 0;
 if (CompatEffectAbs(m[0]-1)>0.00001f || CompatEffectAbs(m[5]-1)>0.00001f ||
     CompatEffectAbs(m[1])+CompatEffectAbs(m[4])+CompatEffectAbs(m[8])+CompatEffectAbs(m[9])>0.00001f) return 0;
 return CompatEffectAbs(x+m[12])<.25f && CompatEffectAbs(y+m[13])<.25f &&
        CompatEffectAbs(width-1024)<.25f && CompatEffectAbs(height-768)<.25f;
}
static inline int CompatIsFullscreenEffect(const float *m, float x, float y,
                                           float width, float height, float du, float dv) {
 if (!(CompatEffectAbs(du) <= 0.125f && CompatEffectAbs(dv) <= 0.125f)) return 0;
 // Screen effects are axis-aligned; world decals and rotated UI are excluded.
 if (!(CompatEffectAbs(m[1]) <= 0.00001f && CompatEffectAbs(m[4]) <= 0.00001f &&
       CompatEffectAbs(m[8]) <= 0.00001f && CompatEffectAbs(m[9]) <= 0.00001f)) return 0;
 float x0 = m[0] * x + m[12], x1 = m[0] * (x + width) + m[12];
 float y0 = m[5] * y + m[13], y1 = m[5] * (y + height) + m[13];
 if (x0 > x1) { float t=x0; x0=x1; x1=t; }
 if (y0 > y1) { float t=y0; y0=y1; y1=t; }
 return CompatEffectAbs(x0) <= 0.25f && CompatEffectAbs(y0) <= 0.25f &&
        CompatEffectAbs(x1 - 1024.0f) <= 0.25f && CompatEffectAbs(y1 - 768.0f) <= 0.25f;
}
#endif

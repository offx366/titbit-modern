#ifndef TITBIT_PRESENTATION_H
#define TITBIT_PRESENTATION_H
#include <stdint.h>

typedef struct TBViewport { int x, y, width, height, top; } TBViewport;

/* GL uses a bottom-left origin; SDL mouse coordinates start at the top. */
static inline TBViewport tb_fit_viewport(int width,int height,int logical_w,int logical_h) {
 TBViewport vp={0,0,0,0,0};
 if(width<=0||height<=0||logical_w<=0||logical_h<=0)return vp;
 vp.width=width;vp.height=height;
 if((int64_t)width*logical_h>(int64_t)height*logical_w)vp.width=(int64_t)height*logical_w/logical_h;
 else vp.height=(int64_t)width*logical_h/logical_w;
 vp.x=(width-vp.width)/2;vp.y=(height-vp.height)/2;vp.top=height-vp.y-vp.height;
 return vp;
}

static inline int tb_map_mouse(TBViewport vp,int x,int y,int logical_w,int logical_h,int *lx,int *ly) {
 if(vp.width<=0||vp.height<=0){*lx=*ly=0;return 0;}
 int inside=x>=vp.x&&y>=vp.top&&x<vp.x+vp.width&&y<vp.top+vp.height;
 x=x<vp.x?0:x>=vp.x+vp.width?vp.width-1:x-vp.x;
 y=y<vp.top?0:y>=vp.top+vp.height?vp.height-1:y-vp.top;
 *lx=(int64_t)x*logical_w/vp.width;*ly=(int64_t)y*logical_h/vp.height;
 return inside;
}
/* The world viewport includes generated side regions. Keep the coordinates in
 * the original central canvas space (signed X), but validate both physical axes
 * against the complete world viewport, never against the narrower UI canvas. */
static inline int tb_map_world_mouse(TBViewport canvas,TBViewport world,int x,int y,int logical_w,int logical_h,int *lx,int *ly) {
 if(canvas.width<=0||canvas.height<=0||world.width<=0||world.height<=0||
    x<world.x||x>=world.x+world.width||y<world.top||y>=world.top+world.height) {
  *lx=*ly=-1;return 0;
 }
 *lx=(int64_t)(x-canvas.x)*logical_w/canvas.width;
 *ly=(int64_t)(y-canvas.top)*logical_h/canvas.height;
 return 1;
}
#endif

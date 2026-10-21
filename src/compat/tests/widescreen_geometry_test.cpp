/* Pure presentation geometry; no window, display-mode or focus changes. */
#include "../display_geometry.h"
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
int main() {
 CompatViewport wide = CompatFitViewport(1920,1080,16,9,false);
 CompatViewport ui = CompatCentralViewport(wide,1080);
 CHECK(wide.x == 0 && wide.width == 1920 && wide.height == 1080);
 CHECK(ui.x == 240 && ui.width == 1440 && ui.height == 1080);
 int x,y;
 CHECK(CompatMapWorldMouse(wide,ui,960,540,&x,&y) && x == 512 && y == 384);
 CHECK(CompatMapWorldMouse(wide,ui,240,0,&x,&y) && x == 0 && y == 0);
 CHECK(CompatMapWorldMouse(wide,ui,0,540,&x,&y) && x < 0 && y == 384);
 CHECK(CompatMapWorldMouse(wide,ui,1919,540,&x,&y) && x > 1024);
 CHECK(!CompatMapWorldMouse(wide,ui,1920,540,&x,&y));
 wide = CompatFitViewport(1920,1200,16,10,false);
 ui = CompatCentralViewport(wide,1200);
 CHECK(ui.x == 160 && ui.width == 1600 && ui.height == 1200);
 CHECK(CompatMapWorldMouse(wide,ui,960,600,&x,&y) && x == 512 && y == 384);
 wide = CompatFitViewport(1280,1024,16,9,false);
 ui = CompatCentralViewport(wide,1024);
 CHECK(wide.height == 720 && wide.top == 152);
 CHECK(ui.x == 160 && ui.width == 960);
 CHECK(!CompatMapWorldMouse(wide,ui,640,151,&x,&y));
 CHECK(CompatMapWorldMouse(wide,ui,640,152,&x,&y) && x == 512 && y == 0);
 // Original 4:3 path still ignores clicks in the bars.
 CompatViewport classic = CompatFitViewport(1920,1080,1024,768,false);
 CHECK(!CompatMapMouse(classic,0,540,1024,768,&x,&y));
 CHECK(CompatMapMouse(classic,960,540,1024,768,&x,&y) && x == 512 && y == 384);
 return 0;
}

/* Authored 0x40fe90 source candidate; no original instructions/data are build
 * inputs. This version restores native local lifetime, 0xa0 stack allocation
 * and EBX/ESI saves, but full compiler section still differs (1408 vs 1504).
 * All 28 helper calls preserve evidenced ABI; classes are authored layout
 * views, not original source names or complete native global-storage types.
 * Camera/zoom/Scene remain explicit unbuilt runtime inputs. */
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "widescreen_hooks.h"
#endif
struct Vec {float x,y,z;Vec& Init3(float,float,float);Vec& Assign(const Vec&);};
struct CopyVec:Vec {CopyVec(const CopyVec&);};
struct M {float v[16];Vec *Origin(Vec*)const;};extern M camera;extern float zoom;
class Scene{public:void SetPoint(Vec);};extern Scene scene;
class Picking{unsigned ptr,flag;int left,top,right,bottom,mx,my;Vec point,origin;float planes[6][4];public:void Build();float Ray(CopyVec,CopyVec,CopyVec,float);void Pick(int,int);};
void Picking::Pick(int x,int y){
 Vec screen={(float)(x-left)*1024/(right-left),(float)(bottom-y)*768/(bottom-top),0};scene.SetPoint(screen);Build();
 Vec ax={1,0,0},ay={0,1,0},az={0,0,1};
 float w=right-left;float nx=(float)x-left-w*0.5f;nx=(nx+nx)/w;
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 nx=(float)CompatWorldMouseX(nx);
#endif
 float h=bottom-top;float ny=(float)y-top-h*0.5f;ny=(ny+ny)/h;
 Vec n0={planes[0][0],planes[0][1],planes[0][2]};
 Vec n2={planes[2][0],planes[2][1],planes[2][2]};
 float pd=planes[5][3],neg=-pd;
 Vec p0;{Vec tmp;tmp.Init3(neg*planes[5][0],neg*planes[5][1],neg*planes[5][2]);p0=tmp;}Vec p={0,0,0};bool parallel=true;float tx,ty;
 if(n0.x*n2.x+n0.y*n2.y+n0.z*n2.z>0.0001f){
  tx=2*Ray((const CopyVec&)p0,(const CopyVec&)ax,(const CopyVec&)n0,planes[0][3]);
  ty=2*Ray((const CopyVec&)p0,(const CopyVec&)ay,(const CopyVec&)n2,planes[2][3]);
  float s=pd+pd;az.x*=s;az.y*=s;az.z*=s;parallel=false;
 }else{
  tx=Ray((const CopyVec&)p,(const CopyVec&)ax,(const CopyVec&)n0,planes[0][3]);
  ty=Ray((const CopyVec&)p,(const CopyVec&)ay,(const CopyVec&)n2,planes[2][3]);
 }
 float scale=tx*nx;ax.x*=scale;ax.y*=scale;ax.z*=scale;
 scale=ty*ny;ay.x*=scale;ay.y*=scale;ay.z*=scale;
 float inv=1.0f/zoom;p.x=(ay.x+ax.x+az.x+p.x)*inv;p.y=(ay.y+ax.y+az.y+p.y)*inv;p.z=(ay.z+ax.z+az.z+p.z)*inv;
 Vec vz={camera.v[2]*p.z,camera.v[6]*p.z,camera.v[10]*p.z};
 Vec vy={camera.v[1]*p.y,camera.v[5]*p.y,camera.v[9]*p.y};
 Vec vx;vx.Init3(camera.v[0]*p.x,camera.v[4]*p.x,camera.v[8]*p.x);
 Vec eye;camera.Origin(&eye);
 Vec t;t.Init3(vx.x+eye.x+vy.x,vx.y+eye.y+vy.y,vx.z+eye.z+vy.z);
 Vec out;out.Init3(t.x+vz.x,t.y+vz.y,t.z+vz.z);point.x=out.x;point.y=out.y;point.z=out.z;
 if(parallel){Vec z;z.Init3(camera.v[2],camera.v[6],camera.v[10]);Vec d;d.Init3(point.x-z.x,point.y-z.y,point.z-z.z);origin.Assign(d);}else{Vec eye2;camera.Origin(&eye2);origin.Assign(eye2);}
}
Vec& Vec::Init3(float a,float b,float c){x=a;y=b;z=c;return *this;}
Vec& Vec::Assign(const Vec&v){x=v.x;y=v.y;z=v.z;return *this;}
CopyVec::CopyVec(const CopyVec&v){x=v.x;y=v.y;z=v.z;}

// Mouse picking against the scene (0x4105e0-0x411d40): ray vs. oriented box via
// a bounding sphere and the box's 12 triangles, ray vs. mesh in object space,
// and the per-frame selection with enter/leave notifications.
#include <math.h>
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "../../native/widescreen_hooks.h"
#endif
#pragma intrinsic(sqrt)

struct CVec3 {
 float x, y, z;
 CVec3() {}
 CVec3(float ax, float ay, float az);                // 0x406ee0
 CVec3(const CVec3 &o);                              // 0x406f00
 float Length_00406f50() const;
};

class Triangle {  // 0x428ab0 (was Triangle_00428ab0)
public:
 float body[0x38 / 4 - 1];
 Triangle();
 virtual ~Triangle();
 void Set_00428af0(float ax, float ay, float az, float bx, float by, float bz, float cx, float cy, float cz);
 bool RayHits_004295e0(CVec3 origin, CVec3 direction, float *t);
};
float __stdcall RaySphere_00428fd0(float ox, float oy, float oz, float dx, float dy, float dz,
                                 float sx, float sy, float sz, float radius);

struct BoxMatrix { float m[16]; void Identity_0040cc50(); };

struct BoneP { char head[0x2c]; float center[3]; float extents[3]; float extra[3]; char pad[0x94 - 0x50]; float world[16]; };
struct PickItem {                     // object component chain (+0x0c next)
 virtual void s0();
 virtual int GetType();
 virtual void s2(); virtual void s3(); virtual void s4();
 virtual bool RayTest(CVec3 origin, CVec3 direction, float *distance);   // +0x14
 int owner, field8;
 PickItem *next;
};
struct PickObject { char head[0x0c]; PickItem *next; char pad10[0x38 - 0x10]; BoneP *bone; char pad3c[0x88 - 0x3c]; char selectable; };
struct PickList { PickObject **items; int count; int capacity, grow; };
// Scene message (0x48 bytes, ObservedPickingMessage in src/native): object at +0x20, event code at +0x24,
// the screen position of a plane hit at +0x28/+0x2c.
struct SceneMessage { int reserved[8]; PickObject *object; int code; float x, y; int rest[6]; };
struct Scene_005011c0 {
 int head;
 PickList objects;                    // +0x04
 PickList windows;                    // +0x14
 PickList planes;                     // +0x24
 void PostMessage_00424780(SceneMessage *message);
};
extern Scene_005011c0 g_005011c0;
extern "C" PickObject *g_005022d4;    // object under the cursor

class PickingRay {
public:
 unsigned ptr, flag;
 int left, top, right, bottom, mx, my;   // +0x08
 CVec3 point;                         // +0x20
 CVec3 origin;                        // +0x2c
 bool RayBox_004105e0(CVec3 center, CVec3 half, BoxMatrix m, float *distance);
 bool RayObject_00411ac0(PickObject *object, float *distance);
 void Select_004115c0();
};

#define XFORM(x, y, z) CVec3(m.m[0] * (x) + m.m[4] * (y) + m.m[8] * (z) + m.m[12], \
                             m.m[1] * (x) + m.m[5] * (y) + m.m[9] * (z) + m.m[13], \
                             m.m[2] * (x) + m.m[6] * (y) + m.m[10] * (z) + m.m[14])
#define TRI(a, b, c) \
 tri.Set_00428af0(a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z); \
 if (tri.RayHits_004295e0(origin, dir, distance)) return true;

bool PickingRay::RayBox_004105e0(CVec3 center, CVec3 half, BoxMatrix m, float *distance) {
 Triangle tri;
 CVec3 c = XFORM(center.x, center.y, center.z);
 float radius = (float)sqrt(half.x * half.x + half.y * half.y + half.z * half.z);
 CVec3 dir;
 dir.x = point.x - origin.x;
 dir.y = point.y - origin.y;
 dir.z = point.z - origin.z;
 float length = dir.Length_00406f50();
 if (length != 0.0f) { length = 1.0f / length; dir.x = dir.x * length; dir.y = dir.y * length; dir.z = dir.z * length; }
 if (RaySphere_00428fd0(origin.x, origin.y, origin.z, dir.x, dir.y, dir.z, c.x, c.y, c.z, radius) == -1.0f)
  return false;
 float x0 = center.x - half.x, x1 = center.x + half.x;
 float y0 = center.y - half.y, y1 = center.y + half.y;
 float z0 = center.z - half.z, z1 = center.z + half.z;
 CVec3 A = XFORM(x0, y1, z0), B = XFORM(x0, y1, z1), C = XFORM(x1, y1, z1), D = XFORM(x1, y1, z0);
 CVec3 E = XFORM(x0, y0, z0), F = XFORM(x0, y0, z1), G = XFORM(x1, y0, z1), H = XFORM(x1, y0, z0);
 TRI(A, B, D)
 TRI(B, D, C)
 TRI(A, B, E)
 TRI(E, F, B)
 TRI(B, C, F)
 TRI(C, F, G)
 TRI(A, D, H)
 TRI(A, H, E)
 TRI(D, G, H)
 TRI(C, D, G)
 TRI(E, F, G)
 TRI(E, G, H)
 return false;
}

// Ray in the object's bone space against its first mesh component (type 4).
bool PickingRay::RayObject_00411ac0(PickObject *object, float *distance) {
 PickItem *item = object->next;
 CVec3 dir;
 dir.x = point.x - origin.x;
 dir.y = point.y - origin.y;
 dir.z = point.z - origin.z;
 float length = (float)sqrt(dir.z * dir.z + dir.y * dir.y + dir.x * dir.x);
 if (length != 0.0f) { length = 1.0f / length; dir.x = dir.x * length; dir.y = dir.y * length; dir.z = dir.z * length; }
 for (; item; item = item->next) {
  if (item->GetType() == 4) {
   const float *w = object->bone->world;
   float ox = origin.x - w[12], oy = origin.y - w[13], oz = origin.z - w[14];
   CVec3 o, d;
   o.x = ox * w[0] + oy * w[1] + oz * w[2];
   o.y = ox * w[4] + oy * w[5] + oz * w[6];
   o.z = ox * w[8] + oy * w[9] + oz * w[10];
   d.x = dir.x * w[0] + dir.y * w[1] + dir.z * w[2];
   d.y = dir.x * w[4] + dir.y * w[5] + dir.z * w[6];
   d.z = dir.x * w[8] + dir.y * w[9] + dir.z * w[10];
   return item->RayTest(o, d, distance);
  }
 }
 return true;
}

void PickingRay::Select_004115c0() {
 CVec3 center, half;
 center.x = center.y = center.z = 0;
 half.x = half.y = half.z = 0;
 BoxMatrix m;
 m.Identity_0040cc50();
 float best = 1e7f;
 SceneMessage message;
 for (int k = 0; k < (int)(sizeof(message) / 4); k++) ((int *)&message)[k] = 0;
 PickObject *previous = g_005022d4;
 g_005022d4 = 0;
 float distance;
 int i;
 for (i = 0; i < g_005011c0.objects.count; i++) {
  PickObject *o = g_005011c0.objects.items[i];
  if (!o->selectable) continue;
  BoneP *b = o->bone;
  center.y = b->center[1]; center.x = b->center[0]; half.x = b->extents[0];
  center.z = b->center[2]; half.y = b->extents[1]; half.z = b->extents[2];
  m = *(BoxMatrix *)b->world;
  if (RayBox_004105e0(center, half, m, &distance) && distance < best &&
      RayObject_00411ac0(o, &distance) && distance < best) {
   best = distance;
   g_005022d4 = o;
  }
 }
 for (i = 0; i < g_005011c0.windows.count; i++) {
  PickObject *o = g_005011c0.windows.items[i];
  if (!o->selectable) continue;
  BoneP *b = o->bone;
  center.y = b->center[1]; center.x = b->center[0]; half.x = b->extents[0];
  center.z = b->center[2]; half.y = b->extents[1]; half.z = b->extents[2];
  m = *(BoxMatrix *)b->world;
  if (RayBox_004105e0(center, half, m, &distance) && distance < best &&
      RayObject_00411ac0(o, &distance) && distance < best) {
   best = distance;
   g_005022d4 = o;
  }
 }
 // Screen-space planes: 2D hit test in a 1024x768 virtual screen, nearest by depth.
 best = 10000.0f;
 for (i = 0; i < g_005011c0.planes.count; i++) {
  PickObject *o = g_005011c0.planes.items[i];
  if (!o->selectable) continue;
  BoneP *b = o->bone;
  m = *(BoxMatrix *)b->world;
  float sx = (float)(mx - left) / (float)(right - left) * 1024.0f;
  float sy = (float)(my - bottom) / (float)(top - bottom) * 768.0f;
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  // Inverse of this root window's presentation transform. Send the same local
  // coordinates to its script so slot selection and hover animation agree.
  sx = CompatOverlayMouseX((const char *)o + 0x14, sx);
#endif
  float px = m.m[4] * b->center[1] + m.m[8] * b->center[2] + m.m[0] * b->center[0] + m.m[12] - b->extra[0];
  float py = m.m[5] * b->center[1] + m.m[9] * b->center[2] + m.m[1] * b->center[0] + m.m[13] - b->extra[1];
  if (px <= sx && sx <= b->extra[0] + b->extra[0] + px && py <= sy && sy <= b->extra[1] + b->extra[1] + py) {
   float depth = b->center[2] + *(float *)((char *)b + 0x0c);
   if (depth < best) {
    g_005022d4 = o;
    best = depth;
    message.x = sx;
    message.y = sy;
   }
  }
 }
 if (g_005022d4) {
  message.code = 2;
  message.object = g_005022d4;
  g_005011c0.PostMessage_00424780(&message);
 }
 if (previous != g_005022d4) {
  if (previous) {
   message.code = 0xb;
   message.object = previous;
   g_005011c0.PostMessage_00424780(&message);
  }
  if (g_005022d4) {
   message.object = g_005022d4;
   message.code = 10;
   g_005011c0.PostMessage_00424780(&message);
  }
 }
}

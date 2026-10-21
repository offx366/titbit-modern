// Engine block 0x40c000-0x410000: matrix/vector helpers, game object bone API,
// resource holders released through the global resource manager (0x5ee6f0).
#include "lane_engine.h"
#include "lane_string.h"
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "../../native/widescreen_hooks.h"
#endif
extern "C" __declspec(dllimport) char *__stdcall CharNextA(const char *);

// MBCS strchr (0x40c3a0)
const char *__cdecl FindChar_0040c3a0(const char *text, char ch) {
 while (*text && *text != ch) text = CharNextA(text);
 return *text == ch ? text : 0;
}

struct Mat4_0040cba0 {
 float m[16];
 Mat4_0040cba0 &Copy_0040cba0(const Mat4_0040cba0 &o);
};
Mat4_0040cba0 &Mat4_0040cba0::Copy_0040cba0(const Mat4_0040cba0 &o) { *this = o; return *this; }

struct Vec3M {
 float x, y, z;
 Vec3M() {}
 Vec3M(float ax, float ay, float az) { x = ax; y = ay; z = az; }
 Vec3M &Add_0040cbc0(const Vec3M &o);
 Vec3M Transform_0040cbf0(const Mat4_0040cba0 &m) const;   // returned by value
};
Vec3M &Vec3M::Add_0040cbc0(const Vec3M &o) { x = o.x + x; y = o.y + y; z = o.z + z; return *this; }
Vec3M Vec3M::Transform_0040cbf0(const Mat4_0040cba0 &m) const {
 return Vec3M(m.m[0] * x + m.m[4] * y + m.m[8] * z + m.m[12],
              m.m[1] * x + m.m[5] * y + m.m[9] * z + m.m[13],
              m.m[2] * x + m.m[6] * y + m.m[10] * z + m.m[14]);
}

// String concatenation into a fresh buffer (0x40e8f0)
struct ConcatString : LaneString { int ConcatCopy_0040e8f0(int len1, const char *s1, int len2, const char *s2); };
int ConcatString::ConcatCopy_0040e8f0(int len1, const char *s1, int len2, const char *s2) {
 int total = len2 + len1;
 if (total != 0) {
  if (!AllocInline(total)) return 0;
  memcpy(data, s1, len1);
  memcpy(data + len1, s2, len2);
 }
 return 1;
}

// ---- Global resource manager ----
struct ResourceManager { void Release_0042c570(int id); };
extern ResourceManager g_005ee6f0;

struct ObservedSoundState { char name[32]; int a, b, c; ObservedSoundState(); void Reset(); };

// vtable 0x4cd56c: ctor 0x40e380, dtor 0x40e3c0, deleting 0x40e3a0
class SoundHolder_0040e380 {
public:
 ObservedSoundState state;          // +4
 char body[0x430 - 0x30];
 int resource;                      // +0x430
 SoundHolder_0040e380();
 virtual ~SoundHolder_0040e380();
};
SoundHolder_0040e380::SoundHolder_0040e380() {}
SoundHolder_0040e380::~SoundHolder_0040e380() { g_005ee6f0.Release_0042c570(resource); }

// vtable 0x4cd588: ctors 0x40f3a0/0x40f420, dtor 0x40f480, deleting 0x40f400
class Texture_0040f3a0 : public EngineObject {
public:
 int resource;                      // 0x14
 Vec3Z v18, v24, v30, v3c;           // 0x18..0x44
 Vec3Z scale;                       // 0x48
 float alpha;                       // 0x54
 Texture_0040f3a0();
 Texture_0040f3a0(int ownerObject);
 virtual ~Texture_0040f3a0();
#ifdef TITBIT_SOURCE_LINK
 virtual int GetType();
 virtual ObservedString Export();
 virtual void Update(int);
#endif
};
Texture_0040f3a0::Texture_0040f3a0() {
 alpha = 1.0f; scale.x = 1.0f; scale.y = 1.0f; scale.z = 1.0f;
}
Texture_0040f3a0::Texture_0040f3a0(int ownerObject) {
 alpha = 1.0f; scale.x = 1.0f; scale.y = 1.0f; scale.z = 1.0f;
 owner = ownerObject;
}
Texture_0040f3a0::~Texture_0040f3a0() { g_005ee6f0.Release_0042c570(resource); }

// Quaternion product using the 8-multiplication form (0x40df80).
struct QuatM {
 float x, y, z, w;
 void Mul_0040df80(QuatM *out, const QuatM &q) const;
};
// Every product is computed before the first store, as in the original: `out`
// may alias `this` or `q` (q.Mul(&q, r)).
void QuatM::Mul_0040df80(QuatM *out, const QuatM &q) const {
 float t = (q.y - q.z);
 float e2 = t * (z - y);
 float e4;
 float e3 = (x - w) * t;
 e4 = ((q.x - q.w) * (z + y));
 float a;
 a = (x + z) * (q.x + q.y);
 float b = ((q.x - q.y) * (x - z));
 float c;
 register float d;
 c = (q.w - q.z) * ((y + w));
 d = ((q.z + q.w) * (w - y));
 float e;
 e = (q.x + q.w) * (w + x);
 out->x = e - (((c + d + a + b) * 0.5f));
 out->y = (0.5f * ((((c + (a - b))) - d))) - e3;
 out->z = ((a - b - c) + d) * 0.5f - e4;
 out->w = ((0.5f * ((d - (a + b)) + c)) + e2);
}

// Engine sin/cos helpers (0x40df60, 0x40df70).
extern "C" double __stdcall FUN_0040df60(float);
extern "C" double __stdcall FUN_0040df70(float);
#include <math.h>

struct Vec3_00406f20 { float x, y, z; void Set_00407030(float, float, float); };

// ---- Game object bones (script API) ----
struct Quat4Z { float x, y, z, w; Quat4Z() { x = y = z = w = 0; } };
struct Mat4I {
 float m[16];
 Mat4I() {
  m[0] = m[5] = m[10] = m[15] = 1.0f;
  m[1] = m[2] = m[3] = m[4] = m[6] = m[7] = m[8] = m[9] = m[11] = m[12] = m[13] = m[14] = 0;
 }
};
struct Bone_0040c6d0 {                // 0xd8 bytes
 int flags;                         // +0
 Vec3Z position;                    // +4
 Quat4Z rotation;                   // +0x10
 Vec3Z scale;                       // +0x20
 Vec3Z center;                      // +0x2c
 Vec3Z v38, v44;                    // +0x38, +0x44
 int link;                          // +0x50
 Mat4I local, world;                // +0x54, +0x94
 int parent;                        // +0xd4
 Bone_0040c6d0();
 void SetRotation_0040ddc0(float x, float y, float z);
 Vec3M GetRotation_0040dc40() const;
 void UpdateMatrix_0040c7e0(int recompute);
};

// Rotation as Euler angles in degrees (0x40dc40).
Vec3M Bone_0040c6d0::GetRotation_0040dc40() const {
 float x2 = rotation.x + rotation.x, y2 = rotation.y + rotation.y, z2 = rotation.z + rotation.z;
 float xx = x2 * rotation.x, xy = y2 * rotation.x, xz = z2 * rotation.x;
 float yy = y2 * rotation.y, yz = z2 * rotation.y, zz = z2 * rotation.z;
 float xw = x2 * rotation.w, yw = y2 * rotation.w, zw = z2 * rotation.w;
 float m00 = 1.0f - (zz + yy), m01 = xy - zw, m01b = xy + zw;
 float m11 = 1.0f - (zz + xx), test = xz - yw, m12 = xw + yz, m22 = 1.0f - (yy + xx);
 float ax, ay, az;
 // Same comparison form as the original (test ah,5 / and eax,4100h): a NaN
 // `test` takes the +90 degree branch there, so it must here too.
 if (test < 1.0f) {
  if (test > -1.0f) { ax = (float)atan2(m12, m22); ay = -(float)asin(test); az = (float)atan2(m01b, m00); }
  else { ax = -(float)atan2(m01, m11); ay = -1.5707964f; az = 0.0f; }
 } else { ax = (float)atan2(m01, m11); ay = 1.5707964f; az = 0.0f; }
 Vec3M r;
 r.x = ax * 57.295776f; r.y = ay * 57.295776f; r.z = az * 57.295776f;
 return r;
}

// Set the rotation from Euler angles in degrees (0x40ddc0).
void Bone_0040c6d0::SetRotation_0040ddc0(float x, float y, float z) {
 float hx = x * 0.5f * 0.017453292f;
 QuatM qx; qx.w = (float)FUN_0040df70(hx); qx.x = (float)FUN_0040df60(hx); qx.y = 0; qx.z = 0;
 float hy = y * 0.5f * 0.017453292f;
 QuatM qy; qy.w = (float)FUN_0040df70(hy); qy.y = (float)FUN_0040df60(hy); qy.x = 0; qy.z = 0;
 float hz = z * 0.5f * 0.017453292f;
 QuatM qz; qz.w = (float)FUN_0040df70(hz); qz.z = (float)FUN_0040df60(hz); qz.x = 0; qz.y = 0;
 // Order as in the original: (qz * qy) * qx -- the first product is inlined
 // there (this = qz, q = qy), the second is the call to 0x40df80 (this = zy, q = qx).
 QuatM zy, r;
 qz.Mul_0040df80(&zy, qy);
 zy.Mul_0040df80(&r, qx);
 rotation.x = r.x; rotation.y = r.y; rotation.z = r.z; rotation.w = r.w;
}

Bone_0040c6d0::Bone_0040c6d0() {
 flags = 0; link = 0; parent = -1;
 scale.x = 1.0f; scale.y = 1.0f; scale.z = 1.0f;
}
typedef Bone_0040c6d0 Bone_0040ddc0;
class GameObjectBones {
public:
 char head[0x34];
 int boneCount;                     // 0x34
 Bone_0040ddc0 *bones;              // 0x38
 int pad3c;
 int dirty;                         // 0x40
 bool SetBonePosition_0040e970(int index, float x, float y, float z);
 bool SetBoneRotation_0040e9b0(int index, float x, float y, float z);
 bool SetBoneScale_0040ea00(int index, float x, float y, float z);
 bool SetBoneCenter_0040ea40(int index, float x, float y, float z);
 bool GetBoneRotation_0040ea80(int index, Vec3M *out);
 bool GetBonePosition_0040ead0(int index, Vec3M *out);
};
// The original range test uses && and therefore never rejects an index.
bool GameObjectBones::SetBonePosition_0040e970(int index, float x, float y, float z) {
 if (index < 0 && index >= boneCount) return false;
 Vec3Z &p = bones[index].position; p.x = x; p.y = y; p.z = z;
 dirty = 1; return true;
}
bool GameObjectBones::SetBoneRotation_0040e9b0(int index, float x, float y, float z) {
 if (index < 0 && index >= boneCount) return false;
 bones[index].SetRotation_0040ddc0(x, y, z);
 dirty = 1; return true;
}
bool GameObjectBones::SetBoneScale_0040ea00(int index, float x, float y, float z) {
 if (index < 0 && index >= boneCount) return false;
 Vec3Z &p = bones[index].scale; p.x = x; p.y = y; p.z = z;
 dirty = 1; return true;
}
bool GameObjectBones::SetBoneCenter_0040ea40(int index, float x, float y, float z) {
 if (index < 0 && index >= boneCount) return false;
 Vec3Z &p = bones[index].center; p.x = x; p.y = y; p.z = z;
 dirty = 1; return true;
}
bool GameObjectBones::GetBoneRotation_0040ea80(int index, Vec3M *out) {
 if (index < 0 && index >= boneCount) return false;
 *out = bones[index].GetRotation_0040dc40();
 return true;
}
bool GameObjectBones::GetBonePosition_0040ead0(int index, Vec3M *out) {
 if (index < 0 && index >= boneCount) return false;
 *out = *(const Vec3M *)&bones[index].position;
 return true;
}

// 4x4 matrix product into a temporary, then copied out (0x40cc90).
struct Mat4Mul {
 float m[16];
 Mat4Mul *Multiply_0040cc90(Mat4Mul *out, const Mat4Mul &b) const;
};
Mat4Mul *Mat4Mul::Multiply_0040cc90(Mat4Mul *out, const Mat4Mul &b) const {
 Mat4Mul r;
 for (int c = 0; c < 4; c++)
  for (int i = 0; i < 4; i++)
   r.m[c * 4 + i] = m[4 + i] * b.m[c * 4 + 1] + b.m[c * 4 + 2] * m[8 + i] + b.m[c * 4] * m[i] + b.m[c * 4 + 3] * m[12 + i];
 *out = r;
 return out;
}

// Rebuild a bone's world matrix from scale/rotation/position and its parent,
// refresh its bounding half-extents, then fold it into the GL modelview (0x40c7e0).
// Same class names as src/native/vector_geometry.cpp and frustum.cpp (published exact).
struct ObservedMatrix4 { float v[16]; ObservedMatrix4() { Identity(); } void Identity(); };
struct ObservedVector3 {
 float x, y, z;
 ObservedVector3(float a, float b, float c);
 ObservedVector3(const ObservedVector3 &v);
};
extern "C" __declspec(dllimport) void __stdcall glGetFloatv(unsigned, float *);
static inline float AbsF(float v) { return v < 0 ? -v : v; }
void Bone_0040c6d0::UpdateMatrix_0040c7e0(int recompute) {
 float *view = local.m;
 glGetFloatv(0xba6, view);                    // GL_MODELVIEW_MATRIX
 if (recompute == 1) {
  ObservedMatrix4 s;                          // identity via 0x40cc50
  float *w = world.m;
  w[0] = w[5] = w[10] = w[15] = 1.0f;
  w[1] = w[2] = w[3] = w[4] = w[6] = w[7] = w[8] = w[9] = w[11] = w[12] = w[13] = w[14] = 0;
  float x2 = rotation.x + rotation.x, y2 = rotation.y + rotation.y, z2 = rotation.z + rotation.z;
  float xx = x2 * rotation.x, xy = y2 * rotation.x, xz = z2 * rotation.x;
  float yy = y2 * rotation.y, yz = z2 * rotation.y, zz = z2 * rotation.z;
  float xw = x2 * rotation.w, yw = y2 * rotation.w, zw = z2 * rotation.w;
  w[0] = 1.0f - (zz + yy); w[4] = xy - zw; w[8] = yw + xz;
  w[1] = zw + xy; w[5] = 1.0f - (zz + xx); w[9] = yz - xw;
  w[2] = xz - yw; w[6] = xw + yz; w[10] = 1.0f - (yy + xx);
  s.v[0] = scale.x; s.v[5] = scale.y; s.v[10] = scale.z;
  s.v[1] = s.v[2] = s.v[3] = s.v[4] = 0; s.v[15] = 1.0f;
  Mat4Mul product;
  world = *(Mat4I *)((Mat4Mul *)s.v)->Multiply_0040cc90(&product, *(Mat4Mul *)w);
  w[12] = position.x; w[13] = position.y; w[14] = position.z;
  if (parent != -1) {
   Bone_0040c6d0 *p = this + (parent - flags);
   world = *(Mat4I *)((Mat4Mul *)p->world.m)->Multiply_0040cc90(&product, *(Mat4Mul *)w);
  }
  Mat4I m = world;
  m.m[12] = m.m[13] = m.m[14] = 0;
  float ex = v38.x;
  ObservedVector3 r(m.m[0] * ex + (m.m[8] + m.m[4]) * 0.0f,
                    m.m[1] * ex + (m.m[9] + m.m[5]) * 0.0f,
                    m.m[2] * ex + (m.m[10] + m.m[6]) * 0.0f);
  v44.x = AbsF(r.x); v44.z = AbsF(r.z); v44.y = AbsF(r.y);
  Vec3M t, u;
  ((Vec3_00406f20 *)&t)->Set_00407030(0, v38.y, 0);
  u = t.Transform_0040cbf0(*(Mat4_0040cba0 *)m.m);
  ObservedVector3 a(*(ObservedVector3 *)&u);
  t.x = AbsF(a.x); t.y = AbsF(a.y); t.z = AbsF(a.z);
  ((Vec3M *)&v44)->Add_0040cbc0(t);
  ((Vec3_00406f20 *)&t)->Set_00407030(0, 0, v38.z);
  u = t.Transform_0040cbf0(*(Mat4_0040cba0 *)m.m);
  ObservedVector3 b(*(ObservedVector3 *)&u);
  t.x = AbsF(b.x); t.y = AbsF(b.y); t.z = AbsF(b.z);
  ((Vec3M *)&v44)->Add_0040cbc0(t);
 }
 Mat4Mul product2;
 ((Mat4_0040cba0 *)view)->Copy_0040cba0(*(Mat4_0040cba0 *)((Mat4Mul *)view)->Multiply_0040cc90(&product2, *(Mat4Mul *)world.m));
}

// Textured quad attached to a bone of its owner (0x40f4e0).
extern "C" {
 __declspec(dllimport) void __stdcall glEnable(unsigned);
 __declspec(dllimport) void __stdcall glDisable(unsigned);
 __declspec(dllimport) void __stdcall glBlendFunc(unsigned, unsigned);
 __declspec(dllimport) void __stdcall glColor4f(float, float, float, float);
 __declspec(dllimport) void __stdcall glPushMatrix(void);
 __declspec(dllimport) void __stdcall glPopMatrix(void);
 __declspec(dllimport) void __stdcall glLoadMatrixf(const float *);
 __declspec(dllimport) void __stdcall glBindTexture(unsigned, unsigned);
 __declspec(dllimport) void __stdcall glBegin(unsigned);
 __declspec(dllimport) void __stdcall glEnd(void);
 __declspec(dllimport) void __stdcall glTexCoord2f(float, float);
 __declspec(dllimport) void __stdcall glVertex3f(float, float, float);
}
// Virtual Update(int time) (slot 3, ret 4): draws, then passes the time on along the chain.
struct UpdateChain { virtual void s0(); virtual void s1(); virtual void s2(); virtual void Update(int time); };
struct TextureView : Texture_0040f3a0 { void Draw_0040f4e0(int time); };
void TextureView::Draw_0040f4e0(int time) {
 glEnable(0xde1);                       // GL_TEXTURE_2D
 glEnable(0xbe2);                       // GL_BLEND
 glBlendFunc(0x302, 0x303);             // SRC_ALPHA, ONE_MINUS_SRC_ALPHA
 glColor4f(scale.x, scale.y, scale.z, alpha);
 glPushMatrix();
 GameObjectBones *object = (GameObjectBones *)owner;
 glLoadMatrixf(object->bones[field8].local.m);
 glBindTexture(0xde1, resource);
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 int fullscreen_effect = CompatBeginFullscreenEffect(v24.x, v24.y, v18.x, v18.y, v3c.x, v3c.y);
#endif
 glBegin(5);                            // GL_TRIANGLE_STRIP
 glTexCoord2f(v30.x + v3c.x, v30.y);
 glVertex3f(v24.x + v18.x, v24.y, v24.z);
 glTexCoord2f(v30.x, v30.y);
 glVertex3f(v24.x, v24.y, v24.z);
 glTexCoord2f(v30.x + v3c.x, v30.y + v3c.y);
 glVertex3f(v24.x + v18.x, v18.y + v24.y, v24.z);
 glTexCoord2f(v30.x, v30.y + v3c.y);
 glVertex3f(v24.x, v18.y + v24.y, v24.z);
 glEnd();
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 CompatEndFullscreenEffect(fullscreen_effect);
#endif
 glDisable(0xde1);
 glPopMatrix();
 glColor4f(1.0f, 1.0f, 1.0f, 1.0f);
 if (child) ((UpdateChain *)child)->Update(time);
}

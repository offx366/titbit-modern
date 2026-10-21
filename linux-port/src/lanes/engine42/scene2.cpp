#define OBSERVED_STRING_WTL_BUFFER  // GetBuffer/ReleaseBuffer expanded inline (WTL)
#define OBSERVED_STRING_INLINE_COPY  // CString copy ctor expanded inline (WTL)
#define OBSERVED_STRING_WTL_LOADSTRING  // WTL CString layout (see engine_string.h)
#define OBSERVED_STRING_RELEASE_EXTERNAL  // CString::Release out of line (0x402180)
// Scene: camera/lighting/settings readers, interface overlay, object removal,
// script entry points (0x420200, 0x423e40-0x425fd0).
#include "lane_xml.h"
#include "e42_scene.h"
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "../../native/widescreen_hooks.h"
#endif
extern "C" {
 __declspec(dllimport) void __stdcall glMatrixMode(unsigned);
 __declspec(dllimport) void __stdcall glOrtho(double, double, double, double, double, double);
 __declspec(dllimport) void __stdcall glDepthMask(unsigned char);
 void *__cdecl memmove(void *, const void *, unsigned);
 double __cdecl atof(const char *);
}
void __cdecl Log_00403650(const char *text);
extern "C" char *__cdecl strcpy(char *, const char *);
#include <math.h>
#pragma intrinsic(strcpy)

struct DomNode42 {
 virtual void s0();
 virtual void Release(int);
 virtual void s2(); virtual void s3(); virtual void s4();
 virtual const std::string *Name();
 virtual void s6(); virtual void s7(); virtual void s8(); virtual void s9(); virtual void s10();
 virtual DomNode42 *FirstChild();
 virtual void s12(); virtual void s13();
 virtual DomNode42 *NextSibling();
 virtual XmlElement_v *ToElement();
 int refs;
};

struct Camera_0041e8f0 {
 void SetAmbient_0041f510(const float *color);
 void SetMatrix_0041f800(const Mat4E42 *matrix);
};
extern Camera_0041e8f0 g_005026d0;
struct Color4E42 { float r, g, b, a; };
Color4E42 __cdecl ReadColor_00412c90(DomNode42 *node);
Vec3_00406f00 __cdecl ReadVec3_00413a20(DomNode42 *node);
extern SceneObject *g_005022d4;                     // object under the mouse
extern Scene g_005011c0;                   // the game scene

struct SoundStream42 {
 unsigned char body[0x30];
 int stream;                                        // +0x30
 void Load_00429d00(DomNode42 *node);
 void Play_00429ca0(bool loop);
};
struct ObjectList42 : ScenePtrArray<SceneObject *> {
 void SetSize_00411f60(int size, int grow);
 void Add_00411d70(SceneObject *window);
};
struct EngineObject42 { void Detach_00413850(); };
struct TextTable42 { const char *Find_0044dd10(const char *key); };
void __stdcall ConstructPointers_004120d0(SceneObject **, int);

void Mat4E42::SetTranslation_00420200(const Vec3_00406f00 &v) {
 m[12] = v.x;
 m[13] = v.y;
 m[14] = v.z;
}

// <lightning><ambient .../></lightning>
// NONMATCHING: faithful translation
void Scene::ReadLighting_00423e40(DomNode42 *node) {
 for (; node; node = node->NextSibling()) {
  if (*node->Name() == "lightning") {
   for (DomNode42 *child = node->FirstChild(); child; child = child->NextSibling()) {
    if (*child->Name() == "ambient") {
     Color4E42 color = ReadColor_00412c90(child);
     g_005026d0.SetAmbient_0041f510(&color.r);
    }
   }
  }
 }
}

// <camera fov=".."><position/><rotation/></camera>
// NONMATCHING: faithful translation
void Scene::ReadCamera_00423f80(DomNode42 *node) {
 std::string unused;
 for (; node; node = node->NextSibling()) {
  if (*node->Name() == "camera") {
   Mat4E42 &matrix = *(Mat4E42 *)&projection;
   Vec3_00406f00 rotation(0, 0, 0), position(0, 0, 0);
   Mat4E42 step;
   XmlElement_v *element = node->ToElement();
   XmlAttr_v *fovAttribute = element->Attribute(std::string("fov"));
   if (fovAttribute) projection.fov = (float)atof(fovAttribute->Value()->c_str());
   for (DomNode42 *child = node->FirstChild(); child; child = child->NextSibling()) {
    if (child->Name()->compare("position") == 0) position = ReadVec3_00413a20(child);
    else if (child->Name()->compare("rotation") == 0) rotation = ReadVec3_00413a20(child);
   }
   matrix.Identity_0040cc50();
   step.Identity_0040cc50();
   step.RotateX_0041fdd0(rotation.x);
   matrix.Assign_0040cba0(step.Mul_0040cc90(matrix));
   step.Identity_0040cc50();
   step.RotateY_0041fe00(rotation.y);
   matrix.Assign_0040cba0(step.Mul_0040cc90(matrix));
   step.Identity_0040cc50();
   step.RotateZ_0041fe30(rotation.z);
   matrix.Assign_0040cba0(step.Mul_0040cc90(matrix));
   matrix.SetTranslation_00420200(position);
   cameraSet = true;
   g_005026d0.SetMatrix_0041f800(&matrix);
  }
 }
}

// Interface objects in a 1024x768 orthographic pass, back to front.
// NONMATCHING: faithful translation
void Scene::DrawOverlay_00424a30() {
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 CompatBeginOverlay();
#endif
 glPushMatrix();
 glLoadIdentity();
 glMatrixMode(0x1701);                               // GL_PROJECTION
 glPushMatrix();
 glLoadIdentity();
 glOrtho(0, 1024, 768, 0, -10000, 20000);
 glDepthMask(0);
 glDisable(0xb71);                                   // GL_DEPTH_TEST
 glEnable(0xbc0);
 glEnable(0xbe2);
 glEnable(0xde1);
 glMatrixMode(0x1700);                               // GL_MODELVIEW
 for (int i = windows.size - 1; i >= 0; i--) {
  SceneObject *window = windows.data[i];
  SceneMesh *mesh = window->mesh;
  // written as the original's skip tests (NaN coordinates still draw)
  if (!mesh) continue;
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  bool cursor = window == pointNode;
  // The cursor follows the world mouse into the extended side fields. Every
  // other interface object retains the original horizontal canvas bounds.
  if (!cursor) {
#endif
  if (mesh->ox + mesh->x + mesh->width < 0.0f) continue;
  if (mesh->ox + mesh->x - mesh->width > 1024.0f) continue;
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  }
#endif
  if (mesh->y + mesh->height + mesh->oy < 0.0f) continue;
  if (mesh->y + mesh->oy - mesh->height > 768.0f) continue;
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  if (cursor) CompatBeginCursorOverlay();
#endif
  window->Update(g_005026bc);
  window->Render(g_005026bc);
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
  if (cursor) CompatEndCursorOverlay();
#endif
 }
 glDisable(0xde1);
 glDisable(0xbc0);
 glDisable(0xbe2);
 glEnable(0xb71);
 glDepthMask(1);
 glMatrixMode(0x1701);
 glPopMatrix();
 glMatrixMode(0x1700);
 glPopMatrix();
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 CompatEndOverlay();
#endif
}


template<class T> static inline void RemoveFrom(ScenePtrArray<T> &list, T item) {
 for (int i = 0; i < list.size; i++) {
  if (list.data[i] == item) {
   int move = list.size - i - 1;
   if (move) memmove(&list.data[i], &list.data[i + 1], move * sizeof(T));
   list.size--;
   break;
  }
 }
}

// Removes and deletes an object (message 4); statics force an octree rebuild.
// NONMATCHING: faithful translation
void Scene::RemoveObject_004256d0(SceneObject *object) {
 bool rebuild = false;
 if (object->reserved4) ((EngineObject42 *)object)->Detach_00413850();
 RemoveFrom(windows, object);
 RemoveFrom(objects, object);
 for (int s = 0; s < statics.size; s++) {
  if (statics.data[s] == object) {
   int move = statics.size - s - 1;
   if (move) memmove(&statics.data[s], &statics.data[s + 1], move * sizeof(SceneObject *));
   statics.size--;
   rebuild = true;
   break;
  }
 }
 for (int n = messages.size, i = 0; n; n--, i++)
  if (messages.data[i].selected == object) messages.data[i].selected = 0;
 if (rebuild) {
  ((ObjectList42 *)&spatial.storage)->SetSize_00411f60(0, -1);
  SpatialNodeE42 *root = (SpatialNodeE42 *)&spatial.root;
  root->count = 0;
  root->objects = 0;
  if (root->split) {
   for (int i = 0; i < 8; i++) {
    if (root->children[i]) delete root->children[i];
    root->children[i] = 0;
   }
  }
  root->split = false;
  g_005011c0.BuildOctree_00423a80(false);
 }
 if (g_005022d4 == object) g_005022d4 = 0;
 delete object;
}

// NONMATCHING: faithful translation
void Scene::CreateTextWindowI_00425640(const char *key, int x, int y, int width, int height,
                                                int a, int b, const char *font) {
 const char *text = ((TextTable42 *)&pairs)->Find_0044dd10(key);
 if (!text) return;
 CreateTextWindow_00424bb0(0, text, x, y, width, height, a, b, font);
}

// Script SCENE.DeleteObject
void Scene::DeleteObject_00425690(SceneObject *object) {
 ObservedPickingMessage message;
 memset(&message, 0, sizeof(message));
 message.selected = object;
 message.event = 4;
 Send_00424780(&message);
}

// Script SCENE.Add(object, kind)
// NONMATCHING: faithful translation
void Scene::AddObject_00425860(SceneObject *object, int kind) {
 if (!object) return;
 if (kind == 1) {
  int index = objects.size;
  ((ObjectList42 *)&objects)->SetSize_00411f60(index + 1, -1);
  objects.data[index] = object;
  return;
 }
 if (kind == 2) { ((ObjectList42 *)&windows)->Add_00411d70(object); return; }
 int index = statics.size;
 int newSize = index + 1;
 if (newSize >= 0) {
  if (newSize == 0) {
   if (statics.data) { ::operator delete(statics.data); statics.data = 0; }
   statics.capacity = statics.size = 0;
  } else if (statics.data == 0) {
   statics.data = (SceneObject **)::operator new(newSize * sizeof(SceneObject *));
   if (statics.data) memset(statics.data, 0, newSize * sizeof(SceneObject *));
   statics.capacity = newSize;
   statics.size = newSize;
  } else if (newSize > statics.capacity) {
   int grow = statics.grow_by;
   if (grow == 0) {
    grow = statics.size / 8;
    grow = (grow < 4) ? 4 : ((grow > 1024) ? 1024 : grow);
   }
   int newMax = statics.capacity + grow;
   if (newMax <= newSize) newMax = newSize;
   SceneObject **data = (SceneObject **)::operator new(newMax * sizeof(SceneObject *));
   memcpy(data, statics.data, statics.size * sizeof(SceneObject *));
   if (statics.size < newSize) ConstructPointers_004120d0(&data[statics.size], newSize - statics.size);
   ::operator delete(statics.data);
   statics.data = data;
   statics.size = newSize;
   statics.capacity = newMax;
  } else {
   if (index < newSize) memset(&statics.data[index], 0, (newSize - index) * sizeof(SceneObject *));
   statics.size = newSize;
  }
 }
 statics.data[index] = object;
}

// <stream_sound .../> background music
// NONMATCHING: faithful translation
void Scene::ReadSettings_00425cc0(DomNode42 *node) {
 std::string unused;                                  // original: constructed, never used
 for (; node; node = node->NextSibling())
  if (*node->Name() == "stream_sound") ((SoundStream42 *)&sound)->Load_00429d00(node);
 if (((SoundStream42 *)&sound)->stream) ((SoundStream42 *)&sound)->Play_00429ca0(true);
}

// Script SCENE.SetCursorType
// NONMATCHING: faithful translation
void Scene::SetCursorType_00425de0(int type) {
 cursorType = type;
 if (pointNode) {
  ObservedPickingMessage message;
  memset(&message, 0, sizeof(message));
  message.selected = 0;
  strcpy((char *)message.reserved0, "cursor");
  message.event = 0xc;
  ((int *)message.reserved28)[0] = type;
  g_005011c0.Send_00424780(&message);
  Log_00403650("Cursor");
  ((int *)pointNode)[0x10] = 1;
 }
}

class GameObject_0040e630 : public SceneObject {
 unsigned char body[0x88 - sizeof(SceneObject)];
public:
 bool selectable;
 GameObject_0040e630();
 void AddComponent_0041e520(void *component);
 bool BindScript_0040e720(ObservedString source);
};
struct Bone_0040c6d0 { SceneMesh mesh; unsigned char rest[0xd8 - sizeof(SceneMesh)]; Bone_0040c6d0(); ~Bone_0040c6d0(); };  // dtor 0x4051b0 (empty, out of line)
class AviPlane_0040b3b0 {
public:
 void *vtable;
 unsigned reserved4[6];
 float width, height;          // 0x1c
 int p6;                       // 0x24
 int frame, time, state;       // 0x28
 int p7, p8, p9, p10, p11, p12; // 0x34
 unsigned char reserved4c[0x120 - 0x4c];
 char file[0x20];              // 0x120
 bool loop;                    // 0x140
 unsigned char reserved141[0x164 - 0x141];
 AviPlane_0040b3b0(GameObject_0040e630 *owner);
 void Start_0040be20();
};

// Creates a full-screen style AVI plane interface object.
// NONMATCHING: faithful translation
SceneObject *Scene::CreateAviPlane_00425a20(float x, float y, float z, float width, float height,
                                                     int p6, int p7, int p8, int p9, int p10, int p11,
                                                     int p12, bool loop, const char *file, const char *script) {
 GameObject_0040e630 *object = new GameObject_0040e630;
 AviPlane_0040b3b0 *plane = new AviPlane_0040b3b0(object);
 object->shape = (void *)1;
 Bone_0040c6d0 *bone = new Bone_0040c6d0[1];
 object->mesh = &bone->mesh;
 SceneMesh *mesh = object->mesh;
 mesh->ox = x; mesh->oy = y; mesh->oz = z;
 ((int *)object)[0x10] = 1;
 object->selectable = true;
 float halfWidth = width * 0.5;
 float halfHeight = height * 0.5f;
 mesh->width = halfWidth;
 mesh->depth = 0;
 mesh->height = halfHeight;
 mesh = object->mesh;
 mesh->z = 0;
 mesh->x = halfWidth;
 mesh->y = halfHeight;
 mesh = object->mesh;
 mesh->radius = (float)sqrt(mesh->depth * mesh->depth + mesh->height * mesh->height + mesh->width * mesh->width);
 object->AddComponent_0041e520(plane);
 ((ObjectList42 *)&windows)->Add_00411d70(object);
 object->BindScript_0040e720(ObservedString(script));
 strcpy(plane->file, file);
 plane->frame = 0; plane->time = 0; plane->state = 0;
 plane->width = width; plane->height = height; plane->p6 = p6;
 plane->p7 = p7; plane->p8 = p8; plane->p9 = p9; plane->p10 = p10; plane->p11 = p11; plane->p12 = p12;
 plane->loop = loop;
 plane->Start_0040be20();
 ObservedPickingMessage message;
 memset(&message, 0, sizeof(message));
 message.event = 3;
 message.selected = object;
 Send_00424780(&message);
 return object;
}

// Script CAMERA.GetCamera: camera position and Euler angles (degrees); returns the fov.
struct CameraScript {  // 0x420220 (was CameraScript_00420220)
 unsigned char reserved[0xebfc4];
 float m[16];
 float scale, fov;
 float GetCamera_00420220(Vec3_00406f00 *position, Vec3_00406f00 *angles);
};
extern "C" double __cdecl asin(double);

// Inline vector setter (arguments evaluated before the three stores).
inline void SetVec42(Vec3_00406f00 *v, float ax, float ay, float az) { v->x = ax; v->y = ay; v->z = az; }

// NONMATCHING: faithful translation
float CameraScript::GetCamera_00420220(Vec3_00406f00 *position, Vec3_00406f00 *angles) {
 SetVec42(position, m[12], m[13], m[14]);
 if (m[2] < 1.0f) {
  if (m[2] > -1.0f) {
   angles->x = (float)atan2(m[6], m[10]);
   angles->y = -(float)asin(m[2]);
   angles->z = (float)atan2(m[1], m[0]);
  } else {
   angles->x = -(float)atan2(m[4], m[5]);
   angles->y = -1.5707964f;
   angles->z = 0;
  }
 } else {
  angles->x = (float)atan2(m[4], m[5]);
  angles->y = 1.5707964f;
  angles->z = 0;
 }
 angles->x *= 57.295776f;
 angles->y *= 57.295776f;
 angles->z *= 57.295776f;
 return fov;
}

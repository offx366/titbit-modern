// AVI video plane (vtable 0x4cd540, 0x164 bytes): a textured quad on a bone of
// its owner whose texture is refreshed from an AVI stream every frame.
// Constructors, Open, Close, Tick: lanes/claude/engine_408.cpp.
#include "e40_engine.h"
#include "lane_xml.h"
#include "e40_gl.h"
extern "C" {
__declspec(dllimport) void *__stdcall CreateCompatibleDC(void *);
void *__stdcall DrawDibOpen(void);
int __stdcall DrawDibDraw(void *, void *, int, int, int, int, void *, void *, int, int, int, int, unsigned);
void *__stdcall AVIStreamGetFrame(void *, long);
char *__cdecl strcpy(char *, const char *);
}
#pragma intrinsic(strcpy)
#ifdef TITBIT_COMPAT
#include "../../compat/compat.h"   /* VfW frame decoding without installed codecs (src/compat/README.md) */
#endif

struct TextureCache { // original global 0x5ee6f0
 void Release_0042c570(int id);
 int Create_0042c760(ObservedString name, int flags, int width, int height, int bits);
};
extern TextureCache g_005ee6f0;
Vec3V __cdecl ReadVec3_00413a20(XmlNode_v *node);

struct BoneFrame { char head[0x54]; float matrix[16]; char tail[0xd8 - 0x94]; };
struct BoneOwner { char head[0x38]; BoneFrame *bones; };

class AviPlane_0040b320 : public EngineObject {
public:
 unsigned lastTime;              // 0x14
 unsigned texture;               // 0x18
 Vec3Z size;                     // 0x1c
 Vec3Z position;                 // 0x28
 Vec3Z uv;                       // 0x34
 Vec3Z uvSize;                   // 0x40
 int repeat;                     // 0x4c
 char info[0x8c];                // 0x50  AVISTREAMINFO
 void *stream;                   // 0xdc
 void *frames;                   // 0xe0
 char bmi[0x28];                 // 0xe4
 unsigned length;                // 0x10c
 int width, height;              // 0x110
 void *pixels;                   // 0x118
 unsigned msPerFrame;            // 0x11c
 char file[0x20];                // 0x120
 bool keying;                    // 0x140
 int pad144;
 void *drawDib;                  // 0x148
 void *bitmap;                   // 0x14c
 void *dc;                       // 0x150
 unsigned char *bits;            // 0x154
 unsigned elapsed;               // 0x158
 unsigned frame;                 // 0x15c
 bool playing;                   // 0x160
 AviPlane_0040b320();
 virtual ~AviPlane_0040b320();
 virtual int GetType();
 virtual ObservedString Export();
 virtual void Update(int time);
 void Open_0040bb20(const char *file);
 void SwapRedBlue_0040bc60(unsigned char *pixels);
 void Key_0040bca0(unsigned char *pixels);
 void ShowFrame_0040bd20(long index);
 void Close_0040bde0();
 void Start_0040be20();
 void Free_0040bed0();
 void Tick_0040bef0();
 void Load_0040b640(XmlNode_v *node);
};

AviPlane_0040b320::~AviPlane_0040b320() { Free_0040bed0(); }

ObservedString AviPlane_0040b320::Export() {
 ObservedString xml, number;
 return xml;
}

void AviPlane_0040b320::Update(int time) {
 if (playing) {
  unsigned shown = frame;
  Tick_0040bef0();
  if (frame >= length) {
   if (repeat > 0) repeat--;
   if (repeat == 0) {
    Detach_00413850();
    delete this;
    return;
   }
   frame = 0;
   elapsed = 0;
  }
  if (shown != frame) ShowFrame_0040bd20(frame);
  glEnable(0xbc0);
  glEnable(0xbe2);
  glEnable(0xde1);
  glBlendFunc(0x302, 0x303);
  glColor4f(1.0f, 1.0f, 1.0f, 1.0f);
  glPushMatrix();
  glLoadMatrixf(((BoneOwner *)owner)->bones[field8].matrix);
  glBindTexture(0xde1, texture);
  glBegin(7);
  glTexCoord2f(uvSize.x + uv.x, uv.y);
  glVertex3f(size.x + position.x, position.y, position.z);
  glTexCoord2f(uv.x, uv.y);
  glVertex3f(position.x, position.y, position.z);
  glTexCoord2f(uv.x, uvSize.y + uv.y);
  glVertex3f(position.x, size.y + position.y, position.z);
  glTexCoord2f(uvSize.x + uv.x, uvSize.y + uv.y);
  glVertex3f(size.x + position.x, size.y + position.y, position.z);
  glEnd();
  glDisable(0xde1);
  glDisable(0xbc0);
  glDisable(0xbe2);
  glPopMatrix();
 }
 if (next) next->Update(time);
}

void AviPlane_0040b320::Load_0040b640(XmlNode_v *node) {
 XmlElement_v *element = node->ToElement();
 std::string text;
 if (element) {
  XmlAttr_v *a = element->Attribute(std::string("aviname"));
  if (a) {
   text = *a->Value();
   strcpy(file, text.c_str());
  }
  a = element->Attribute(std::string("keying"));
  if (a) keying = atoi(a->Value()->c_str()) != 0;
  a = element->Attribute(std::string("repeat"));
  if (a) repeat = atoi(a->Value()->c_str());
  for (XmlNode_v *child = node->FirstChild(); child; child = child->NextSibling()) {
   if (*child->Name() == "position") *(Vec3V *)&position = ReadVec3_00413a20(child);
   else if (*child->Name() == "size") *(Vec3V *)&size = ReadVec3_00413a20(child);
   else if (*child->Name() == "uvposition") *(Vec3V *)&uv = ReadVec3_00413a20(child);
   else if (*child->Name() == "uvsize") *(Vec3V *)&uvSize = ReadVec3_00413a20(child);
  }
  if (--element->refs <= 0) element->Destroy(1);
 }
 Start_0040be20();
}

void AviPlane_0040b320::Key_0040bca0(unsigned char *p) {
 int count = height * width;
 if (!keying) {
  do {
   p[3] = 0xff;
   p += 4;
  } while (--count);
  return;
 }
 {
  do {
   if (p[0] < 100 && p[1] < 100 && p[2] > 19) { p[3] = -p[2] - 1; p[2] = 0; }
   else p[3] = 0xff;
   p += 4;
  } while (--count);
 }
}

void AviPlane_0040b320::ShowFrame_0040bd20(long index) {
 struct DibInfo { unsigned long size; long w, h; unsigned short planes, bits; unsigned long compression, image, xppm, yppm, used; };
 DibInfo *dib = (DibInfo *)AVIStreamGetFrame(frames, index);
 if (!dib) return;
 pixels = (char *)dib + dib->size + dib->used * 4;
 DrawDibDraw(drawDib, dc, 0, 0, width, height, dib, pixels, 0, 0, width, height, 0);
 SwapRedBlue_0040bc60(bits);
 Key_0040bca0(bits);
 glBindTexture(0xde1, texture);
 glTexSubImage2D(0xde1, 0, 0, 0, width, height, 0x1908, 0x1401, bits);
}

void AviPlane_0040b320::Start_0040be20() {
 dc = CreateCompatibleDC(0);
 drawDib = DrawDibOpen();
 Open_0040bb20(file);
 if (!frames || !bits || !msPerFrame) return;
 texture = g_005ee6f0.Create_0042c760("texture256x256", 0, 0x400, 0x400, 0x20);
 playing = true;
 uvSize.x = (width * 0.0009765625f - 0.01f) * uvSize.x;
 uvSize.y = (height * 0.0009765625f - 0.01f) * uvSize.y;
 uv.y -= uvSize.y + 1.0f;
}

void AviPlane_0040b320::Free_0040bed0() {
 Close_0040bde0();
 if (texture) g_005ee6f0.Release_0042c570(texture);
}

// AVI.Create script function
AviPlane_0040b320 *__cdecl CreateAvi_0040bf30(float px, float py, float pz, float sx, float sy, float sz,
                                               float ux, float uy, float uz, float wx, float wy, float wz,
                                               bool keying, const char *file, int repeat) {
 AviPlane_0040b320 *avi = new AviPlane_0040b320;
 strcpy(avi->file, file);
 avi->position.x = px; avi->position.y = py; avi->position.z = pz;
 avi->size.x = sx; avi->size.y = sy; avi->size.z = sz;
 avi->uv.x = ux; avi->uv.y = uy; avi->uv.z = uz;
 avi->uvSize.x = wx; avi->uvSize.y = wy; avi->uvSize.z = wz;
 avi->keying = keying;
 avi->repeat = repeat;
 avi->Start_0040be20();
 return avi;
}

// Native 0x40ba00.
int AviPlane_0040b320::GetType(){return 8;}

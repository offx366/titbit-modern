// Engine block 0x408000-0x40c000: component links, AVI plane, small accessors.
#include "lane_engine.h"
#include "lane_string.h"
extern "C" {
 __declspec(dllimport) int __stdcall DeleteObject(void *);
 __declspec(dllimport) int __stdcall DrawDibClose(void *);
 __declspec(dllimport) long __stdcall AVIStreamGetFrameClose(void *);
 __declspec(dllimport) unsigned long __stdcall AVIStreamRelease(void *);
 __declspec(dllimport) void __stdcall AVIFileExit(void);
 __declspec(dllimport) char *__stdcall CharNextA(const char *);
 void __cdecl free(void *);
}

// ---- Component list (owner->+0x10 is the head, +8 links siblings) ----
struct ComponentLink {
 void *vtable;
 struct ComponentOwner *owner;
 ComponentLink *next;
 void Append_0040b270(ComponentLink *item);
 void Unlink_0040b2a0();
};
struct ComponentOwner { int pad[4]; ComponentLink *first; };

void ComponentLink::Append_0040b270(ComponentLink *item) {
 if (next) {
  ComponentLink *p = next;
  while (p->next) p = p->next;
  p->next = item;
  return;
 }
 next = item;
}

void ComponentLink::Unlink_0040b2a0() {
 ComponentLink *p = owner->first;
 if (p == this) { owner->first = next; return; }
 if (p) {
  while (p->next != this) p = p->next;
  p->next = next;
 }
}

// ---- Resource with a name and a malloc'd buffer (vtable 0x4cd4cc) ----
struct NameString : LaneString {
 NameString() { Init(); }
 NameString &operator=(const char *text) {
  int length = text ? lstrlenA(text) : 0;
  if (Header()->refs > 1 || length > Header()->capacity) {
   ReleaseInline();
   if (length == 0) Init();
   else {
    LaneStringHeader *p = (LaneStringHeader *)::operator new(length + 13);
    if (!p) return *this;
    p->refs = 1; *(length + 12 + (char *)p) = 0; p->length = length; p->capacity = length;
    data = (char *)(p + 1);
   }
  }
  memcpy(data, text, length); Header()->length = length; data[length] = 0;
  return *this;
 }
 ~NameString() {
  if (Header() != observed_empty_header && InterlockedDecrement(&Header()->refs) <= 0)
   delete (unsigned char *)Header();
 }
};

class NamedBuffer_00408a40 : public EngineObject {
public:
 int pad14[2];
 float scaleX, scaleY, step;   // 0x1c, 0x20, 0x24
 NameString name;              // 0x28
 int mode;                     // 0x2c
 void *buffer;                 // 0x30
 NamedBuffer_00408a40();
 NamedBuffer_00408a40(int ownerObject);
 virtual ~NamedBuffer_00408a40();
#ifdef TITBIT_SOURCE_LINK
 virtual int GetType();
 virtual ObservedString Export();
 virtual void Update(int);
#endif
};
NamedBuffer_00408a40::NamedBuffer_00408a40() {
 name = " ";
 scaleX = 1.0f; scaleY = 1.0f; step = 0.02f; mode = 1; buffer = 0;
}
NamedBuffer_00408a40::NamedBuffer_00408a40(int ownerObject) {
 owner = ownerObject;
 name = " ";
 scaleX = 1.0f; scaleY = 1.0f; step = 0.02f; mode = 2; buffer = 0;
}
NamedBuffer_00408a40::~NamedBuffer_00408a40() {
 if (buffer) free(buffer);
 buffer = 0;
}

// ---- String reverse find returning an index (0x409580) ----
struct LaneStringFind : LaneString {
 int ReverseFind_00409580(char ch) const;
 LaneStringFind &Append_00409960(const char *text);
};
LaneStringFind &LaneStringFind::Append_00409960(const char *text) {
 int length;
 if (text == 0 || (length = lstrlenA(text)) == 0) return *this;
 LaneStringHeader *old = Header();
 if (old->refs < 2 && old->length + length <= old->capacity) {
  memcpy(data + old->length, text, length);
  Header()->length += length;
  data[Header()->length] = 0;
  return *this;
 }
 int oldLength = old->length;
 if (oldLength + length != 0) {
  if (!Allocate_00402120(oldLength + length)) return *this;
  memcpy(data, old + 1, oldLength);
  memcpy(data + oldLength, text, length);
 }
 if (old != observed_empty_header && InterlockedDecrement(&old->refs) <= 0) delete (unsigned char *)old;
 return *this;
}
int LaneStringFind::ReverseFind_00409580(char ch) const {
 const char *last = 0;
 const char *p = data;
 if (*p) {
  do {
   if (*p == ch) last = p;
   p = CharNextA(p);
  } while (*p);
  if (last) return last - data;
 }
 return -1;
}

// ---- Array of 0x434-byte slots (0x40a6f0, 0x40a720) ----
struct Slot434 {
 virtual void Activate(int);
 char pad[0x20];
 int used;                 // 0x24
 int busy;                 // 0x28
 int level;                // 0x2c
 char rest[0x434 - 0x30];
};
extern "C" __declspec(dllimport) char *__stdcall CharLowerA(char *);
extern "C" __declspec(dllimport) int __stdcall lstrcmpA(const char *, const char *);
struct ByValueString : LaneString {
 ~ByValueString() {
  if (Header() != observed_empty_header && InterlockedDecrement(&Header()->refs) <= 0)
   delete (unsigned char *)Header();
 }
};
struct SlotTable_0040a6f0 {
 int pad; int count; Slot434 *items;
 int Find_0040a5d0(ByValueString name);
 Slot434 *At_0040a6f0(int index);
 int ActivateFree_0040a720();
};
Slot434 *SlotTable_0040a6f0::At_0040a6f0(int index) {
 if (index >= 0 && index < count) return &items[index];
 return 0;
}
int SlotTable_0040a6f0::Find_0040a5d0(ByValueString name) {
 if (name.Header()->refs > 1) {
  LaneStringHeader *old = name.Header();
  name.ReleaseInline();
  if (name.Allocate_00402120(old->length)) memcpy(name.data, old + 1, old->length + 1);
 }
 CharLowerA(name.data);
 for (int i = 0; i < count; i++)
  if (lstrcmpA(name.data, (char *)&items[i] + 4) == 0) return i;
 return -1;
}

int SlotTable_0040a6f0::ActivateFree_0040a720() {
 int found = -1;
 int last = count - 1;
 for (int i = 1; i < last; i++) {
  if (!items[i].used) { found = i; continue; }
  if (items[i].level < 1000 && !items[i].busy) { found = i; break; }
 }
 if (found != -1) items[found].Activate(0);
 return found;
}

// ---- AVI plane (vtable 0x4cd540) ----
struct GameTimer { unsigned Now_00424a20(); };
extern GameTimer g_005011c0;

class AviPlane_0040b320 : public EngineObject {
public:
 unsigned lastTime;              // 0x14
 int pad18;
 Vec3Z corner[4];                // 0x1c..0x48
 int visible;                    // 0x4c
 struct StreamInfo { char head[0x34]; int left, top, right, bottom; char tail[0x8c - 0x44]; } info;  // 0x50
 void *stream;                   // 0xdc  PAVISTREAM
 void *frames;                   // 0xe0  PGETFRAME
 struct DibHeader { unsigned long size; long width, height; unsigned short planes, bitCount;
  unsigned long compression; char rest[0x28 - 0x14]; } bmi;                                       // 0xe4
 long length;                    // 0x10c
 int width, height;              // 0x110, 0x114
 int pad118;
 unsigned msPerFrame;            // 0x11c
 char pad120[0x140 - 0x120];
 bool loop;                      // 0x140
 char pad141[0x148 - 0x141];
 void *drawDib;                  // 0x148
 void *bitmap;                   // 0x14c
 void *dc;                       // 0x150
 void *bits;                     // 0x154
 unsigned elapsed;               // 0x158
 unsigned frame;                 // 0x15c
 bool finished;                  // 0x160
 void Open_0040bb20(const char *file);
 AviPlane_0040b320();
 AviPlane_0040b320(int ownerObject);
 virtual ~AviPlane_0040b320();   // defined once, in engine40/avi_plane.cpp (calls Free 0x40bed0)
#ifdef TITBIT_SOURCE_LINK
 virtual int GetType();
 virtual ObservedString Export();
 virtual void Update(int);
#endif
 void SwapRedBlue_0040bc60(unsigned char *pixels);
 void Close_0040bde0();
 void Tick_0040bef0();
};

AviPlane_0040b320::AviPlane_0040b320() {
 bits = 0; frame = 0; finished = false; lastTime = 0; elapsed = 0;
 stream = frames = bitmap = dc = drawDib = 0;
 pad18 = 0; width = height = length = 0; msPerFrame = 0;
 loop = true; visible = 1;
}
AviPlane_0040b320::AviPlane_0040b320(int ownerObject) {
 owner = ownerObject;
 bits = 0; frame = 0; finished = false; lastTime = 0; elapsed = 0;
 stream = frames = bitmap = dc = drawDib = 0;
 pad18 = 0; width = height = length = 0; msPerFrame = 0;
 loop = true; visible = 1;
}
void AviPlane_0040b320::SwapRedBlue_0040bc60(unsigned char *pixels) {
 int count = height * width;
 do {
  unsigned char t = pixels[2]; pixels[2] = pixels[0]; pixels[0] = t;
  pixels += 4;
 } while (--count);
}
extern "C" {
 __declspec(dllimport) void __stdcall AVIFileInit(void);
 __declspec(dllimport) long __stdcall AVIStreamOpenFromFileA(void **, const char *, unsigned long, long, unsigned, void *);
 __declspec(dllimport) long __stdcall AVIStreamInfoA(void *, void *, long);
 __declspec(dllimport) long __stdcall AVIStreamLength(void *);
 __declspec(dllimport) long __stdcall AVIStreamSampleToTime(void *, long);
 __declspec(dllimport) void *__stdcall AVIStreamGetFrameOpen(void *, void *);
 __declspec(dllimport) int __stdcall MessageBoxA(void *, const char *, const char *, unsigned);
 __declspec(dllimport) void *__stdcall CreateDIBSection(void *, const void *, unsigned, void **, void *, unsigned long);
 __declspec(dllimport) void *__stdcall SelectObject(void *, void *);
 __declspec(dllimport) int __stdcall DeleteDC(void *);
}
#ifdef TITBIT_COMPAT
#include "../../compat/compat.h"   /* VfW frame decoding without installed codecs (src/compat/README.md) */
#endif
void AviPlane_0040b320::Open_0040bb20(const char *file) {
 AVIFileInit();
 if (AVIStreamOpenFromFileA(&stream, file, 0x73646976, 0, 0, 0) != 0) {
  MessageBoxA(0, "Failed To Open The AVI Stream", "Error", 0x30);
  return;
 }
 if (AVIStreamInfoA(stream, &info, sizeof(info)) != 0) return;
 width = info.right - info.left;
 height = info.bottom - info.top;
 length = AVIStreamLength(stream);
 if (length <= 0 || width <= 0 || height <= 0) return;
 long total = AVIStreamSampleToTime(stream, length);
 bmi.width = width;
 bmi.height = height;
 bmi.size = 0x28;
 bmi.planes = 1;
 bmi.bitCount = 32;
 bmi.compression = 0;
 msPerFrame = total / length;
 if (!msPerFrame) msPerFrame = 1;
 bitmap = CreateDIBSection(dc, &bmi, 0, &bits, 0, 0);
 SelectObject(dc, bitmap);
 frames = AVIStreamGetFrameOpen(stream, 0);
 if (frames == 0)
  MessageBoxA(0, "Failed To Open The AVI Frame", "Error", 0x30);
}

void AviPlane_0040b320::Close_0040bde0() {
 DeleteObject(bitmap);
 DrawDibClose(drawDib);
 AVIStreamGetFrameClose(frames);
 AVIStreamRelease(stream);
 DeleteDC(dc);
 stream = frames = bitmap = dc = drawDib = bits = 0;
 AVIFileExit();
}
void AviPlane_0040b320::Tick_0040bef0() {
 unsigned now = g_005011c0.Now_00424a20();
 unsigned delta = now - lastTime;
 if (lastTime == 0) delta = 1;
 lastTime = now;
 elapsed += delta;
 frame = elapsed / msPerFrame;
}

// Script instance holder (vtable 0x4cd61c), the 0x4cd620 scene object and the
// skeleton object (vtable 0x4cd63c).
#include "e41_engine.h"
#include "lane_xml.h"
#include <math.h>
extern "C" {
__declspec(dllimport) void __stdcall glPushMatrix(void);
__declspec(dllimport) void __stdcall glPopMatrix(void);
__declspec(dllimport) void __stdcall glLoadMatrixf(const float *);
__declspec(dllimport) void __stdcall glGetFloatv(unsigned, float *);
}
extern "C" {
void *__cdecl memset(void *, int, unsigned);
void __cdecl free(void *);
int __cdecl rand(void);
__declspec(dllimport) int __stdcall lstrcmpA(const char *, const char *);
void __cdecl scFree_Instance(void *instance);   // SeeR
void *__cdecl scCompile_Text(char *text);
void *__cdecl scCreate_Instance(void *script, char *vars, ...);
int __cdecl scGet_Symbol(void *instance, char *name);
extern int scErrorNo;
extern char scErrorMsg[1024];
extern char scErrorLine[1024];
}
#include "e41_string.h"
void __cdecl PickingTrace(const char *, ...);               // engine log, 0x403650
class VfsFile {  // 0x4203d0 (was VfsFile_004203d0)
public:
 ObservedString name;
 unsigned position;
 void *handle;
 unsigned size;
 int source, kind;
 VfsFile();
 ~VfsFile();
 void Open_004206b0(const char *path);
 unsigned Read_004209b0(void *buffer, unsigned count);
 void Close_00420a60();
 unsigned Size_00413ca0();
};
#pragma intrinsic(memset)

struct Mat4I {
 float m[16];
 Mat4I() {
  m[0] = m[5] = m[10] = m[15] = 1.0f;
  m[1] = m[2] = m[3] = m[4] = m[6] = m[7] = m[8] = m[9] = m[11] = m[12] = m[13] = m[14] = 0;
 }
};

// Compiled SeeR program plus its instance.
class ScriptHolder { // original 0x41a770
public:
 void *program;                       // +0x04 (malloc'd)
 void *instance;                      // +0x08
 int handlers[13];                    // +0x0c, -1 = none
 ScriptHolder();
 virtual ~ScriptHolder();
 bool Compile_0041a7f0(ObservedString file);
};

ScriptHolder::ScriptHolder() {
 memset(handlers, 0xff, sizeof(handlers));
 program = 0;
 instance = 0;
}

ScriptHolder::~ScriptHolder() {
 if (instance) scFree_Instance(instance);
 if (program) free(program);
}

// Narrow repairs for inconsistent identifiers in the shipped script data.
// They are applied to the temporary compiler input, never to QUEST.ezd.
static void RepairScriptToken(char *&text, unsigned &size, const char *before, const char *after) {
 unsigned oldSize = 0, newSize = 0;
 while (before[oldSize]) ++oldSize;
 while (after[newSize]) ++newSize;
 for (unsigned offset = 0; offset + oldSize <= size; ++offset) {
  unsigned match = 0;
  while (match < oldSize && text[offset+match] == before[match]) ++match;
  if (match != oldSize) continue;
  unsigned total = size - oldSize + newSize;
  char *fixed = (char *)operator new(total+1);
  for (unsigned i = 0; i < offset; ++i) fixed[i] = text[i];
  for (unsigned i = 0; i < newSize; ++i) fixed[offset+i] = after[i];
  for (unsigned i = offset+oldSize; i <= size; ++i) fixed[i-oldSize+newSize] = text[i];
  operator delete(text); text = fixed; size = total;
  return;
 }
}

// Particle (0x48 bytes): ctor 0x406760, empty destructor shared at 0x4051b0.
// Load and compile a SeeR script file, then resolve the event handlers.
bool ScriptHolder::Compile_0041a7f0(ObservedString file) {
 if (lstrcmpA(file, "") == 0) return false;
 VfsFile in;
 in.Open_004206b0(file);
 unsigned size = in.Size_00413ca0();
 if (size == 0) return false;
 char *text = (char *)operator new(size + 1);
 memset(text, 0, size + 1);
 in.Read_004209b0(text, size);
 in.Close_00420a60();
 text[size] = 0;
 // The pickup's click handler and the save schema use item_porno_disk.
 if (lstrcmpA(file, "pornodisk.scv") == 0)
  RepairScriptToken(text, size, "queststate.porno_disk", "queststate.item_porno_disk");
 // loaddlg.scv restores lab03 from location 40; 31 denotes the hippie camp.
 if (lstrcmpA(file, "anton_lab3.scv") == 0)
  RepairScriptToken(text, size, "queststate.activelocation = 31;", "queststate.activelocation = 40;");
 if (!text) {
  PickingTrace("Can't open script (*.scv) file.");
  return false;
 }
 program = scCompile_Text(text);
 operator delete(text);
 if (scErrorNo == 0 && program) {
  instance = scCreate_Instance(program, "");
  if (!instance) return false;
  handlers[3] = scGet_Symbol(instance, "ON_CREATE");
  handlers[4] = scGet_Symbol(instance, "ON_DESTROY");
  handlers[1] = scGet_Symbol(instance, "ON_COLLISION");
  handlers[5] = scGet_Symbol(instance, "ON_TIME");
  handlers[2] = scGet_Symbol(instance, "ON_MOUSEOVER");
  handlers[8] = scGet_Symbol(instance, "ON_LBUTTONDOWN");
  handlers[9] = scGet_Symbol(instance, "ON_LBUTTONUP");
  handlers[10] = scGet_Symbol(instance, "ON_SETFOCUS");
  handlers[11] = scGet_Symbol(instance, "ON_KILLFOCUS");
  handlers[12] = scGet_Symbol(instance, "ON_NOTIFY");
  return true;
 }
 ObservedString message;
 message.Format("%s\n> %s\n", scErrorMsg, scErrorLine);
 PickingTrace(message);
 return false;
}

struct Elem48 {
 int head[2];
 float color[4];                      // +0x08 (ParticleState layout)
 float dcolor[4];                     // +0x18
 float pos[3];                        // +0x28
 float vel[3];                        // +0x34
 float size, dsize;                   // +0x40
 Elem48();
 ~Elem48();
};

struct TextureRecord { char name[0x2c]; char ext[0x10]; };
struct TextureCache { void Release_0042c570(int id); TextureRecord *Get_0042c730(int id); int Load_0042c2b0(ObservedString name, int flags); }; // original global 0x5ee6f0  // 0x42c080 (was TextureCache_0042c080)
extern TextureCache g_005ee6f0;

// Particle start state and per-particle variation ranges.
struct ParticleState {
 float r, g, b, a, dr, dg, db, da;
 float x, y, z, dx, dy, dz;
 float size, dsize;
};

// Particle emitter (vtable 0x4cd620).
class SceneObject_0041b380 : public EngineObject {
public:
 int count;                           // +0x14 particle_count
 int field18, field1c;
 int texture;                         // +0x20
 float spawn_carry;                   // +0x24 fractional particles carried to the next frame
 float range;                         // +0x28 particle_per_second
 Elem48 *elements;                    // +0x2c
 ParticleState initial;               // +0x30
 float field70[3];                    // +0x70 gravity
 int emitter_type;                    // +0x7c
 int field80, field84;                // +0x80 lifetime
 ParticleState variations;            // +0x88
 Mat4I matrix;                        // +0xc8
 SceneObject_0041b380(EngineObject *owner);
 virtual ~SceneObject_0041b380();
 virtual int GetType();                // 0x41d9c0
 virtual ObservedString Export();
 virtual void Update(int time);        // 0x41b930: queue live particles as sprites
 virtual void Render(int time);        // 0x41bb20: capture modelview, advance and respawn
 void Step_0041b890(Elem48 *p, unsigned dt);
 void SetCount_0041bcc0(int n);
 void Spawn_0041b4c0(Elem48 *p);
 void Load_0041c8c0(XmlNode_v *node);
 void ReadState_0041cfe0(ParticleState *s, XmlNode_v *node);
 ObservedString WriteState_0041c260(const ParticleState *s, ObservedString name);
};

SceneObject_0041b380::SceneObject_0041b380(EngineObject *owner_) {
 owner = owner_;
 memset(&initial, 0, sizeof(initial));
 memset(&variations, 0, sizeof(variations));
 spawn_carry = 0;
 field80 = 0;
 field84 = 0;
 range = 100.0f;
 field18 = 0;
 count = 0;
 elements = 0;
 texture = 0;
}

SceneObject_0041b380::~SceneObject_0041b380() {
 delete[] elements;
 g_005ee6f0.Release_0042c570(texture);
}

struct BoneVec { float x, y, z; BoneVec &operator=(const BoneVec &o); };         // 0x406f00
struct BoneMat { float m[16]; BoneMat &operator=(const BoneMat &o); };        // 0x40cba0

struct Bone_0040c6d0 {                // 0xd8 bytes, see lanes/claude/engine_40c.cpp
 int index;                           // +0x00
 float position[3];                   // +0x04
 float rotation[4];                   // +0x10
 BoneVec scale;                       // +0x20
 BoneVec center;                      // +0x2c
 BoneVec extents, v44;                // +0x38
 int link;                            // +0x50
 BoneMat local;                       // +0x54
 BoneMat world;                       // +0x94
 int parent;                          // +0xd4
 Bone_0040c6d0();
 ~Bone_0040c6d0();
 Bone_0040c6d0 &operator=(const Bone_0040c6d0 &o) {
  index = o.index;
  position[0] = o.position[0]; position[1] = o.position[1]; position[2] = o.position[2];
  rotation[0] = o.rotation[0]; rotation[1] = o.rotation[1]; rotation[2] = o.rotation[2]; rotation[3] = o.rotation[3];
  scale = o.scale; center = o.center; extents = o.extents; v44 = o.v44;
  link = o.link;
  local = o.local; world = o.world;
  parent = o.parent;
  return *this;
 }
 void UpdateMatrix_0040c7e0(int recompute);
 ObservedString Export_0040ced0() const;
 void Load_0040d600(XmlNode_v *node);
};

struct SplineAnimation_00406a40 { char body[0x1c]; SplineAnimation_00406a40(EngineObject *owner); void Load_00407280(XmlNode_v *node); };
struct ManualControl_00415e40 { char body[0x10]; ManualControl_00415e40(EngineObject *owner); void Load_0044e440(XmlNode_v *node); };
struct SkeletonAnimation_004269f0 { char body[0x34]; SkeletonAnimation_004269f0(EngineObject *owner); void Load_00427130(XmlNode_v *node); };

class Skeleton : public EngineObject { // original 0x41da00
public:
 char body14[0x34 - 0x14];
 int bone_count;                      // +0x34
 Bone_0040c6d0 *bones;                // +0x38
 float depth;                         // +0x3c
 int visible;                         // +0x40
 Skeleton();
 virtual ~Skeleton();
#ifdef TITBIT_SOURCE_LINK
 virtual int GetType();
 virtual void Update(int);
#endif
 virtual ObservedString Export();
 virtual void Render(int pass);
 void AddChild_0041e520(EngineObject *child);
 void Load_0041db90(XmlNode_v *node);
};

void SceneObject_0041b380::Step_0041b890(Elem48 *p, unsigned dt) {
 float t = (float)dt;
 p->color[0] = t * p->dcolor[0] + p->color[0];
 p->color[1] = t * p->dcolor[1] + p->color[1];
 p->color[2] = t * p->dcolor[2] + p->color[2];
 p->color[3] = t * p->dcolor[3] + p->color[3];
 p->pos[0] = t * p->vel[0] + p->pos[0];
 p->pos[1] = t * p->vel[1] + p->pos[1];
 p->pos[2] = t * p->vel[2] + p->pos[2];
 p->vel[0] = t * field70[0] + p->vel[0];
 p->vel[1] = t * field70[1] + p->vel[1];
 p->vel[2] = t * field70[2] + p->vel[2];
 p->size = t * p->dsize + p->size;
}

static inline float RandomUnit() { return (float)(rand() - 0x3fff) * 6.1038882e-05f; }
#define RANDOM_SPREAD(range) (RandomUnit() * (range))

// New particle: start state plus random variation; unless emitter_type has
// bit 2 (local) position and velocity go through the parent bone's matrix.
void SceneObject_0041b380::Spawn_0041b4c0(Elem48 *p) {
 *(ParticleState *)p->color = initial;
 float vz;
 if (emitter_type & 2) {
  p->pos[0] = RANDOM_SPREAD(variations.x) + initial.x;
  p->pos[1] = RANDOM_SPREAD(variations.y) + initial.y;
  p->pos[2] = RANDOM_SPREAD(variations.z) + initial.z;
  p->vel[0] = RANDOM_SPREAD(variations.dx) + initial.dx;
  p->vel[1] = RANDOM_SPREAD(variations.dy) + initial.dy;
  vz = RANDOM_SPREAD(variations.dz) + initial.dz;
 } else {
  float x = RANDOM_SPREAD(variations.x) + initial.x;
  float y = RANDOM_SPREAD(variations.y) + initial.y;
  float z = RANDOM_SPREAD(variations.z) + initial.z;
  const float *m = (const float *)(*(char **)((char *)owner + 0x38) + 0x94 + field8 * 0xd8);
  p->pos[0] = x * m[0] + z * m[8] + y * m[4] + m[12];
  p->pos[1] = z * m[9] + y * m[5] + x * m[1] + m[13];
  p->pos[2] = x * m[2] + z * m[10] + y * m[6] + m[14];
  x = RANDOM_SPREAD(variations.dx) + initial.dx;
  y = RANDOM_SPREAD(variations.dy) + initial.dy;
  z = RANDOM_SPREAD(variations.dz) + initial.dz;
  p->vel[0] = x * m[0] + z * m[8] + y * m[4];
  p->vel[1] = z * m[9] + y * m[5] + x * m[1];
  vz = x * m[2] + z * m[10] + y * m[6];
 }
 p->vel[2] = vz;
 p->color[0] = RANDOM_SPREAD(variations.r) + initial.r;
 p->color[1] = RANDOM_SPREAD(variations.g) + initial.g;
 p->color[2] = RANDOM_SPREAD(variations.b) + initial.b;
 p->color[3] = RANDOM_SPREAD(variations.a) + initial.a;
 p->dcolor[0] = RANDOM_SPREAD(variations.dr) + initial.dr;
 p->dcolor[1] = RANDOM_SPREAD(variations.dg) + initial.dg;
 p->dcolor[2] = RANDOM_SPREAD(variations.db) + initial.db;
 p->head[0] = field1c;
 p->head[1] = field80 - (int)((float)(rand() - 0x3fff) * -6.1038882e-05f) * field84 + field1c;
}

void SceneObject_0041b380::SetCount_0041bcc0(int n) {
 if (n == count) return;
 delete[] elements;
 elements = new Elem48[n];
 memset(elements, 0, n * sizeof(Elem48));
 count = n;
}

Skeleton::Skeleton() {
 bone_count = 0;
 bones = 0;
 visible = 1;
}

Skeleton::~Skeleton() {
 bone_count = 0;
 delete[] bones;
}

struct SpriteQueue_005026d0 { void AddSprite_0041ec80(const float *position, const float *color, const unsigned *texture, const float *size, bool additive); };
extern SpriteQueue_005026d0 g_005026d0;   // transparent depth list (renderer at 0x5026d0)
struct ColumnVec { float x, y, z; };

int SceneObject_0041b380::GetType() {
 return 2;
}

void SceneObject_0041b380::Update(int time) {
 ColumnVec axis;
 axis.x = axis.y = axis.z = 0;
 const float *bone = ((Skeleton *)owner)->bones[field8].local.m;
 axis = *(const ColumnVec *)bone;
 float scale = (float)sqrt(axis.z * axis.z + axis.y * axis.y + axis.x * axis.x);
 for (int i = 0; i < count; i++) {
  Elem48 *e = &elements[i];
  if (!(e->color[3] > 0.0f)) continue;
  float size = scale * e->size;
  float pos[3];
  if (emitter_type & 2) {
   pos[0] = bone[8] * e->pos[2] + bone[4] * e->pos[1] + bone[0] * e->pos[0] + bone[12];
   pos[1] = bone[9] * e->pos[2] + bone[5] * e->pos[1] + bone[1] * e->pos[0] + bone[13];
   pos[2] = bone[10] * e->pos[2] + bone[6] * e->pos[1] + bone[2] * e->pos[0] + bone[14];
  } else {
   pos[0] = matrix.m[8] * e->pos[2] + matrix.m[4] * e->pos[1] + matrix.m[0] * e->pos[0] + matrix.m[12];
   pos[1] = matrix.m[9] * e->pos[2] + matrix.m[5] * e->pos[1] + matrix.m[1] * e->pos[0] + matrix.m[13];
   pos[2] = matrix.m[10] * e->pos[2] + matrix.m[6] * e->pos[1] + matrix.m[2] * e->pos[0] + matrix.m[14];
  }
  float color[4];
  color[0] = e->color[0]; color[1] = e->color[1]; color[2] = e->color[2]; color[3] = e->color[3];
  g_005026d0.AddSprite_0041ec80(pos, color, (const unsigned *)&texture, &size, (emitter_type & 1) != 0);
 }
 if (next) next->Update(time);
}

void SceneObject_0041b380::Render(int time) {
 if (time) {
  glGetFloatv(0xba6, matrix.m);                      // GL_MODELVIEW_MATRIX
  field1c = time;
  unsigned dt = (unsigned)time - (unsigned)field18;
  if (dt >= (unsigned)field80) dt = field80;
  int spawn;
  if (field18) {
   float total = range * (int)dt * 0.001f + spawn_carry;
   spawn = (int)total;
   spawn_carry = total - (float)spawn;
  } else spawn = (int)range;
  int spawn_total = spawn;
  for (int i = 0; i < count; i++) {
   Step_0041b890(&elements[i], dt);
   Elem48 *e = &elements[i];
   if ((unsigned)field1c > (unsigned)e->head[1]) {
    if (spawn) {
     Spawn_0041b4c0(e);
     float late = (float)(unsigned)(spawn * dt / spawn_total);
     Step_0041b890(&elements[i], (int)late);
     unsigned jitter = (int)((float)(rand() - 0x3fff) * 6.1038882e-05f) * field84;
     e = &elements[i];
     e->head[1] = (int)((float)jitter + ((float)(unsigned)(field1c + field80) - late));
     spawn--;
    } else {
     e->color[3] = 0;
     e->dcolor[3] = 0;
    }
   }
  }
  field18 = field1c;
 }
 if (next) next->Render(time);
}


#ifdef TITBIT_SOURCE_LINK
// The original object tables 0x4cd570 and 0x4cd63c use these folded bodies.
// Define the actual object methods; do not substitute an Audiere method.
int Skeleton::GetType() { return 0; }                 // native 0x48b410: XOR EAX,EAX; RET
void Skeleton::Update(int time) {                     // native 0x406230
 if (next) next->Update(time);
}
#endif

void Skeleton::AddChild_0041e520(EngineObject *child) {
 child->owner = this;
 AppendNext_00413820(child);
}

struct ExtraChain { void Append_0040b270(void *item); };

void EngineObject::AttachExtra_0041e530(ObjectExtra *item) {
 ((EngineObject *)item)->owner = this;
 if (extra) { ((ExtraChain *)extra)->Append_0040b270(item); return; }
 extra = item;
}

void Skeleton::Render(int pass) {
 if (owner) {
  glPushMatrix();
  glLoadMatrixf(((Skeleton *)owner)->bones[field8].local.m);
 }
 for (int i = 0; i < bone_count; i++) bones[i].UpdateMatrix_0040c7e0(1);
 if (bone_count > 0) {
  Bone_0040c6d0 *b = bones;
  depth = (float)fabs(b->local.m[2] * b->center.x + b->local.m[6] * b->center.y + b->local.m[10] * b->center.z + b->local.m[14]);
 }
 visible = 0;
 if (extra) extra->Render(pass);
 if (next) next->Render(pass);
 if (owner) glPopMatrix();
}

ObservedString Skeleton::Export() {
 ObservedString xml, number;
 xml += "<position ";
 xml += "owner_bone_id=\"";
 number.Format("%i", field8);
 xml += number;
 xml += "\" ";
 xml += "bonecount=\"";
 number.Format("%i", bone_count);
 xml += number;
 xml += "\" ";
 xml += ">";
 xml += "\n\r";
 xml += "<bones>";
 xml += "\n\r";
 for (int i = 0; i < bone_count; i++) xml += bones[i].Export_0040ced0();
 xml += "</bones>";
 xml += "\n\r";
 if (extra) {
  xml += "<animations>";
  xml += "\n\r";
  xml += extra->Export();
  xml += "</animations>";
  xml += "\n\r";
 }
 xml += "</position>";
 xml += "\n\r";
 return xml;
}

#define STATE_FIELD(label, value) \
 name += label; number.Format("%.8f", (double)(value)); name += number; name += "\" ";

// "<name x=.. y=.. z=.. dx=.. dy=.. dz=.. r=.. g=.. b=.. a=.. dr=.. dg=.. db=.. da=.. size=.. dsize=.. />"
ObservedString SceneObject_0041b380::WriteState_0041c260(const ParticleState *s, ObservedString name) {
 ObservedString number;
 name = "<" + name;
 name += " ";
 STATE_FIELD("x=\"", s->x)
 STATE_FIELD("y=\"", s->y)
 STATE_FIELD("z=\"", s->z)
 STATE_FIELD("dx=\"", s->dx)
 STATE_FIELD("dy=\"", s->dy)
 STATE_FIELD("dz=\"", s->dz)
 STATE_FIELD("r=\"", s->r)
 STATE_FIELD("g=\"", s->g)
 STATE_FIELD("b=\"", s->b)
 STATE_FIELD("a=\"", s->a)
 STATE_FIELD("dr=\"", s->dr)
 STATE_FIELD("dg=\"", s->dg)
 STATE_FIELD("db=\"", s->db)
 STATE_FIELD("da=\"", s->da)
 STATE_FIELD("size=\"", s->size)
 STATE_FIELD("dsize=\"", s->dsize)
 name += "/>";
 name += "\n\r";
 return name;
}

ObservedString SceneObject_0041b380::Export() {
 ObservedString xml, number;
 xml += "<particle_emitter ";
 xml += "parent_bone_id=\"";
 number.Format("%i", field8);
 xml += number;
 xml += "\" ";
 TextureRecord *t = g_005ee6f0.Get_0042c730(texture);
 number = t->name;                    // original reuses 'number' for the texture file name
 number += ".";
 number += t->ext;
 xml += "texture=\"";
 xml += number;
 xml += "\" ";
 xml += "grav_x=\"";
 number.Format("%0.8f", (double)field70[0]);
 xml += number;
 xml += "\" ";
 xml += "grav_y=\"";
 number.Format("%0.8f", (double)field70[1]);
 xml += number;
 xml += "\" ";
 xml += "grav_z=\"";
 number.Format("%0.8f", (double)field70[2]);
 xml += number;
 xml += "\" ";
 xml += "lifetime=\"";
 number.Format("%i", field80);
 xml += number;
 xml += "\" ";
 xml += "emitter_type=\"";
 number.Format("%i", emitter_type);
 xml += number;
 xml += "\" ";
 xml += "particle_count=\"";
 number.Format("%i", count);
 xml += number;
 xml += "\" ";
 xml += "particle_per_second=\"";
 number.Format("%0.8f", (double)range);
 xml += number;
 xml += "\" ";
 xml += ">";
 xml += "\n\r";
 xml += WriteState_0041c260(&initial, "initial_state");
 xml += WriteState_0041c260(&variations, "variations");
 xml += "</particle_emitter>";
 xml += "\n\r";
 return xml;
}

#define READ_FLOAT(attr, field)  a = element->Attribute(std::string(attr));  if (a) field = (float)atof(a->Value()->c_str());

void SceneObject_0041b380::ReadState_0041cfe0(ParticleState *s, XmlNode_v *node) {
 XmlElement_v *element = node->ToElement();
 if (!element) return;
 XmlAttr_v *a;
 READ_FLOAT("x", s->x)
 READ_FLOAT("y", s->y)
 READ_FLOAT("z", s->z)
 READ_FLOAT("dx", s->dx)
 READ_FLOAT("dy", s->dy)
 READ_FLOAT("dz", s->dz)
 READ_FLOAT("r", s->r)
 READ_FLOAT("g", s->g)
 READ_FLOAT("b", s->b)
 READ_FLOAT("a", s->a)
 READ_FLOAT("dr", s->dr)
 READ_FLOAT("dg", s->dg)
 READ_FLOAT("db", s->db)
 READ_FLOAT("da", s->da)
 READ_FLOAT("size", s->size)
 READ_FLOAT("dsize", s->dsize)
 if (--element->refs <= 0) element->Destroy(1);
}

void SceneObject_0041b380::Load_0041c8c0(XmlNode_v *node) {
 int particles = 0;
 XmlElement_v *element = node->ToElement();
 if (element) {
  XmlAttr_v *a = element->Attribute(std::string("parent_bone_id"));
  if (a) field8 = atoi(a->Value()->c_str());
  a = element->Attribute(std::string("texture"));
  if (a) texture = g_005ee6f0.Load_0042c2b0(ObservedString(a->Value()->c_str()), 0);
  READ_FLOAT("grav_x", field70[0])
  READ_FLOAT("grav_y", field70[1])
  READ_FLOAT("grav_z", field70[2])
  a = element->Attribute(std::string("lifetime"));
  if (a) field80 = atoi(a->Value()->c_str());
  a = element->Attribute(std::string("emitter_type"));
  if (a) emitter_type = atoi(a->Value()->c_str());
  a = element->Attribute(std::string("particle_count"));
  if (a) particles = atoi(a->Value()->c_str());
  READ_FLOAT("particle_per_second", range)
  if (--element->refs <= 0) element->Destroy(1);
 }
 for (XmlNode_v *child = node->FirstChild(); child; child = child->NextSibling()) {
  if (*child->Name() == "initial_state") ReadState_0041cfe0(&initial, child);
  else if (*child->Name() == "variations") ReadState_0041cfe0(&variations, child);
 }
 SetCount_0041bcc0(particles);
}

void Skeleton::Load_0041db90(XmlNode_v *node) {
 PickingTrace("Start reading bones list");
 XmlElement_v *element = node->ToElement();
 if (element) {
  XmlAttr_v *a = element->Attribute(std::string("owner_bone_id"));
  if (a) field8 = atoi(a->Value()->c_str());
  a = element->Attribute(std::string("bonecount"));
  if (a) bone_count = atoi(a->Value()->c_str());
 }
 if (bone_count > 0) {
  bones = new Bone_0040c6d0[bone_count];
  for (XmlNode_v *child = node->FirstChild(); child; child = child->NextSibling()) {
   if (*child->Name() == "bones") {
    for (XmlNode_v *b = child->FirstChild(); b; b = b->NextSibling()) {
     if (*b->Name() == "bone") {
      Bone_0040c6d0 bone;
      bone.Load_0040d600(b);
      if (bone.index >= 0 && bone.index < bone_count) bones[bone.index] = bone;
     }
    }
   }
   if (*child->Name() == "animations") {
    for (XmlNode_v *a = child->FirstChild(); a; a = a->NextSibling()) {
     ObjectExtra *item;
     if (*a->Name() == "splineanimation") {
      SplineAnimation_00406a40 *s = new SplineAnimation_00406a40(this);
      s->Load_00407280(a);
      item = (ObjectExtra *)s;
     } else if (*a->Name() == "manual_control") {
      ManualControl_00415e40 *m = new ManualControl_00415e40(this);
      m->Load_0044e440(a);
      item = (ObjectExtra *)m;
     } else if (*a->Name() == "skeleton_animation") {
      SkeletonAnimation_004269f0 *k = new SkeletonAnimation_004269f0(this);
      k->Load_00427130(a);
      item = (ObjectExtra *)k;
     } else continue;
     if (extra == 0) extra = item;
     else ((ExtraChain *)extra)->Append_0040b270(item);
    }
   }
  }
  // original: released only inside the bone_count block and without a null check
  if (--element->refs <= 0) element->Destroy(1);
 }
 PickingTrace("Reading bones done");
}

// Native 0x406760, shared empty record constructor.
Elem48::Elem48(){}

#define OBSERVED_STRING_WTL_BUFFER  // GetBuffer/ReleaseBuffer expanded inline (WTL)
#define OBSERVED_STRING_INLINE_COPY  // CString copy ctor expanded inline (WTL)
#define OBSERVED_STRING_WTL_LOADSTRING  // WTL CString layout (see engine_string.h)
#define OBSERVED_STRING_RELEASE_EXTERNAL  // CString::Release out of line (0x402180)
// Scene XML loader: Scene::LoadScene (0x422510, tail 0x42280c) and ReadObjects (0x422d40).
#include "lane_xml.h"
#include "e42_scene.h"
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
#include "../../native/widescreen_hooks.h"
#endif
extern "C" char *__cdecl strcpy(char *, const char *);
#pragma intrinsic(strcpy)

void __cdecl Log_00403650(const char *text);
ObservedString __stdcall Concat_0040e070(const char *a, const ObservedString &b);
void __cdecl FormatArchiveString(ObservedString *, const char *, ...);

// DOM node implementation interface (Arabica-style refcounted impl).
struct DomNode42 {
 virtual void s0();
 virtual void Release(int);                          // +0x04
 virtual void s2(); virtual void s3(); virtual void s4();
 virtual const std::string *Name();                  // +0x14
 virtual void s6(); virtual void s7(); virtual void s8(); virtual void s9(); virtual void s10();
 virtual DomNode42 *FirstChild();                    // +0x2c
 virtual void s12(); virtual void s13();
 virtual DomNode42 *NextSibling();                   // +0x38
 virtual XmlElement_v *ToElement();                  // +0x3c
 int refs;
};

class DomParser_0042f2c0 {
 void *vtables[3];
 unsigned char body[0x68 - 12];
public:
 DomParser_0042f2c0();
 ~DomParser_0042f2c0();
 void SetFeature_0042f610(const std::string &name, bool value);
 DomNode42 *Parse_00431620(const char *text);
};
// The original catches CenterPoint's CSL::XML::CXMLException& (catch type .?AVCXMLException@XML@CSL@@);
// the catch only matches when the class has exactly this name. GetMsg = 0x447bd0.
namespace CSL { namespace XML {
class CXMLException { public: std::string GetMsg() const; };
} }

class VfsFile {  // 0x4203d0 (was VfsFile_004203d0)
public:
 ObservedString name;
 unsigned position;
 void *handle;
 unsigned size;
 int source, kind;
 VfsFile();
 ~VfsFile();
 int Locate_00420420(const char *path);
 void Open_004206b0(const char *path);
 unsigned Read_004209b0(char *buffer, unsigned count);
 void Close_00420a60();
 unsigned GetSize_00413ca0();
};

// NONMATCHING: faithful translation
void Scene::LoadScene_00422510(ObservedString path) {
 Log_00403650(Concat_0040e070("Start loading ", path));
 DomParser_0042f2c0 parser;
 parser.SetFeature_0042f610(std::string("namespaces"), false);
 parser.SetFeature_0042f610(std::string("white-space-in-element-content"), true);
 ObservedString text;
 ObservedString unused;
 VfsFile file;
 if (!file.Locate_00420420(path)) return;
 file.Open_004206b0(path);
 char *buffer = text.GetBuffer(file.GetSize_00413ca0() + 1);
 buffer[file.GetSize_00413ca0()] = 0;
 file.Read_004209b0(buffer, file.GetSize_00413ca0());
 file.Close_00420a60();
 text.ReleaseBuffer(-1);
 Log_00403650(text);
 DomNode42 *document = 0;   // original: still NULL after a caught parse error (original bug: crashes below)
 try {
  document = parser.Parse_00431620(text);
 } catch (CSL::XML::CXMLException &error) {
  Log_00403650(error.GetMsg().c_str());
 }
 Log_00403650("Parsing done");
 for (DomNode42 *node = document->FirstChild(); node; node = node->NextSibling()) {
  std::string name(*node->Name());
  if (name == "scene") {
   ObservedString message;
   FormatArchiveString(&message, "&scene = %i", this);
   Log_00403650(message);
   DomNode42 *content = node->FirstChild();
   Log_00403650("Reading resource list");
   ReadResources_00422a90(content);
   Log_00403650("Reading static objects");
   ReadObjects_00422d40(content, 0);
   Log_00403650("Reading dynamic objects");
   ReadObjects_00422d40(content, 1);
   Log_00403650("Reading interface objects");
   ReadObjects_00422d40(content, 2);
   ReadCamera_00423f80(content);
   ReadSettings_00425cc0(content);
   ReadAmbient_00424230(content);
   FormatArchiveString(&message, "Dyn obj count - %i", objects.size);
   Log_00403650(message);
   Log_00403650("Reading lightning");
   ReadLighting_00423e40(content);
   Log_00403650("Building octree");
   BuildOctree_00423a80(true);
   Log_00403650("DONE");
  }
 }
 if (--document->refs < 1) document->Release(1);
 Log_00403650("Scene loaded");
#if defined(TITBIT_COMPAT) || defined(TITBIT_WIDESCREEN_HOOKS)
 CompatSceneChanged(path);
#endif
}

// Scene object components, constructed with their owner object.
class GameObject_0040e630;
class Component42 { public: virtual ~Component42(); };
#define COMPONENT(Class, Size, LoadDecl) \
class Class : public Component42 { unsigned char body[Size - 4]; public: Class(GameObject_0040e630 *owner); LoadDecl; };
COMPONENT(ParticleEmitter_0041b380, 0x108, void Load_0041c8c0(DomNode42 *node))
COMPONENT(Lod, 0xe8, bool Load_004153b0(DomNode42 *node); void Detach_00413850())
COMPONENT(SrbLod, 0x128, bool Load_004153b0(DomNode42 *node))
COMPONENT(LightSource_00412140, 0x70, void Load_004121a0(DomNode42 *node))
COMPONENT(StupidOccluder_00405e90, 0xa4, void Load_00405fa0(DomNode42 *node))
COMPONENT(BoxOccluder_00405240, 0x2c4, void Load_004057f0(DomNode42 *node))
COMPONENT(TextWindow_00408b80, 0x38, void Load_00408d60(DomNode42 *node))
COMPONENT(InterfacePlane_0040f420, 0x58, void Load_0040f640(DomNode42 *node))
COMPONENT(AviPlane_0040b3b0, 0x164, void Load_0040b640(DomNode42 *node))

class GameObject_0040e630 : public SceneObject {
 unsigned char body[0x88 - sizeof(SceneObject)];
public:
 bool selectable;
 GameObject_0040e630();
 void ReadPosition_0040e710(DomNode42 *node);
 void AddComponent_0041e520(Component42 *component);
 bool BindScript_0040e720(ObservedString source);
};

struct ObjectList42 : ScenePtrArray<SceneObject *> {
 void SetSize_00411f60(int size, int grow);
 void Add_00411d70(SceneObject *window);
};

// NONMATCHING: faithful translation
void Scene::ReadObjects_00422d40(DomNode42 *node, int kind) {
 ObservedString unused;
 std::string type;
 std::string flag;
 std::string section;
 section = "static_objects";
 if (kind == 1) section = "dynamic_objects";
 else if (kind == 2) section = "interface_objects";
 for (; node; node = node->NextSibling()) {
  if (*node->Name() != section) continue;
  for (DomNode42 *item = node->FirstChild(); item; item = item->NextSibling()) {
   if (*item->Name() != "object") continue;
   DomNode42 *child = item->FirstChild();
   XmlElement_v *element = item->ToElement();
   GameObject_0040e630 *object = 0;
   while (child) {
    std::string childName(*child->Name());
    if (childName == "position") {
     object = new GameObject_0040e630;
     object->ReadPosition_0040e710(child);
     break;
    }
    child = child->NextSibling();
   }
   if (!child) continue;
   {
    std::string name("");
    std::string script("");
    if (element) {
     XmlAttr_v *attribute = element->Attribute(std::string("name"));
     if (attribute) {
      name = *attribute->Value();
      if (name == "cursor") pointNode = object;
     }
     attribute = element->Attribute(std::string("scriptname"));
     if (attribute) script = *attribute->Value();
     attribute = element->Attribute(std::string("selectable"));
     if (attribute) {
      flag = *attribute->Value();
      if (flag == "1") object->selectable = true;
     }
     if (--element->refs <= 0) element->Destroy(1);
    }
    strcpy(object->name, name.c_str());
    object->BindScript_0040e720(ObservedString(script.c_str()));
   }
   if (!object) continue;
   for (child = item->FirstChild(); child; child = child->NextSibling()) {
    type = *child->Name();
    if (type == "particle_emitter") {
     ParticleEmitter_0041b380 *c = new ParticleEmitter_0041b380(object);
     object->AddComponent_0041e520(c);
     c->Load_0041c8c0(child);
    } else if (type == "lod") {
     Lod *c = new Lod(object);
     object->AddComponent_0041e520(c);
     if (!c->Load_004153b0(child)) { c->Detach_00413850(); delete c; }
    } else if (type == "srb_lod") {
     SrbLod *c = new SrbLod(object);
     object->AddComponent_0041e520(c);
     c->Load_004153b0(child);
    } else if (type == "light_source") {
     LightSource_00412140 *c = new LightSource_00412140(object);
     object->AddComponent_0041e520(c);
     c->Load_004121a0(child);
    } else if (type == "stupid_occluder") {
     StupidOccluder_00405e90 *c = new StupidOccluder_00405e90(object);
     object->AddComponent_0041e520(c);
     c->Load_00405fa0(child);
    } else if (type == "box_occluder") {
     BoxOccluder_00405240 *c = new BoxOccluder_00405240(object);
     object->AddComponent_0041e520(c);
     c->Load_004057f0(child);
    } else if (type == "text_window") {
     TextWindow_00408b80 *c = new TextWindow_00408b80(object);
     object->AddComponent_0041e520(c);
     c->Load_00408d60(child);
    } else if (type == "interface_plane") {
     InterfacePlane_0040f420 *c = new InterfacePlane_0040f420(object);
     object->AddComponent_0041e520(c);
     c->Load_0040f640(child);
    } else if (type == "avi_plane") {
     AviPlane_0040b3b0 *c = new AviPlane_0040b3b0(object);
     object->AddComponent_0041e520(c);
     c->Load_0040b640(child);
    }
   }
   if (kind == 1) {
    int index = objects.size;
    ((ObjectList42 *)&objects)->SetSize_00411f60(index + 1, -1);
    objects.data[index] = object;
   } else if (kind == 0) {
    int index = statics.size;
    ((ObjectList42 *)&statics)->SetSize_00411f60(index + 1, -1);
    statics.data[index] = object;
   } else if (kind == 2) {
    ((ObjectList42 *)&windows)->Add_00411d70(object);
   }
   ObservedPickingMessage message;
   memset(&message, 0, sizeof(message));
   message.event = 3;
   message.selected = object;
   Send_00424780(&message);
  }
 }
}

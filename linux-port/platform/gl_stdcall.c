/* Win32 OpenGL calls pop their arguments on x86; ELF libGL functions do not.
 * Only these prefixed entry points cross that boundary. Never bind an engine
 * stdcall declaration directly to a Linux GL symbol. */
#include <GL/gl.h>
#include <GL/glu.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "titbit_platform.h"
#if defined(__i386__)
#define WAPI __attribute__((stdcall))
#else
#define WAPI
#endif
#ifndef __EMSCRIPTEN__
static void *gl_library;
static pthread_once_t library_once=PTHREAD_ONCE_INIT;
static void load_libraries(void) {
 gl_library=dlopen("libGL.so.1",RTLD_NOW|RTLD_LOCAL);
 if(!gl_library){fprintf(stderr,"Titbit: OpenGL runtime load failed: %s\n",dlerror());abort();}
}
static void *resolve(const char *name) {
 void *result;
 /* GLU is linked into the executable (statically with --minimal), so it is
  * taken from there: the system may have no 32-bit libGLU.so.1 at all. */
 if(!strcmp(name,"gluPerspective"))return (void *)&gluPerspective;
 if(!strcmp(name,"gluBuild2DMipmaps"))return (void *)&gluBuild2DMipmaps;
 pthread_once(&library_once,load_libraries);
 result=dlsym(gl_library,name);
 if(!result){fprintf(stderr,"Titbit: required OpenGL symbol missing: %s\n",name);abort();}
 return result;
}
#define GET_PROC(name,params) typedef void (*Fn) params; static void *cached; void *p=__atomic_load_n(&cached,__ATOMIC_ACQUIRE);if(!p){p=resolve(#name);__atomic_store_n(&cached,p,__ATOMIC_RELEASE);} Fn fn=(Fn)p
#define VOID_WRAP(name,params,args) void WAPI tb_gl_stdcall_##name params {GET_PROC(name,params);fn args;}
#define RET_WRAP(type,name,params,args) type WAPI tb_gl_stdcall_##name params {typedef type (*Fn) params;static void *cached;void *p=__atomic_load_n(&cached,__ATOMIC_ACQUIRE);if(!p){p=resolve(#name);__atomic_store_n(&cached,p,__ATOMIC_RELEASE);}return ((Fn)p) args;}
#else
#include <functional>
#include <vector>
#include <array>
#include <map>
static std::vector<std::vector<std::function<void()>>> browser_lists(1);
static unsigned browser_recording;
static void record_gl(std::function<void()> command) {
 if(browser_recording)browser_lists[browser_recording].push_back(command);else command();
}
#define VOID_WRAP(name,params,args) void tb_gl_stdcall_##name params { record_gl([=]{ name args; }); }
#define RET_WRAP(type,name,params,args) type tb_gl_stdcall_##name params { return name args; }
extern "C" {
void glGenerateMipmap(GLenum);
GLuint glGenLists(GLsizei count){if(count<=0)return 0;unsigned base=browser_lists.size();browser_lists.resize(base+count);return base;}
void glNewList(GLuint id,GLenum mode){if(mode!=GL_COMPILE||!id||id>=browser_lists.size())abort();browser_lists[id].clear();browser_recording=id;}
void glEndList(){browser_recording=0;}
void glCallList(GLuint id){if(id>=browser_lists.size())abort();for(auto &command:browser_lists[id])command();}
void glMaterialf(GLenum face,GLenum pname,GLfloat value){glMaterialfv(face,pname,&value);}
/* Engine fallback rendering uses separate texture passes when ARB multitexture
 * is not advertised; WebGL does not expose that desktop extension. */
void glActiveTextureARB(GLenum texture){glActiveTexture(texture);}
void glClientActiveTextureARB(GLenum texture){glClientActiveTexture(texture);}
void glMultiTexCoord1fARB(GLenum texture,GLfloat x){if(texture!=GL_TEXTURE0)abort();glTexCoord2f(x,0);}
void glMultiTexCoord2fARB(GLenum texture,GLfloat x,GLfloat y){if(texture!=GL_TEXTURE0)abort();glTexCoord2f(x,y);}
void glMultiTexCoord3fARB(GLenum texture,GLfloat x,GLfloat y,GLfloat z){if(z!=0)abort();glMultiTexCoord2fARB(texture,x,y);}
void glMultiTexCoord4fARB(GLenum texture,GLfloat x,GLfloat y,GLfloat z,GLfloat w){if(w!=1)abort();glMultiTexCoord3fARB(texture,x,y,z);}
GLint gluBuild2DMipmaps(GLenum target,GLint internal,GLsizei width,GLsizei height,GLenum format,GLenum type,const void *pixels){
 int w=1,h=1;while(w<width)w*=2;while(h<height)h*=2;
 std::vector<unsigned char> resized;
 if(w!=width||h!=height){
  if(type!=GL_UNSIGNED_BYTE||(format!=GL_RGB&&format!=GL_RGBA))return GL_INVALID_ENUM;
  unsigned components=format==GL_RGB?3:4;resized.resize((size_t)w*h*components);
  const unsigned char *source=(const unsigned char*)pixels;
  for(int y=0;y<h;++y)for(int x=0;x<w;++x){
   float sx=(x+.5f)*width/w-.5f,sy=(y+.5f)*height/h-.5f;
   if(sx<0)sx=0;if(sy<0)sy=0;int x0=(int)sx,y0=(int)sy,x1=x0+1<width?x0+1:x0,y1=y0+1<height?y0+1:y0;
   float fx=sx-x0,fy=sy-y0;
   for(unsigned c=0;c<components;++c){
    float top=source[((size_t)y0*width+x0)*components+c]*(1-fx)+source[((size_t)y0*width+x1)*components+c]*fx;
    float bottom=source[((size_t)y1*width+x0)*components+c]*(1-fx)+source[((size_t)y1*width+x1)*components+c]*fx;
    resized[((size_t)y*w+x)*components+c]=(unsigned char)(top*(1-fy)+bottom*fy+.5f);
   }
  }
  pixels=resized.data();
 }
 glTexImage2D(target,0,format,w,h,0,format,type,pixels);glGenerateMipmap(target);return 0;
}
}
#endif
#ifdef __EMSCRIPTEN__
extern "C" {
#endif
#ifdef __EMSCRIPTEN__
/* Setting the default sphere-map mode has no effect until texgen is enabled.
 * The browser renderer currently uses the scene's explicit texture coordinates. */
void tb_gl_stdcall_glTexGeni(GLenum a,GLenum b,GLint c){if(b!=GL_TEXTURE_GEN_MODE||c!=GL_SPHERE_MAP)abort();}
#else
VOID_WRAP(glTexGeni,(GLenum a,GLenum b,GLint c),(a,b,c))
#endif
VOID_WRAP(glMaterialf,(GLenum a,GLenum b,GLfloat c),(a,b,c))
VOID_WRAP(glCullFace,(GLenum a),(a))
VOID_WRAP(glMaterialfv,(GLenum a,GLenum b,const GLfloat *c),(a,b,c))
VOID_WRAP(glPointSize,(GLfloat a),(a))
VOID_WRAP(glClearDepth,(GLdouble a),(a))
#ifdef __EMSCRIPTEN__
static std::map<GLuint,GLuint> browser_textures;
void tb_gl_stdcall_glDeleteTextures(GLsizei count,const GLuint *ids){for(int i=0;i<count;++i){auto it=browser_textures.find(ids[i]);if(it!=browser_textures.end()){glDeleteTextures(1,&it->second);browser_textures.erase(it);}}}
#else
VOID_WRAP(glDeleteTextures,(GLsizei a,const GLuint *b),(a,b))
#endif
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glTexImage2D(GLenum a,GLint b,GLint c,GLsizei d,GLsizei e,GLint f,GLenum g,GLenum h,const void *i){glTexImage2D(a,b,g,d,e,0,g,h,i);}
#else
VOID_WRAP(glTexImage2D,(GLenum a,GLint b,GLint c,GLsizei d,GLsizei e,GLint f,GLenum g,GLenum h,const void *i),(a,b,c,d,e,f,g,h,i))
#endif
VOID_WRAP(glTexEnvi,(GLenum a,GLenum b,GLint c),(a,b,c))
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glTexParameteri(GLenum a,GLenum b,GLint c){if((b==GL_TEXTURE_WRAP_S||b==GL_TEXTURE_WRAP_T)&&c==GL_CLAMP)c=GL_CLAMP_TO_EDGE;record_gl([=]{glTexParameteri(a,b,c);});}
#else
VOID_WRAP(glTexParameteri,(GLenum a,GLenum b,GLint c),(a,b,c))
#endif
VOID_WRAP(glShadeModel,(GLenum a),(a))
VOID_WRAP(glOrtho,(GLdouble a,GLdouble b,GLdouble c,GLdouble d,GLdouble e,GLdouble f),(a,b,c,d,e,f))
VOID_WRAP(glGetFloatv,(GLenum a,GLfloat *b),(a,b))
VOID_WRAP(glLightModelfv,(GLenum a,const GLfloat *b),(a,b))
VOID_WRAP(glLightfv,(GLenum a,GLenum b,const GLfloat *c),(a,b,c))
VOID_WRAP(glGetIntegerv,(GLenum a,GLint *b),(a,b))
VOID_WRAP(glNormal3f,(GLfloat a,GLfloat b,GLfloat c),(a,b,c))
RET_WRAP(GLuint,glGenLists,(GLsizei a),(a))
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glNewList(GLuint a,GLenum b){glNewList(a,b);}
void tb_gl_stdcall_glEndList(){glEndList();}
#else
VOID_WRAP(glNewList,(GLuint a,GLenum b),(a,b))
VOID_WRAP(glEndList,(void),())
#endif
VOID_WRAP(glCallList,(GLuint a),(a))
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glNormal3fv(const GLfloat *a){std::array<float,3> v={a[0],a[1],a[2]};record_gl([=]{glNormal3fv(v.data());});}
#else
VOID_WRAP(glNormal3fv,(const GLfloat *a),(a))
#endif
VOID_WRAP(glDepthMask,(GLboolean a),(a))
VOID_WRAP(glDepthFunc,(GLenum a),(a))
VOID_WRAP(glVertex3f,(GLfloat a,GLfloat b,GLfloat c),(a,b,c))
VOID_WRAP(glLoadMatrixf,(const GLfloat *a),(a))
VOID_WRAP(glMultMatrixf,(const GLfloat *a),(a))
VOID_WRAP(glBegin,(GLenum a),(a))
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glVertex3fv(const GLfloat *a){std::array<float,3> v={a[0],a[1],a[2]};record_gl([=]{glVertex3fv(v.data());});}
#else
VOID_WRAP(glVertex3fv,(const GLfloat *a),(a))
#endif
VOID_WRAP(glEnd,(void),())
void WAPI tb_gl_stdcall_glViewport(GLint x,GLint y,GLsizei width,GLsizei height) {tb_gl_viewport(x,y,width,height);}
VOID_WRAP(glDisable,(GLenum a),(a))
VOID_WRAP(glClear,(GLbitfield a),(a))
VOID_WRAP(glEnable,(GLenum a),(a))
VOID_WRAP(glTexCoord2f,(GLfloat a,GLfloat b),(a,b))
VOID_WRAP(glMatrixMode,(GLenum a),(a))
VOID_WRAP(glLoadIdentity,(void),())
VOID_WRAP(glPushMatrix,(void),())
VOID_WRAP(glPopMatrix,(void),())
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glTexParameterf(GLenum a,GLenum b,GLfloat c){if(b==GL_TEXTURE_MAG_FILTER&&c>=GL_NEAREST_MIPMAP_NEAREST)c=GL_LINEAR;record_gl([=]{glTexParameterf(a,b,c);});}
#else
VOID_WRAP(glTexParameterf,(GLenum a,GLenum b,GLfloat c),(a,b,c))
#endif
VOID_WRAP(glTexSubImage2D,(GLenum a,GLint b,GLint c,GLint d,GLsizei e,GLsizei f,GLenum g,GLenum h,const void *i),(a,b,c,d,e,f,g,h,i))
VOID_WRAP(glFlush,(void),())
VOID_WRAP(glColor4f,(GLfloat a,GLfloat b,GLfloat c,GLfloat d),(a,b,c,d))
VOID_WRAP(glBlendFunc,(GLenum a,GLenum b),(a,b))
#ifdef __EMSCRIPTEN__
void tb_gl_stdcall_glBindTexture(GLenum target,GLuint id){record_gl([=]{auto &native=browser_textures[id];if(!native)glGenTextures(1,&native);glBindTexture(target,native);});}
#else
VOID_WRAP(glBindTexture,(GLenum a,GLuint b),(a,b))
#endif
VOID_WRAP(glPixelStorei,(GLenum a,GLint b),(a,b))
RET_WRAP(const GLubyte *,glGetString,(GLenum a),(a))
VOID_WRAP(gluPerspective,(GLdouble a,GLdouble b,GLdouble c,GLdouble d),(a,b,c,d))
RET_WRAP(GLint,gluBuild2DMipmaps,(GLenum a,GLint b,GLsizei c,GLsizei d,GLenum e,GLenum f,const void *g),(a,b,c,d,e,f,g))
VOID_WRAP(glMultiTexCoord1fARB,(GLenum a,GLfloat b),(a,b))
VOID_WRAP(glMultiTexCoord2fARB,(GLenum a,GLfloat b,GLfloat c),(a,b,c))
VOID_WRAP(glMultiTexCoord3fARB,(GLenum a,GLfloat b,GLfloat c,GLfloat d),(a,b,c,d))
VOID_WRAP(glMultiTexCoord4fARB,(GLenum a,GLfloat b,GLfloat c,GLfloat d,GLfloat e),(a,b,c,d,e))
VOID_WRAP(glActiveTextureARB,(GLenum a),(a))
VOID_WRAP(glClientActiveTextureARB,(GLenum a),(a))

struct Entry { const char *name;void *address; };
#define ENTRY(name) {#name,(void *)&tb_gl_stdcall_##name}
static const struct Entry entries[]={
 ENTRY(glTexGeni),ENTRY(glMaterialf),ENTRY(glCullFace),ENTRY(glMaterialfv),ENTRY(glPointSize),ENTRY(glClearDepth),
 ENTRY(glDeleteTextures),ENTRY(glTexImage2D),ENTRY(glTexEnvi),ENTRY(glTexParameteri),ENTRY(glShadeModel),ENTRY(glOrtho),
 ENTRY(glGetFloatv),ENTRY(glLightModelfv),ENTRY(glLightfv),ENTRY(glGetIntegerv),ENTRY(glNormal3f),ENTRY(glGenLists),
 ENTRY(glNewList),ENTRY(glEndList),ENTRY(glCallList),ENTRY(glNormal3fv),ENTRY(glDepthMask),ENTRY(glDepthFunc),
 ENTRY(glVertex3f),ENTRY(glLoadMatrixf),ENTRY(glMultMatrixf),ENTRY(glBegin),ENTRY(glVertex3fv),ENTRY(glEnd),ENTRY(glViewport),
 ENTRY(glDisable),ENTRY(glClear),ENTRY(glEnable),ENTRY(glTexCoord2f),ENTRY(glMatrixMode),ENTRY(glLoadIdentity),
 ENTRY(glPushMatrix),ENTRY(glPopMatrix),ENTRY(glTexParameterf),ENTRY(glTexSubImage2D),ENTRY(glFlush),ENTRY(glColor4f),
 ENTRY(glBlendFunc),ENTRY(glBindTexture),ENTRY(glPixelStorei),ENTRY(glGetString),ENTRY(gluPerspective),ENTRY(gluBuild2DMipmaps),
 ENTRY(glMultiTexCoord1fARB),ENTRY(glMultiTexCoord2fARB),ENTRY(glMultiTexCoord3fARB),ENTRY(glMultiTexCoord4fARB),
 ENTRY(glActiveTextureARB),ENTRY(glClientActiveTextureARB)
};
void *tb_gl_stdcall_proc(const char *name) {
 for(unsigned i=0;i<sizeof(entries)/sizeof(entries[0]);i++)if(!strcmp(name,entries[i].name))return entries[i].address;
 /* An unknown function has no known stdcall signature. Returning a native
  * cdecl pointer here would corrupt the engine stack. */
 return NULL;
}
#ifdef __EMSCRIPTEN__
}
#endif

#define _GNU_SOURCE
#include "titbit_platform.h"
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <sys/mman.h>
#include <sys/resource.h>
#ifndef __EMSCRIPTEN__
#include <sys/syscall.h>
#endif
#include <unistd.h>
#include <errno.h>
#ifndef SCHED_IDLE
#define SCHED_IDLE SCHED_OTHER
#endif
#if defined(__i386__)
#define WAPI __attribute__((stdcall))
#else
#define WAPI
#endif
extern void WAPI SetLastError(uint32_t);
typedef uint32_t (WAPI *ThreadRoutine)(void *);
typedef struct { uint32_t magic;pthread_t id;pthread_mutex_t mutex;pthread_cond_t condition;unsigned suspended,refs;ThreadRoutine routine;void *argument; } Thread;
#define THREAD_MAGIC 0x54425448u
static void thread_release(Thread *thread) {
 if(__atomic_sub_fetch(&thread->refs,1,__ATOMIC_ACQ_REL)==0){pthread_cond_destroy(&thread->condition);pthread_mutex_destroy(&thread->mutex);free(thread);}
}
static void *thread_entry(void *arg) {
 Thread *thread=arg;pthread_mutex_lock(&thread->mutex);
 while(thread->suspended)pthread_cond_wait(&thread->condition,&thread->mutex);
 pthread_mutex_unlock(&thread->mutex);uint32_t result=thread->routine(thread->argument);thread_release(thread);return (void*)(uintptr_t)result;
}
void *WAPI CreateThread(void *security,size_t stack,ThreadRoutine routine,void *argument,uint32_t flags,uint32_t *id) {
 (void)security;if(!routine||(flags&~4u)){SetLastError(87);return NULL;}
 Thread *thread=calloc(1,sizeof(*thread));if(!thread){SetLastError(8);return NULL;}
 thread->magic=THREAD_MAGIC;thread->refs=2;thread->routine=routine;thread->argument=argument;thread->suspended=!!(flags&4);
 pthread_mutex_init(&thread->mutex,NULL);pthread_cond_init(&thread->condition,NULL);
 pthread_attr_t attributes;pthread_attr_init(&attributes);pthread_attr_setdetachstate(&attributes,PTHREAD_CREATE_DETACHED);
 if(stack&&pthread_attr_setstacksize(&attributes,stack)!=0){pthread_attr_destroy(&attributes);thread->refs=1;thread_release(thread);SetLastError(87);return NULL;}
 int result=pthread_create(&thread->id,&attributes,thread_entry,thread);pthread_attr_destroy(&attributes);
 if(result){thread->refs=1;thread_release(thread);SetLastError((uint32_t)result);return NULL;}
 if(id)*id=(uint32_t)(uintptr_t)thread->id;
 return thread;
}
uint32_t WAPI ResumeThread(Thread *thread) {
 if(!thread||thread->magic!=THREAD_MAGIC){SetLastError(6);return 0xffffffffu;}
 pthread_mutex_lock(&thread->mutex);unsigned old=thread->suspended;thread->suspended=0;pthread_cond_broadcast(&thread->condition);pthread_mutex_unlock(&thread->mutex);return old;
}
int32_t WAPI SetThreadPriority(Thread *thread,int priority) {
 if(!thread||thread->magic!=THREAD_MAGIC){SetLastError(6);return 0;}
 struct sched_param parameters={0};int policy=SCHED_OTHER;
 if(priority>0){policy=SCHED_RR;parameters.sched_priority=priority;}
 else if(priority<0)policy=SCHED_IDLE;
 int result=pthread_setschedparam(thread->id,policy,&parameters);if(result)SetLastError((uint32_t)result);return result==0;
}
int tb_kernel_close_handle(void *handle) {
 Thread *thread=handle;if(!thread||thread->magic!=THREAD_MAGIC)return 0;thread->magic=0;thread_release(thread);return 1;
}
/* CRITICAL_SECTION is 24 bytes on Win32. Native mutex storage is indirect so
 * its larger pthread representation never overwrites a reconstructed object. */
void WAPI InitializeCriticalSection(void *storage) {
 pthread_mutex_t *mutex=malloc(sizeof(*mutex));if(!mutex)abort();pthread_mutexattr_t attributes;
 pthread_mutexattr_init(&attributes);pthread_mutexattr_settype(&attributes,PTHREAD_MUTEX_RECURSIVE);
 if(pthread_mutex_init(mutex,&attributes))abort();
 pthread_mutexattr_destroy(&attributes);
 memset(storage,0,6*sizeof(uint32_t));memcpy(storage,&mutex,sizeof(mutex));
}
static pthread_mutex_t *critical(void *storage){pthread_mutex_t *mutex=NULL;memcpy(&mutex,storage,sizeof(mutex));return mutex;}
void WAPI EnterCriticalSection(void *storage){pthread_mutex_lock(critical(storage));}
void WAPI LeaveCriticalSection(void *storage){pthread_mutex_unlock(critical(storage));}
void WAPI DeleteCriticalSection(void *storage){pthread_mutex_t *mutex=critical(storage);pthread_mutex_destroy(mutex);free(mutex);memset(storage,0,6*sizeof(uint32_t));}
#define TLS_SLOTS 1088
static pthread_mutex_t tls_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_key_t tls_keys[TLS_SLOTS];static unsigned char tls_used[TLS_SLOTS];
uint32_t WAPI TlsAlloc(void){pthread_mutex_lock(&tls_mutex);for(unsigned i=0;i<TLS_SLOTS;i++)if(!tls_used[i]&&pthread_key_create(&tls_keys[i],NULL)==0){tls_used[i]=1;pthread_mutex_unlock(&tls_mutex);return i;}pthread_mutex_unlock(&tls_mutex);SetLastError(8);return 0xffffffffu;}
int32_t WAPI TlsSetValue(uint32_t slot,void *value){if(slot>=TLS_SLOTS||!tls_used[slot]){SetLastError(87);return 0;}int result=pthread_setspecific(tls_keys[slot],value);if(result)SetLastError((uint32_t)result);return result==0;}
void *WAPI TlsGetValue(uint32_t slot){if(slot>=TLS_SLOTS||!tls_used[slot]){SetLastError(87);return NULL;}SetLastError(0);return pthread_getspecific(tls_keys[slot]);}
int32_t WAPI TlsFree(uint32_t slot){if(slot>=TLS_SLOTS){SetLastError(87);return 0;}pthread_mutex_lock(&tls_mutex);if(!tls_used[slot]){pthread_mutex_unlock(&tls_mutex);SetLastError(87);return 0;}pthread_key_delete(tls_keys[slot]);tls_used[slot]=0;pthread_mutex_unlock(&tls_mutex);return 1;}

typedef struct Mapping {void *address;size_t size;struct Mapping *next;} Mapping;
static Mapping *mappings;static pthread_mutex_t map_mutex=PTHREAD_MUTEX_INITIALIZER;
static int protection_flags(uint32_t protection){switch(protection){case 1:return PROT_NONE;case 2:return PROT_READ;case 4:case 8:return PROT_READ|PROT_WRITE;case 0x10:return PROT_EXEC;case 0x20:return PROT_READ|PROT_EXEC;case 0x40:case 0x80:return PROT_READ|PROT_WRITE|PROT_EXEC;default:return -1;}}
void *WAPI VirtualAlloc(void *address,size_t size,uint32_t type,uint32_t protection){
 int prot=protection_flags(protection);size_t page=(size_t)sysconf(_SC_PAGESIZE);
 if(!size||size>SIZE_MAX-page||!(type&0x3000)||(type&~0x3000u)||prot<0){SetLastError(87);return NULL;}
 size=(size+page-1)&~(page-1);
 if(address&&(type&0x1000)&&!(type&0x2000)) {
  pthread_mutex_lock(&map_mutex);Mapping *entry;
  for(entry=mappings;entry;entry=entry->next)if((uintptr_t)address>=(uintptr_t)entry->address&&size<=entry->size&&((uintptr_t)address-(uintptr_t)entry->address)<=entry->size-size)break;
  int result=entry?mprotect(address,size,prot):-1;pthread_mutex_unlock(&map_mutex);
  if(result){SetLastError(entry?(uint32_t)errno:487);return NULL;}return address;
 }
 if(!(type&0x1000))prot=PROT_NONE;
 void *result=mmap(address,size,prot,MAP_PRIVATE|MAP_ANONYMOUS|(address?MAP_FIXED_NOREPLACE:0),-1,0);if(result==MAP_FAILED){SetLastError((uint32_t)errno);return NULL;}
 Mapping *entry=malloc(sizeof(*entry));if(!entry){munmap(result,size);SetLastError(8);return NULL;}entry->address=result;entry->size=size;
 pthread_mutex_lock(&map_mutex);entry->next=mappings;mappings=entry;pthread_mutex_unlock(&map_mutex);return result;
}
int32_t WAPI VirtualFree(void *address,size_t size,uint32_t type){
 pthread_mutex_lock(&map_mutex);Mapping **cursor=&mappings;while(*cursor&&(*cursor)->address!=address)cursor=&(*cursor)->next;
 if(!*cursor||(type==0x8000&&size!=0)||(type!=0x8000&&type!=0x4000)){pthread_mutex_unlock(&map_mutex);SetLastError(87);return 0;}
 Mapping *entry=*cursor;int result;
 if(type==0x8000){result=munmap(entry->address,entry->size);if(result==0){*cursor=entry->next;free(entry);}}
 else {if(!size)size=entry->size;if(size>entry->size){pthread_mutex_unlock(&map_mutex);SetLastError(87);return 0;}result=mprotect(address,size,PROT_NONE);if(result==0)result=madvise(address,size,MADV_DONTNEED);}
 pthread_mutex_unlock(&map_mutex);if(result)SetLastError((uint32_t)errno);return result==0;
}

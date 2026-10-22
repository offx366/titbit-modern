import test from 'node:test';
import assert from 'node:assert/strict';
import {createGateway,proofDigest}from './gateway.mjs';
import {createHash}from 'node:crypto';
const hash=b=>createHash('sha256').update(b).digest('hex');
class Bucket {
  objects=new Map();
  async put(key,value,options={}){
    // No await before condition+commit: model an atomic R2 If-None-Match.
    if(options.onlyIf?.get('If-None-Match')==='*'&&this.objects.has(key))return null;
    const data=typeof value==='string'?Buffer.from(value):Buffer.from(value);
    const obj={key,data,size:data.length,customMetadata:options.customMetadata||{}};
    this.objects.set(key,obj);return obj;
  }
  async get(key,options={}){const v=this.objects.get(key);if(!v)return null;
    const b=options.range?v.data.subarray(options.range.offset,options.range.offset+options.range.length):v.data;
    return {...v,body:new Response(b).body,arrayBuffer:async()=>b,text:async()=>b.toString()};}
  async head(key){return this.objects.get(key)||null;}
  async list(){return{objects:[...this.objects.values()]};}
  async delete(keys){for(const k of Array.isArray(keys)?keys:[keys])this.objects.delete(k);}
}
async function fixture(){
  const files={},raw={};for(let i=0;i<19;i++){
    const name=i===0?'QUEST.ezd':`video${i}.avi`;raw[name]=Buffer.alloc(8192,i+13);files[name]={size:8192,sha256:hash(raw[name])};}
  const payload=Buffer.from('PRIVATE MOD ART'),pack={id:'widescreen',version:'0.1.0',size:payload.length,sha256:hash(payload)};
  const bucket=new Bucket();for(const [name,data]of Object.entries(raw))await bucket.put('reference/'+name,data);
  await bucket.put('mods/'+pack.sha256+'.titbitmod',payload,{customMetadata:{sha256:pack.sha256}});
  const gate=createGateway(files,pack),env={BUCKET:bucket,GATE_ADMIN_TOKEN:'not-shipped-to-client'};
  const call=(path,method='GET',data,extra={})=>gate.fetch(new Request('https://test.invalid'+path,{method,
    headers:{'CF-Connecting-IP':'203.0.113.1',...extra},body:data?JSON.stringify(data):undefined}),env,{});
  const challenge=async()=>{const r=await call('/v1/challenge','POST',{mod:pack.id,version:pack.version});assert.equal(r.status,200);return r.json();};
  const answer=c=>proofDigest(c,s=>raw[s.name].subarray(s.offset,s.offset+s.length));
  return{gate,env,bucket,call,challenge,answer,pack,payload};
}
test('unauthorized direct paths never return private art or references',async()=>{
  const f=await fixture();for(const path of ['/v1/download','/reference/QUEST.ezd','/mods/'+f.pack.sha256+'.titbitmod','/admin/status']){
    const r=await f.call(path);assert.ok([403,404].includes(r.status));assert.match(r.headers.get('cache-control'),/no-store/);assert.notEqual(await r.text(),f.payload.toString());}
});
test('fresh challenge covers every file; constant published hash is rejected',async()=>{
  const f=await fixture(),a=await f.challenge(),b=await f.challenge();assert.notEqual(a.nonce,b.nonce);assert.equal(new Set(a.samples.map(x=>x.name)).size,19);
  assert.equal((await f.call('/v1/prove','POST',{id:a.id,proof:f.pack.sha256})).status,403);
  assert.equal((await f.call('/v1/prove','POST',{id:a.id,proof:await f.answer(a)})).status,403);
});
test('a correct answer authorizes one download; nonce and token replay fail',async()=>{
  const f=await fixture(),c=await f.challenge(),proof=await f.answer(c);
  const r=await f.call('/v1/prove','POST',{id:c.id,proof});assert.equal(r.status,200);const ticket=await r.json();
  assert.equal((await f.call('/v1/prove','POST',{id:c.id,proof})).status,403);
  const headers={Authorization:'Bearer '+ticket.token};
  assert.equal((await f.call('/v1/download?token='+ticket.token,'GET',null,headers)).status,400);
  assert.equal((await f.call('/v1/download','GET',null,{...headers,Range:'bytes=0-9'})).status,400);
  const download=await f.call('/v1/download','GET',null,headers);assert.equal(download.status,200);assert.equal(await download.text(),f.payload.toString());
  assert.equal((await f.call('/v1/download','GET',null,headers)).status,403);
});
test('racing proof and download requests have a single winner',async()=>{
  const f=await fixture(),c=await f.challenge(),proof=await f.answer(c);
  const pair=await Promise.all([f.call('/v1/prove','POST',{id:c.id,proof}),f.call('/v1/prove','POST',{id:c.id,proof})]);
  assert.deepEqual(pair.map(r=>r.status).sort(),[200,403]);const ticket=await pair.find(r=>r.status===200).json();
  const downloads=await Promise.all([1,2].map(()=>f.call('/v1/download','GET',null,{Authorization:'Bearer '+ticket.token})));
  assert.deepEqual(downloads.map(r=>r.status).sort(),[200,403]);
});
test('expired challenge and token, and a different network identity, fail closed',async()=>{
  const f=await fixture(),c=await f.challenge(),proof=await f.answer(c);const old=Date.now;
  try{Date.now=()=>old()+181000;assert.equal((await f.call('/v1/prove','POST',{id:c.id,proof})).status,403);}finally{Date.now=old;}
  const d=await f.challenge(),ticket=await(await f.call('/v1/prove','POST',{id:d.id,proof:await f.answer(d)})).json();
  assert.equal((await f.call('/v1/download','GET',null,{Authorization:'Bearer '+ticket.token,'CF-Connecting-IP':'203.0.113.2'})).status,403);
  try{Date.now=()=>old()+121000;assert.equal((await f.call('/v1/download','GET',null,{Authorization:'Bearer '+ticket.token})).status,403);}finally{Date.now=old;}
});
test('rate limit is applied before private reference reads',async()=>{
  const f=await fixture();for(let i=0;i<8;i++)await f.challenge();assert.equal((await f.call('/v1/challenge','POST',{mod:'widescreen',version:'0.1.0'})).status,429);
});

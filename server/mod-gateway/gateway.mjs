/* File availability verification, not a license/ownership assertion.
 * R2 never has a public object route. All reads are explicitly authorized.
 * No dependencies; build embeds only the public hashes/sizes, never asset bytes.
 */
const utf8 = new TextEncoder();
const headers = {'Cache-Control':'private, no-store, max-age=0','X-Content-Type-Options':'nosniff',
  'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'"};
const hex = a => [...new Uint8Array(a)].map(x=>x.toString(16).padStart(2,'0')).join('');
const random = () => hex(crypto.getRandomValues(new Uint8Array(32)));
const hash = async a => hex(await crypto.subtle.digest('SHA-256',typeof a==='string'?utf8.encode(a):a));
const equal = (a,b) => {
  if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;
  let v=0;for(let i=0;i<a.length;i++)v|=a.charCodeAt(i)^b.charCodeAt(i);return v===0;
};
const json = (value,status=200) => new Response(JSON.stringify(value),{status,headers:{...headers,'Content-Type':'application/json'}});
const failure = (status,code) => Object.assign(new Error(code),{status,code});
const recordKey = (kind,id) => `state/${kind}/${id}`;
async function body(req,max=16384) {
  if(Number(req.headers.get('content-length'))>max)throw failure(413,'body_too_large');
  const reader=req.body?.getReader();if(!reader)throw failure(400,'missing_body');
  const chunks=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
    if(size>max){await reader.cancel();throw failure(413,'body_too_large');}chunks.push(value);}
  const all=new Uint8Array(size);let pos=0;for(const v of chunks){all.set(v,pos);pos+=v.length;}return all;
}
async function readJSON(req) {
  try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await body(req)));}
  catch(e){if(e.status)throw e;throw failure(400,'invalid_json');}
}
async function putState(bucket,kind,id,value) {
  return bucket.put(recordKey(kind,id),JSON.stringify(value),{customMetadata:{expires:String(value.expires)}});
}
async function getState(bucket,kind,id) {
  const obj=await bucket.get(recordKey(kind,id));return obj?JSON.parse(await obj.text()):null;
}
async function claim(bucket,kind,id,expires) {
  const out=await bucket.put(recordKey('used-'+kind,id),'1',{
    onlyIf:new Headers({'If-None-Match':'*'}),customMetadata:{expires:String(expires)}});
  return !!out;
}
async function cleanup(bucket,now) {
  const page=await bucket.list({prefix:'state/',limit:100,include:['customMetadata']});
  const keys=page.objects.filter(x=>Number(x.customMetadata?.expires)<now).map(x=>x.key);
  if(keys.length)await bucket.delete(keys);
}
async function limiter(bucket,owner,now) {
  // An IP is stored only as a secret-salted hash, for at most two minutes.
  const window=Math.floor(now/60),expires=(window+2)*60;
  for(let i=0;i<8;i++)if(await claim(bucket,'rate',`${owner}-${window}-${i}`,expires))return;
  throw failure(429,'try_later');
}
export function proofPrefix(c) {
  return utf8.encode(`titbit-possession-v1\n${c.id}\n${c.nonce}\n${c.packageSha256}\n`);
}
export async function proofDigest(challenge,read) {
  const chunks=[proofPrefix(challenge)];let length=chunks[0].length;
  for(const sample of challenge.samples){
    const label=utf8.encode(`${sample.name}\0${sample.offset}\0${sample.length}\0`);
    const data=new Uint8Array(await read(sample));
    if(data.length!==sample.length)throw failure(503,'reference_unavailable');
    chunks.push(label,data);length+=label.length+data.length;
  }
  const all=new Uint8Array(length);let pos=0;for(const value of chunks){all.set(value,pos);pos+=value.length;}
  return hash(all);
}
export function createGateway(files,pack) {
  const chunkSize=8*1024*1024;
  const records={...files,mod:{size:pack.size,sha256:pack.sha256}};
  const objectKey=name=>name==='mod'?`mods/${pack.sha256}.titbitmod`:'reference/'+name;
  const readReference=async (bucket,s)=>{
    const v=await bucket.get(objectKey(s.name),{range:{offset:s.offset,length:s.length}});
    if(!v||!v.body)throw failure(503,'reference_unavailable');return v.arrayBuffer();
  };
  async function admin(req,env,path) {
    const supplied=req.headers.get('Authorization')||'';
    if(!env.GATE_ADMIN_TOKEN||!equal(supplied,'Bearer '+env.GATE_ADMIN_TOKEN))throw failure(404,'not_found');
    const url=new URL(req.url),bucket=env.BUCKET;
    if(path==='/admin/status'&&req.method==='GET'){
      const objects=[];for(const [name,rec]of Object.entries(records)){
        const head=await bucket.head(objectKey(name));objects.push({name,verified:head?.size===rec.size&&head?.customMetadata?.sha256===rec.sha256});}
      return json({objects,ready:objects.every(x=>x.verified)});
    }
    if(path==='/admin/cleanup'&&req.method==='POST'){await cleanup(bucket,Date.now()/1000);return json({ok:true});}
    const match=path.match(/^\/admin\/objects\/([^/]+)\/(part|commit)$/);
    if(!match||req.method!=='POST')throw failure(404,'not_found');
    const name=decodeURIComponent(match[1]),rec=records[name];if(!rec)throw failure(404,'not_found');
    const count=Math.ceil(rec.size/chunkSize),prefix='seed/'+encodeURIComponent(name)+'/';
    if(match[2]==='part'){
      const i=Number(url.searchParams.get('index'));
      if(!Number.isSafeInteger(i)||i<0||i>=count)throw failure(400,'invalid_part');
      const expected=Math.min(chunkSize,rec.size-i*chunkSize),raw=await body(req,expected);
      if(raw.length!==expected||await hash(raw)!==req.headers.get('X-Chunk-SHA256'))throw failure(400,'invalid_part');
      await bucket.put(prefix+i,raw,{customMetadata:{expires:String(Math.floor(Date.now()/1000)+86400)}});
      return json({part:i,size:expected});
    }
    // Bounded-memory concatenation, provider-verified full-file checksum.
    const stream=new FixedLengthStream(rec.size);
    const writer=stream.writable.getWriter();
    const producer=(async()=>{try{
      for(let i=0;i<count;i++){
        const obj=await bucket.get(prefix+i);if(!obj||obj.size!==Math.min(chunkSize,rec.size-i*chunkSize))throw failure(409,'missing_part');
        const reader=obj.body.getReader();try{while(true){const v=await reader.read();if(v.done)break;await writer.write(v.value);}}finally{reader.releaseLock();}
      }await writer.close();
    }catch(e){await writer.abort(e).catch(()=>{});throw e;}})();
    const put=bucket.put(objectKey(name),stream.readable,{sha256:rec.sha256,customMetadata:{sha256:rec.sha256},
      httpMetadata:{contentType:'application/octet-stream',cacheControl:'private, no-store'}});
    const results=await Promise.allSettled([producer,put]);
    if(results.some(x=>x.status==='rejected'))throw failure(409,'checksum_or_parts_failed');
    await bucket.delete(Array.from({length:count},(_,i)=>prefix+i));
    return json({name,size:rec.size,sha256:rec.sha256,verified:true});
  }
  return {async fetch(req,env,ctx) {
    try{
      const url=new URL(req.url),path=url.pathname,bucket=env.BUCKET,now=Math.floor(Date.now()/1000);
      if(!bucket||!env.GATE_ADMIN_TOKEN)throw failure(503,'not_configured');
      if(path.startsWith('/admin/'))return await admin(req,env,path);
      if(path==='/'&&req.method==='GET')return new Response('Титбит · закрытая выдача модов. Скачивание доступно через лаунчер после проверки файлов игры.',{headers:{...headers,'Content-Type':'text/plain; charset=utf-8'}});
      const ip=req.headers.get('CF-Connecting-IP')||'unknown';
      const owner=await hash(env.GATE_ADMIN_TOKEN+'\0'+ip);
      if(path==='/v1/challenge'&&req.method==='POST'){
        const input=await readJSON(req);if(input.mod!==pack.id||input.version!==pack.version)throw failure(400,'unsupported_mod');
        await limiter(bucket,owner,now);
        const ready=await bucket.head(objectKey('mod'));
        if(ready?.customMetadata?.sha256!==pack.sha256)throw failure(503,'package_unavailable');
        const c={protocol:1,id:random(),nonce:random(),expires:now+180,packageSha256:pack.sha256,samples:[]};
        for(const [name,record]of Object.entries(files))for(let i=0;i<(name==='QUEST.ezd'?16:1);i++){
          const length=Math.min(4096,record.size),limit=record.size-length+1;
          const offset=crypto.getRandomValues(new Uint32Array(1))[0]%limit;
          c.samples.push({name,offset,length});
        }
        const expected=await proofDigest(c,s=>readReference(bucket,s));
        await putState(bucket,'challenge',c.id,{expires:c.expires,expected,owner});
        if(crypto.getRandomValues(new Uint8Array(1))[0]<16&&ctx?.waitUntil)ctx.waitUntil(cleanup(bucket,now).catch(()=>{}));
        return json(c);
      }
      if(path==='/v1/prove'&&req.method==='POST'){
        const input=await readJSON(req);
        if(!/^[a-f0-9]{64}$/.test(input.id||'')||!/^[a-f0-9]{64}$/.test(input.proof||''))throw failure(400,'invalid_proof');
        const c=await getState(bucket,'challenge',input.id);
        if(!c||c.expires<=now||c.owner!==owner)throw failure(403,'proof_rejected');
        // A challenge permits one attempt, including failed attempts.
        if(!await claim(bucket,'challenge',input.id,c.expires)||!equal(c.expected,input.proof))throw failure(403,'proof_rejected');
        const token=random();await putState(bucket,'token',await hash(token),{owner,expires:now+120});
        return json({token,expires:now+120,sha256:pack.sha256,size:pack.size});
      }
      if(path==='/v1/download'&&req.method==='GET'){
        if(url.search||req.headers.has('Range'))throw failure(400,'invalid_download_request');
        const raw=req.headers.get('Authorization')||'',match=raw.match(/^Bearer ([a-f0-9]{64})$/);
        if(!match)throw failure(403,'download_rejected');
        const key=await hash(match[1]),token=await getState(bucket,'token',key);
        if(!token||token.expires<=now||token.owner!==owner)throw failure(403,'download_rejected');
        const obj=await bucket.get(objectKey('mod'));if(!obj||obj.size!==pack.size||obj.customMetadata?.sha256!==pack.sha256)throw failure(503,'package_unavailable');
        if(!await claim(bucket,'token',key,token.expires))throw failure(403,'download_rejected');
        return new Response(obj.body,{headers:{...headers,'Content-Type':'application/octet-stream','Content-Length':String(pack.size),
          'Content-Disposition':'attachment; filename="Titbit-Widescreen-0.1.0.titbitmod"'}});
      }
      throw failure(404,'not_found');
    }catch(e){if(!e.status)console.error('gate_error',String(e.message).slice(0,200));return json({error:e.code||'service_error'},e.status||503);}
  }};
}

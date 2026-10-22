// Exercise persistent asset caching in a real browser, independently of HTTP cache.
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {readFile, mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, join} from 'node:path';

const {chromium} = await import(process.env.TITBIT_PLAYWRIGHT_MODULE || 'playwright');
const moduleBytes = await readFile(resolve(process.argv[2] || '.local/pages', 'assets.js'));
let body = Buffer.from('original game asset'), downloads = 0, code = 200;
const descriptor = () => ({name:'asset.bin',url:'asset.bin',size:body.length,
  sha256:createHash('sha256').update(body).digest('hex')});
const server = http.createServer((request,response) => {
  response.setHeader('Cache-Control','no-store');
  if(request.url==='/game/assets.js') response.writeHead(200,{'Content-Type':'text/javascript'}).end(moduleBytes);
  else if(request.url==='/game/asset.bin') {downloads++;response.writeHead(code).end(body);}
  else if(request.url==='/game/') response.writeHead(200,{'Content-Type':'text/html'}).end('<link rel="icon" href="data:,">Asset cache probe');
  else response.writeHead(404).end();
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile=await mkdtemp(join(tmpdir(),'titbit-asset-cache-'));
const options={headless:true,channel:'chromium',args:['--no-sandbox']};
let context;
async function launch() {
  context=await chromium.launchPersistentContext(profile,options);
  const page=await context.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}/game/`);
  return page;
}
async function read(page,file) {
  return page.evaluate(async file=>{
    const {AssetStore}=await import('./assets.js');
    return Array.from(await new AssetStore().read(file));
  },file);
}
try {
  let page=await launch();
  const original=descriptor();
  assert.deepEqual(await read(page,original),Array.from(body));
  assert.equal(downloads,1);
  await page.reload();
  await context.route('**/asset.bin',route=>route.abort());
  assert.deepEqual(await read(page,original),Array.from(body));
  assert.equal(downloads,1,'Reload must not fetch an intact cached file');
  await context.close();context=null;
  page=await launch();
  await context.route('**/asset.bin',route=>route.abort());
  assert.deepEqual(await read(page,original),Array.from(body));
  assert.equal(downloads,1,'Browser restart must retain the cached file');
  await context.unroute('**/asset.bin');

  body=Buffer.from('new game asset revision');
  const updated=descriptor();
  assert.deepEqual(await read(page,updated),Array.from(body));
  assert.equal(downloads,2,'A changed hash must fetch the new revision');
  assert.deepEqual(await read(page,original),Array.from(Buffer.from('original game asset')));
  assert.equal(downloads,2);

  await page.evaluate(async file=>{
    const {AssetStore}=await import('./assets.js'),store=new AssetStore();
    await(await store.cache()).put(store.key(file),new Response('corrupt'));
  },updated);
  assert.deepEqual(await read(page,updated),Array.from(body));
  assert.equal(downloads,3,'A corrupt cached file must be repaired');

  await page.evaluate(async file=>{
    const {AssetStore}=await import('./assets.js'),store=new AssetStore();
    await(await store.cache()).delete(store.key(file));
  },updated);
  const good=body;
  body=Buffer.alloc(good.length,0);
  await assert.rejects(()=>read(page,updated),/Повреждён файл/);
  assert.equal(await page.evaluate(async file=>{
    const {AssetStore}=await import('./assets.js'),store=new AssetStore();
    return !!await(await store.cache()).match(store.key(file));
  },updated),false,'Invalid downloads must not enter the cache');
  body=good;
  code=404;
  await assert.rejects(()=>read(page,updated),/Не удалось прочитать/);
  code=200;

  const fallback=await page.evaluate(async file=>{
    const {AssetStore}=await import('./assets.js');
    let warnings=0;
    const store=new AssetStore({cacheStorage:{open:async()=>({match:async()=>undefined,
      put:async()=>{throw new DOMException('Full','QuotaExceededError');}})},onCacheError:()=>warnings++});
    const bytes=Array.from(await store.read(file));
    const uncached=Array.from(await new AssetStore({cacheStorage:null,onCacheError:()=>warnings++}).read(file));
    return {bytes,uncached,warnings};
  },updated);
  assert.deepEqual(fallback,{bytes:Array.from(body),uncached:Array.from(body),warnings:2});
  console.log('Asset cache: reload/restart with network blocked, hash updates, corruption repair, invalid download rejection and quota/disabled-storage fallback passed.');
}finally {
  await context?.close();
  await new Promise(resolve=>server.close(resolve));
  await rm(profile,{recursive:true,force:true});
}

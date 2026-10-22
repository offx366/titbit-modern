// Test at a project subpath on a server that supplies NO COOP/COEP headers.
// No game archive is required or sent to the server.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname} from 'node:path';

const {chromium} = await import(process.env.TITBIT_PLAYWRIGHT_MODULE || 'playwright');
const directory = resolve(process.argv[2] || '.local/pages');
const bundled = JSON.parse(await readFile(resolve(directory, 'game-assets.json'), 'utf8')).files.length > 0;
const prefix = '/titbit-modern/';
let assetRequests = 0, blockAssets = false;
const types = {'.js': 'text/javascript', '.html': 'text/html', '.wasm': 'application/wasm'};
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const relative = url.pathname.slice(prefix.length) || 'index.html';
  if (relative.startsWith('assets/')) {
    assetRequests++;
    response.setHeader('Cache-Control', 'no-store');
    if (blockAssets) { response.writeHead(503).end(); return; }
  }
  const file = resolve(directory, relative);
  if (!url.pathname.startsWith(prefix) || !file.startsWith(directory + '/')) {
    response.writeHead(404).end(); return;
  }
  try {
    const bytes = await readFile(file);
    response.writeHead(200, {'Content-Type': types[extname(file)] || 'text/plain'});
    response.end(bytes);
  } catch { response.writeHead(404).end(); }
});
await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(0, '127.0.0.1', resolve);
});
let browser;
try {
  browser = await chromium.launch({headless: true, channel: 'chromium',
    ...(process.env.TITBIT_CHROMIUM_EXECUTABLE ? {executablePath: process.env.TITBIT_CHROMIUM_EXECUTABLE} : {}),
    args: ['--no-sandbox', '--enable-unsafe-swiftshader']});
  for (const entry of ['', 'game.html']) {
    const context = await browser.newContext();
    const page = await context.newPage(), errors = [], uploads = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('request', request => { if (request.method() !== 'GET') uploads.push(request.url()); });
    let navigations = 0;
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++; });
    await page.goto(`http://127.0.0.1:${server.address().port}${prefix}${entry}`);
    await page.waitForFunction(bundled => document.querySelector('#status').textContent.includes(bundled ? 'Игра готова.' : 'Выберите QUEST.ezd'), bundled, {timeout: 60000});
    assert.equal(await page.locator('#file-pickers').isHidden(), bundled);
    assert.equal(await page.evaluate(() => crossOriginIsolated), true);
    assert.equal(await page.evaluate(() => titbit.HEAPU8.buffer instanceof SharedArrayBuffer), true);
    assert.equal(await page.evaluate(() => navigator.serviceWorker.controller !== null), true);
    assert.equal(navigations, 2, 'A fresh static-host visit should reload exactly once');
    assert.deepEqual(errors, []);
    // A normal reload stays isolated, preserves local saves, and does not loop.
    await page.evaluate(async () => {
      const {SaveStore} = await import('./saves.js');
      await new SaveStore({name: 'titbit-pages-test'}).write(1, new Uint8Array(408).fill(17));
    });
    await page.reload();
    await page.waitForFunction(bundled => document.querySelector('#status').textContent.includes(bundled ? 'Игра готова.' : 'Выберите QUEST.ezd'), bundled, {timeout: 60000});
    assert.equal(navigations, 3);
    assert.equal(await page.evaluate(async () => {
      const {SaveStore} = await import('./saves.js');
      return (await new SaveStore({name: 'titbit-pages-test'}).read(1)).every(byte => byte === 17);
    }), true);
    assert.deepEqual(errors, []);
    if (bundled) {
      await page.locator('#start').click();
      await page.waitForFunction(() => titbitFrames > 120, null, {timeout: 60000});
      assert.equal(await page.evaluate(() => document.querySelector('#log').textContent.includes('introbuka.scv compiled')), true);
      assert.equal(await page.evaluate(() => titbit.titbitAudio.ready), true);
      assert.deepEqual(errors, []);
      const coldRequests = assetRequests;
      blockAssets = true;
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Игра готова.'), null, {timeout: 60000});
      await page.locator('#start').click();
      await page.waitForFunction(() => titbitFrames > 120 || document.querySelector('#status').textContent.startsWith('Ошибка:'), null, {timeout: 60000});
      assert.ok(await page.evaluate(() => titbitFrames > 120), await page.locator('#status').textContent());
      assert.equal(assetRequests, coldRequests, 'Reload must launch the actual engine with no requests for bundled assets');
      assert.equal(await page.evaluate(() => titbit.titbitAudio.ready), true);
      assert.deepEqual(errors, []);
      blockAssets = false;
      console.log('Bundled game reload: no network requests for QUEST.ezd or AVI; video and audio running.');
    }
    if (!bundled) {
      await page.locator('#archive').setInputFiles({name: 'QUEST.ezd', mimeType: 'application/octet-stream', buffer: Buffer.from([101,122,100,255])});
      await page.locator('#start').click();
      assert.match(await page.locator('#status').textContent(), /Выберите все 18 AVI/);
      assert.equal(await page.evaluate(() => titbitFrames), 0);
      assert.equal(await page.locator('#file-pickers').isVisible(), true);
      assert.equal(await page.locator('#start').isEnabled(), true);
      await page.locator('#videos').setInputFiles({name: 'BUKA.AVI', mimeType: 'video/x-msvideo', buffer: Buffer.from([1])});
      await page.locator('#start').click();
      const missing = await page.locator('#status').textContent();
      assert.ok(missing.includes('intro2.avi') && !missing.includes('buka.avi'));
      assert.equal(await page.evaluate(() => titbitFrames), 0);
    }
    assert.deepEqual(uploads, [], 'No game data or saves should be uploaded');
    await context.close();
  }
  console.log('Static Pages: project subpath, isolation/reload, Wasm threads, persistent saves, no uploads passed.');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}

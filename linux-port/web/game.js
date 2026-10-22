/* Original engine and assets stay local to this browser. */
import { SaveStore } from './saves.js';
import { AssetStore } from './assets.js';
const canvas = document.querySelector('#canvas');
const status = document.querySelector('#status');
const start = document.querySelector('#start');
const archive = document.querySelector('#archive');
const videos = document.querySelector('#videos');
const log = document.querySelector('#log');
const storage = document.querySelector('#storage');
const assetStorage = document.querySelector('#asset-storage');
const saveSlot = document.querySelector('#save-slot');
const exportSave = document.querySelector('#export-save');
const importSave = document.querySelector('#import-save');
const saves = new SaveStore();
const assets = new AssetStore({onStatus: message, onCacheError: () => {
  if (assetStorage) assetStorage.textContent = 'Кэш игровых файлов недоступен. Игра запустится, но при следующем запуске может потребоваться загрузка.';
}});
let pendingSaves = Promise.resolve(), restoring = false;
let engine, running = false;
let bundledFiles = [];
const requiredVideos = ['acid.avi', 'belka.avi', 'belka2.avi', 'buh.avi', 'buh2.avi',
  'buka.avi', 'cat_1.avi', 'cat_2.avi', 'dans.avi', 'dost.avi', 'fon.avi',
  'gameboom.avi', 'gameover.avi', 'happyend.avi', 'intro.avi', 'intro2.avi', 'porno.avi', 'vzlab.avi'];
window.titbitFrames = 0;
const logLimit = 120000;
let logHistory = '', logPending = [], logPendingSize = 0, logTimer;
function message(text) { status.textContent = text; }
function flushLog() {
  logTimer = undefined;
  logHistory = (logHistory + logPending.join('')).slice(-logLimit);
  logPending = []; logPendingSize = 0;
  log.textContent = logHistory;
  // Reading scrollHeight forces layout. It is useful only while the user is
  // actually reading the journal, and must never run inside the engine frame.
  if (log.closest('details').open) log.scrollTop = log.scrollHeight;
}
function report(text) {
  text = String(text);
  if (['begin draw', 'EndDraw'].includes(text.trim())) return;
  const line = `${text}\n`.slice(-logLimit);
  logPending.push(line); logPendingSize += line.length;
  // Keep the pending batch bounded even during very verbose scene loading.
  while (logPendingSize > logLimit) {
    const excess = logPendingSize - logLimit, first = logPending[0];
    if (first.length <= excess) logPendingSize -= logPending.shift().length;
    else { logPending[0] = first.slice(excess); logPendingSize -= excess; }
  }
  if (logTimer === undefined) logTimer = setTimeout(flushLog, 100);
}
function failure(error) { running = false; console.error(error); report(error.stack || error); message(`Ошибка: ${error.message || error}`); }
function frame() {
  if (!running) return;
  try { engine._titbit_web_frame(); window.titbitFrames++; requestAnimationFrame(frame); }
  catch (error) { failure(error); }
}
async function readRemoteFile(file) { return assets.read(file); }
async function loadRemoteVideos(files) {
  let next = 0, completed = 0, stopped = false;
  async function worker() {
    while (!stopped && next < files.length) {
      const file = files[next++];
      try {
        engine.FS.writeFile(`/${file.name.toLowerCase()}`, await readRemoteFile(file), { canOwn: true });
        message(`Подготовка роликов: ${++completed}/${files.length}…`);
      } catch (error) { stopped = true; throw error; }
    }
  }
  // Bound simultaneous downloads and memory, especially for large AVI files.
  const results = await Promise.allSettled(Array.from({length: Math.min(3, files.length)}, worker));
  const failed = results.find(result => result.status === 'rejected');
  if (failed) throw failed.reason;
}
async function play(bytes, remoteVideos = null) {
  start.disabled = true;
  try {
    if (bytes.length < 16 || bytes[0] !== 101 || bytes[1] !== 122 || bytes[2] !== 100 || bytes[3] !== 255) {
      throw new Error('Выбранный файл не является архивом QUEST.ezd');
    }
    engine.FS.mkdir('/game');
    engine.FS.writeFile('/game/QUEST.ezd', bytes, { canOwn: true });
    if (remoteVideos) {
      await loadRemoteVideos(remoteVideos);
    } else {
      for (const file of videos.files) {
        if (!/^[\w.-]+\.avi$/i.test(file.name)) continue;
        engine.FS.writeFile(`/${file.name.toLowerCase()}`, new Uint8Array(await file.arrayBuffer()), { canOwn: true });
      }
    }
    const bootstrap = await fetch('browser_start.scv');
    if (!bootstrap.ok) throw new Error('Не удалось загрузить сценарий запуска');
    engine.FS.writeFile('/game/browser_start.scv', await bootstrap.text());
    message('Запуск игры…');
    await new Promise(resolve => requestAnimationFrame(resolve));
    const result = engine.ccall('titbit_web_initialize', 'number', ['string'], ['startup.XML']);
    if (result) throw new Error(`Инициализация движка: ${result}`);
    document.querySelector('#files').hidden = true;
    running = true; canvas.focus({ preventScroll: true }); window.scrollTo(0, 0); requestAnimationFrame(frame);
    message('Управление мышью. Меню — Escape.');
  } catch (error) { failure(error); }
}
archive.addEventListener('change', () => { start.disabled = !engine || !archive.files.length; });
start.addEventListener('click', async () => {
  if (!bundledFiles.length) {
    const selected = new Set(Array.from(videos.files, file => file.name.toLowerCase()));
    const missing = requiredVideos.filter(name => !selected.has(name));
    if (missing.length) {
      message(`Выберите все 18 AVI из папки игры. Не хватает: ${missing.join(', ')}.`);
      videos.focus();
      return;
    }
  }
  start.disabled = true;
  try {
    if (bundledFiles.length) {
      await play(await readRemoteFile(bundledFiles.find(file => file.name === 'QUEST.ezd')),
        bundledFiles.filter(file => file.name !== 'QUEST.ezd'));
    } else await play(new Uint8Array(await archive.files[0].arrayBuffer()));
  }
  catch (error) { failure(error); }
});
canvas.addEventListener('contextmenu', event => event.preventDefault());
exportSave.addEventListener('click', async () => {
  try {
    await pendingSaves;
    const url = URL.createObjectURL(await saves.exportFile(Number(saveSlot.value)));
    const link = document.createElement('a');link.href = url;link.download = `slot${saveSlot.value}.sav`;link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { storage.textContent = error.message; }
});
importSave.addEventListener('change', async () => {
  if (!importSave.files.length) return;
  try {
    await pendingSaves;
    const slot = Number(saveSlot.value);
    await saves.importFile(slot, importSave.files[0]);
    restoring = true;
    try { engine.FS.writeFile(`/slot${slot}.sav`, await saves.read(slot)); }
    finally { restoring = false; }
    storage.textContent = `Слот ${slot} импортирован. Выберите его в игровом меню загрузки.`;
  } catch (error) { storage.textContent = error.message; }
  finally { importSave.value = ''; }
});
createTitbit({ canvas, print: report, printErr: report, onPhase: message,
  onAbort: reason => failure(new Error(String(reason))),
  onAudioError: error => failure(error)
}).then(async module => {
  engine = module; window.titbit = module;
  // Hydrate the exact filenames used by the unmodified game scripts before
  // they inspect their save slots. The original serializer still owns bytes.
  for (const { slot } of await saves.list()) {
    if (slot >= 1 && slot <= 6) engine.FS.writeFile(`/slot${slot}.sav`, await saves.read(slot));
  }
  const close = engine.FS.close.bind(engine.FS);
  engine.FS.close = stream => {
    const path = stream.path;
    const writable = (stream.flags & 3) !== 0;
    const result = close(stream);
    const match = /(?:^|\/)slot([1-6])\.sav$/i.exec(path);
    if (match && writable && !restoring) {
      const slot = Number(match[1]), bytes = engine.FS.readFile(path);
      storage.textContent = `Сохранение слота ${slot}…`;
      pendingSaves = pendingSaves.catch(() => {}).then(() => saves.write(slot, bytes)).then(() => {
        storage.textContent = `Слот ${slot} сохранён в браузере.`;
      }).catch(error => { storage.textContent = `Ошибка сохранения: ${error.message}`;throw error; });
      // Keep failures visible without an unhandled rejection in the frame loop.
      pendingSaves.catch(() => {});
    }
    return result;
  };
  exportSave.disabled = importSave.disabled = false;
  start.disabled = !archive.files.length; message('Выберите QUEST.ezd и нажмите «Играть».');
  const manifest = await fetch('game-assets.json', {cache: 'no-cache'});
  if (!manifest.ok) throw new Error('Не удалось прочитать список игровых файлов');
  const data = await manifest.json();
  if (data.version !== 1 || !Array.isArray(data.files)) throw new Error('Некорректный список игровых файлов');
  if (data.files.length) {
    const names = data.files.map(file => file.name);
    if (names.length !== 19 || new Set(names).size !== 19 || !names.includes('QUEST.ezd') ||
        data.files.some(file => !/^(QUEST\.ezd|[\w-]+\.avi)$/.test(file.name) ||
          file.url !== `assets/${file.name}` || !Number.isSafeInteger(file.size) || file.size <= 0 ||
          !/^[a-f0-9]{64}$/.test(file.sha256))) throw new Error('Некорректный список игровых файлов');
    bundledFiles = data.files;
    document.querySelector('#file-pickers').hidden = true;
    start.disabled = false;
    message('Игра готова. Нажмите «Играть».');
    if (assetStorage) assetStorage.textContent = 'Игровые файлы сохраняются в браузере для следующих запусков.';
  }
  // Explicit development server option; the archive is never part of the build.
  if (new URLSearchParams(location.search).has('local')) {
    message('Чтение локального архива…');
    const response = await fetch('/local-game/QUEST.ezd');
    if (!response.ok) throw new Error('Локальный архив недоступен');
    const listing = await fetch('/local-game/videos.json');
    if (!listing.ok) throw new Error('Не удалось получить список видеофайлов');
    const names = await listing.json();
    if (names.some(name => !/^[\w.-]+\.avi$/i.test(name))) throw new Error('Некорректное имя видеофайла');
    await play(new Uint8Array(await response.arrayBuffer()), names.map(name => ({name, url: `/local-game/${encodeURIComponent(name)}`})));
  }
}).catch(failure);

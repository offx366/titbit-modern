import { SaveStore, createSaveRuntime, SAVE_SIZE } from './saves.js';

const params = new URLSearchParams(location.search);
const dbName = params.get('db') || `titbit-save-test-${crypto.randomUUID()}`;
if (!/^titbit-save-test-[a-f0-9-]+$/.test(dbName)) throw new Error('Invalid test database name');
const store = new SaveStore({ name: dbName });
const connections = [store];
const status = document.querySelector('#status');
const passed = params.get('phase') === 'reload' ? JSON.parse(sessionStorage.getItem(dbName) || '[]') : [];
const fixture = seed => Uint8Array.from({ length: SAVE_SIZE }, (_, index) => (index * 37 + seed) & 255);
const equal = (actual, expected, message) => {
  if (!(actual instanceof Uint8Array) || actual.length !== expected.length ||
      actual.some((value, index) => value !== expected[index])) throw new Error(message);
};
const rejects = async (operation, message) => {
  try { await operation(); } catch { return; }
  throw new Error(message);
};
async function check(name, operation) {
  await operation();
  passed.push(name);
  status.textContent = passed.map(name => `PASS ${name}`).join('\n');
}

async function run() {
  const response = await fetch('titbit-save-probe.wasm');
  if (!response.ok) throw new Error(`Wasm HTTP ${response.status}`);
  const runtime = await createSaveRuntime(await response.arrayBuffer(), store);
  if (params.get('phase') !== 'reload') {
    await check('original SaveGame → IndexedDB → original LoadGame', async () => {
      runtime.setState(fixture(7));
      await runtime.save(0);
      runtime.setState(new Uint8Array(SAVE_SIZE));
      await runtime.load(0);
      equal(runtime.getState(), fixture(7), 'Roundtrip changed engine bytes');
    });
    await check('overwrite slot', async () => {
      runtime.setState(fixture(23));
      await runtime.save(0);
      runtime.setState(new Uint8Array(SAVE_SIZE));
      await runtime.load(0);
      equal(runtime.getState(), fixture(23), 'Overwrite lost data');
    });
    await check('separate slots and concurrent writes', async () => {
      await Promise.all([store.write(1, fixture(11)), store.write(2, fixture(29))]);
      equal(await store.read(1), fixture(11), 'Slot 1 changed');
      equal(await store.read(2), fixture(29), 'Slot 2 changed');
      if ((await store.list()).length !== 3) throw new Error('Slot listing incorrect');
    });
    await check('snapshot mutable caller buffer', async () => {
      const bytes = fixture(31);
      const writing = store.write(3, bytes);
      bytes.fill(0);
      await writing;
      equal(await store.read(3), fixture(31), 'Buffer mutated before commit');
    });
    await check('export/import preserves original file bytes', async () => {
      const blob = await store.exportFile(0);
      equal(new Uint8Array(await blob.arrayBuffer()), fixture(23), 'Export added or changed bytes');
      await store.importFile(4, new File([blob], 'slot.sav'));
      await runtime.load(4);
      equal(runtime.getState(), fixture(23), 'Import changed state');
    });
    await check('reject truncated import without overwriting slot', async () => {
      await rejects(() => store.importFile(0, new File([new Uint8Array(407)], 'broken.sav')), 'Accepted short file');
      equal(await store.read(0), fixture(23), 'Invalid import overwrote good slot');
    });
    await check('aborted write after request success preserves previous slot', async () => {
      class AbortingStore extends SaveStore {
        transaction(mode, operation) {
          return super.transaction(mode, objectStore => {
            const request = operation(objectStore);
            if (mode === 'readwrite') request.addEventListener('success', () => objectStore.transaction.abort());
            return request;
          });
        }
      }
      const aborting = new AbortingStore({ name: dbName });
      connections.push(aborting);
      await rejects(() => aborting.write(0, fixture(99)), 'Reported success for aborted transaction');
      equal(await store.read(0), fixture(23), 'Aborted write damaged previous save');
      aborting.close();
    });
    await check('missing and corrupt saves do not change live engine state', async () => {
      runtime.setState(fixture(43));
      await rejects(() => runtime.load(99), 'Loaded missing slot');
      equal(runtime.getState(), fixture(43), 'Missing save changed state');
      await store.write(8, fixture(8));
      await new Promise((resolve, reject) => {
        const tx = store.connection.transaction('slots', 'readwrite');
        tx.oncomplete = resolve;
        tx.onabort = () => reject(tx.error);
        const slots = tx.objectStore('slots');
        const request = slots.get(8);
        request.onsuccess = () => {
          const record = request.result;
          record.bytes[50] ^= 255;
          slots.put(record);
        };
      });
      await rejects(() => runtime.load(8), 'Loaded corrupt slot');
      equal(runtime.getState(), fixture(43), 'Corrupt save changed state');
    });
    await check('storage denied and invalid slots fail explicitly', async () => {
      const denied = new SaveStore({ indexedDB: { open() { throw new DOMException('Denied', 'SecurityError'); } } });
      await rejects(() => denied.write(0, fixture(1)), 'Ignored storage denial');
      await rejects(() => store.write(-1, fixture(1)), 'Accepted invalid slot');
    });
    sessionStorage.setItem(dbName, JSON.stringify(passed));
    connections.forEach(connection => connection.close());
    location.replace(`save-checks.html?phase=reload&db=${encodeURIComponent(dbName)}`);
    return;
  }
  await check('restore persisted state after page reload and Wasm re-instantiation', async () => {
    await runtime.load(0);
    equal(runtime.getState(), fixture(23), 'State lost after reload');
    equal(await store.read(1), fixture(11), 'Other slot lost after reload');
  });
  await check('delete one slot preserves others', async () => {
    await store.remove(1);
    if (await store.read(1) !== null) throw new Error('Slot was not deleted');
    equal(await store.read(0), fixture(23), 'Delete removed another slot');
  });
  connections.forEach(connection => connection.close());
  await new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(dbName);
    request.onsuccess = resolve;
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Test cleanup blocked'));
  });
  sessionStorage.removeItem(dbName);
  document.documentElement.dataset.result = 'passed';
  document.documentElement.dataset.checks = passed.length;
  status.textContent += `\n\n${passed.length} checks passed; temporary database removed.`;
}

run().catch(error => {
  connections.forEach(connection => connection.close());
  status.textContent += `\nFAIL ${error.stack || error.message}`;
  document.documentElement.dataset.result = 'failed';
});

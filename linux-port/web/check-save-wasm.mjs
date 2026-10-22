// Serializer execution check only. Real IndexedDB/reload checks run in a browser.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createSaveRuntime, SAVE_SIZE } from './saves.js';

const path = process.argv[2];
if (!path) throw new Error('Usage: node check-save-wasm.mjs path/to/titbit-save-probe.wasm');
const bytes = await readFile(path);
const module = await WebAssembly.compile(bytes);
assert.deepEqual(WebAssembly.Module.imports(module).map(({ module, name, kind }) =>
  `${module}.${name}:${kind}`).sort(), ['fclose', 'fopen', 'fread', 'fwrite'].map(name => `env.${name}:function`));
const files = new Map();
const store = {
  async write(slot, data) { files.set(slot, data.slice()); },
  async read(slot) { return files.get(slot)?.slice() || null; },
};
const runtime = await createSaveRuntime(bytes, store);
const original = Uint8Array.from({ length: SAVE_SIZE }, (_, index) => (index * 37 + 23) & 255);
runtime.setState(original);
await runtime.save(0);
assert.deepEqual(files.get(0), original, 'Original SaveGame must write every byte');
runtime.setState(new Uint8Array(SAVE_SIZE));
await runtime.load(0);
assert.deepEqual(runtime.getState(), original, 'Original LoadGame must restore every byte');
await assert.rejects(runtime.load(1), /нет сохранения/);
assert.deepEqual(runtime.getState(), original, 'Missing slot must not change live state');
console.log(JSON.stringify({ status: 'save-serializer-passed', formatBytes: SAVE_SIZE,
  originalEngineSerializer: true, persistentStorageChecked: false }));

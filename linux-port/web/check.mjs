import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const path = process.argv[2];
if (!path) throw new Error('Usage: node check.mjs path/to/titbit-probe.wasm');
const module = await WebAssembly.compile(await readFile(path));
assert.deepEqual(WebAssembly.Module.imports(module), [], 'Probe must run without host imports');
const instance = await WebAssembly.instantiate(module);
const tests = ['probe_run', 'probe_inalloca', 'probe_geometry', 'probe_seer', 'probe_varargs'];
for (let repeat = 0; repeat < 100; repeat++) {
  for (const name of tests) {
    assert.equal(instance.exports[name](), 0, `${name}, iteration ${repeat}`);
  }
}
console.log(JSON.stringify({ status: 'probe-passed', tests, repetitions: 100, imports: 0,
  varargsABI: 'ms-x86-packed-v1' }));

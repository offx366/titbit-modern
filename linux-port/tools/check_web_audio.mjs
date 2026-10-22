// Exercise the actual processor with deterministic render quanta. The browser
// integration check additionally verifies the native decoder keeps this fed.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../web/audio-worklet.js', import.meta.url), 'utf8');
function fixture(rate = 44100, outputRate = rate) {
  let Processor;
  vm.runInNewContext(source, {
    AudioWorkletProcessor: class {}, sampleRate: outputRate,
    registerProcessor: (name, type) => { assert.equal(name, 'titbit-pcm'); Processor = type; },
    Int32Array, Float32Array, Atomics
  });
  const capacity = 1024, buffer = new SharedArrayBuffer(64 + capacity * 8);
  const control = new Int32Array(buffer, 0, 16);
  control[3] = 128; control[4] = 65535;
  const pcm = new Float32Array(buffer, 64);
  const processor = new Processor({processorOptions: {buffer, offset: 0, capacity, sourceRate: rate}});
  function queue(values) {
    const write = Atomics.load(control, 1) >>> 0;
    values.forEach((value, i) => {
      pcm[((write + i) & (capacity - 1)) * 2] = value;
      pcm[((write + i) & (capacity - 1)) * 2 + 1] = -value;
    });
    Atomics.store(control, 1, write + values.length);
  }
  function render(length) {
    const output = [new Float32Array(length), new Float32Array(length)];
    const live = processor.process([], [output]);
    return {output, live};
  }
  return {processor, control, queue, render};
}

{
  const f = fixture();
  f.queue([0.25, 0.5, -0.5]);
  assert.deepEqual([...f.render(5).output[0]], [0.25, 0.5, -0.5, 0, 0]);
  assert.equal(f.control[0], 3);
  assert.equal(f.control[7], 2);
  assert.deepEqual([...f.render(3).output[0]], [0, 0, 0]); // no stale replay
  f.queue([0.75, 0.5]);
  assert.deepEqual([...f.render(2).output[1]], [-0.75, -0.5]); // resumes
}
{
  const f = fixture();
  // Both the physical ring boundary and uint32 cursor overflow.
  Atomics.store(f.control, 0, -2); Atomics.store(f.control, 1, -2);
  f.queue([0.25, 0.5, 0.75, 1]);
  assert.deepEqual([...f.render(4).output[0]], [0.25, 0.5, 0.75, 1]);
  assert.equal(f.control[0], 2);
}
{
  const f = fixture();
  f.control[3] = 64; f.queue([1]);
  assert.equal(f.render(1).output[0][0], 0.5);
  f.control[5] = 1; f.queue([1]);
  assert.equal(f.render(1).output[0][0], 0);
  assert.equal(f.control[0], 2); // mute still consumes PCM
  f.control[2] = 1;
  assert.equal(f.render(1).live, false);
}
{
  const f = fixture(22050, 44100);
  f.queue([0, 0.5, 1]);
  assert.deepEqual([...f.render(4).output[0]], [0, 0.25, 0.5, 0.75]);
  // An external reset also discards any fractional interpolation position.
  f.render(1);
  Atomics.store(f.control, 0, Atomics.load(f.control, 1));
  f.queue([-0.5, -1]);
  assert.deepEqual([...f.render(2).output[0]], [-0.5, -0.75]);
}
{
  const f = fixture(88200, 44100);
  f.queue([0, 0.25, 0.5, 0.75]);
  assert.deepEqual([...f.render(2).output[0]], [0, 0.5]);
  assert.equal(f.control[0], 4);
}
console.log('Web audio: PCM, underrun/recovery, stereo, ring/cursor wrap, volume/mute, reset, resampling, close passed.');

// Control words are shared with audio_browser.cpp. The Audiere pthread writes
// stereo float PCM; this processor never calls Wasm or waits for the UI thread.
class TitbitPCM extends AudioWorkletProcessor {
  constructor({processorOptions: p}) {
    super();
    this.control = new Int32Array(p.buffer, p.offset, 16);
    this.pcm = new Float32Array(p.buffer, p.offset + 64, p.capacity * 2);
    this.mask = p.capacity - 1;
    this.ratio = p.sourceRate / sampleRate;
    this.fraction = 0;
    this.lastRead = Atomics.load(this.control, 0) >>> 0;
  }
  process(inputs, outputs) {
    const c = this.control, out = outputs[0];
    if (Atomics.load(c, 2)) return false;
    const start = Atomics.load(c, 0) >>> 0;
    let read = start;
    const write = Atomics.load(c, 1) >>> 0;
    if (read !== this.lastRead) this.fraction = 0; // waveOutReset
    let fraction = this.fraction, missing = 0, nonzero = 0;
    const gain = Atomics.load(c, 5) ? 0 :
      (Atomics.load(c, 3) / 128) * (Atomics.load(c, 4) / 65535);
    for (let i = 0; i < out[0].length; ++i) {
      const available = (write - read) >>> 0;
      if (!available || (fraction && available < 2) || available < Math.floor(fraction + this.ratio)) {
        // Output buffers start zeroed. Never repeat stale PCM on underrun.
        missing++;
        continue;
      }
      const offset = (read & this.mask) * 2;
      const next = ((read + 1) & this.mask) * 2;
      for (let channel = 0; channel < out.length; ++channel) {
        const a = this.pcm[offset + channel];
        const value = (fraction ? a + (this.pcm[next + channel] - a) * fraction : a) * gain;
        out[channel][i] = value;
        if (channel === 0 && value !== 0) nonzero++;
      }
      fraction += this.ratio;
      const consumed = Math.floor(fraction);
      read = (read + consumed) >>> 0;
      fraction -= consumed;
    }
    // Reset owns the cursor if it raced this render quantum.
    if ((Atomics.compareExchange(c, 0, start, read) >>> 0) === start) {
      this.fraction = fraction;
      this.lastRead = read;
    }
    Atomics.add(c, 6, 1); // callbacks
    Atomics.add(c, 7, missing); // output frames without PCM
    Atomics.add(c, 8, out[0].length); // rendered frames, including silence
    Atomics.add(c, 9, nonzero);
    return true;
  }
}
registerProcessor('titbit-pcm', TitbitPCM);

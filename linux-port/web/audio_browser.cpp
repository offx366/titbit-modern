// Audiere already decodes on a pthread. Feed its PCM directly to the browser's
// audio rendering thread: a busy game frame must not interrupt the audio clock.
#include "../platform/titbit_platform.h"
#include <emscripten.h>
#include <SDL.h>
#include <pthread.h>
#include <cstdlib>
#include <cstdint>

namespace {
constexpr unsigned capacity = 32768, control_words = 16;
enum Control { Read, Write, Closed, Volume, Master, Mute };
struct Ring { int32_t control[control_words]; float pcm[capacity * 2]; };
struct Pending { TBWaveHeader *header; uint32_t end; Pending *next; };
unsigned master_volume = 65535;
int master_mute;
uint32_t load(int32_t *p) { return __atomic_load_n(p, __ATOMIC_ACQUIRE); }
void store(int32_t *p, uint32_t v) { __atomic_store_n(p, v, __ATOMIC_RELEASE); }
}

struct TBAudio {
    Ring *ring;
    unsigned channels, bits;
    pthread_mutex_t mutex;
    Pending *first, *last;
};

EM_JS(int, start_audio, (Ring *ring, unsigned rate), {
    try {
        if (!globalThis.AudioWorkletNode || !crossOriginIsolated)
            throw new Error('AudioWorklet requires a cross-origin isolated page');
        const context = new AudioContext({sampleRate: rate, latencyHint: 'interactive'});
        const control = new Int32Array(HEAPU8.buffer, ring, 16);
        const audio = {context, control, node: null, ready: false, closed: false, error: null};
        Module.titbitAudio = audio;
        const events = ['mousedown', 'keydown', 'touchend'];
        const resume = () => {
            if (!Atomics.load(control, 2) && context.state === 'suspended')
                context.resume().catch(fail);
        };
        const fail = error => {
            if (audio.closed) return; // device probing can close before addModule resolves
            audio.error = String(error);
            if (Module.onAudioError) Module.onAudioError(error);
            else console.error(error);
        };
        events.forEach(event => document.addEventListener(event, resume, true));
        audio.close = () => {
            audio.closed = true;
            events.forEach(event => document.removeEventListener(event, resume, true));
            if (audio.node) audio.node.disconnect();
            // The worklet holds views into Wasm memory. Free only after its
            // context is closed, including when addModule is still pending.
            context.close().then(() => Module._free(ring)).catch(fail);
        };
        (Module.titbitAudioDevices ||= new Map()).set(ring, audio);
        audio.promise = context.audioWorklet.addModule('audio-worklet.js').then(() => {
            if (audio.closed) return;
            const node = new AudioWorkletNode(context, 'titbit-pcm', {
                numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [2],
                processorOptions: {buffer: control.buffer, offset: ring,
                    capacity: 32768, sourceRate: rate}
            });
            audio.node = node;
            node.onprocessorerror = () => fail(new Error('Audio processor failed'));
            node.connect(context.destination);
            audio.ready = true;
            resume();
        }).catch(fail);
        return 1;
    } catch (error) {
        console.error(error);
        return 0;
    }
});

EM_JS(void, close_audio, (Ring *ring), {
    const devices = Module.titbitAudioDevices;
    const audio = devices && devices.get(ring);
    if (audio) { devices.delete(ring); audio.close(); }
});

extern "C" {
void tb_web_audio_poll(void *device) {
    auto *a = static_cast<TBAudio *>(device);
    if (!a) return;
    pthread_mutex_lock(&a->mutex);
    const uint32_t read = load(&a->ring->control[Read]);
    while (a->first && int32_t(read - a->first->end) >= 0) {
        Pending *item = a->first;
        a->first = item->next;
        item->header->flags = (item->header->flags & ~TB_WAVE_INQUEUE) | TB_WAVE_DONE;
        std::free(item);
    }
    if (!a->first) a->last = nullptr;
    store(&a->ring->control[Master], __atomic_load_n(&master_volume, __ATOMIC_ACQUIRE));
    store(&a->ring->control[Mute], __atomic_load_n(&master_mute, __ATOMIC_ACQUIRE));
    pthread_mutex_unlock(&a->mutex);
}

TBAudio *tb_audio_open(unsigned rate, unsigned channels, unsigned bits) {
    if (!rate || (channels != 1 && channels != 2) || (bits != 8 && bits != 16)) {
        SDL_SetError("unsupported PCM format"); return nullptr;
    }
    auto *a = static_cast<TBAudio *>(std::calloc(1, sizeof(TBAudio)));
    if (!a) return nullptr;
    a->ring = static_cast<Ring *>(std::calloc(1, sizeof(Ring)));
    if (!a->ring) { std::free(a); return nullptr; }
    a->channels = channels; a->bits = bits;
    pthread_mutex_init(&a->mutex, nullptr);
    store(&a->ring->control[Volume], 128);
    store(&a->ring->control[Master], __atomic_load_n(&master_volume, __ATOMIC_ACQUIRE));
    store(&a->ring->control[Mute], __atomic_load_n(&master_mute, __ATOMIC_ACQUIRE));
    if (!start_audio(a->ring, rate)) {
        pthread_mutex_destroy(&a->mutex); std::free(a->ring); std::free(a);
        SDL_SetError("browser audio initialization failed"); return nullptr;
    }
    return a;
}

int tb_audio_queue(TBAudio *a, TBWaveHeader *header) {
    if (!a || !header || !header->data || header->flags & TB_WAVE_INQUEUE) return 0;
    const unsigned stride = a->channels * (a->bits / 8);
    if (header->length % stride) return 0;
    const unsigned frames = header->length / stride;
    auto *item = static_cast<Pending *>(std::calloc(1, sizeof(Pending)));
    if (!item) return 0;
    pthread_mutex_lock(&a->mutex);
    Ring *r = a->ring;
    uint32_t write = load(&r->control[Write]), read = load(&r->control[Read]);
    if (frames > capacity || write - read > capacity - frames) {
        pthread_mutex_unlock(&a->mutex); std::free(item); return 0;
    }
    const auto *bytes = reinterpret_cast<const uint8_t *>(header->data);
    for (unsigned frame = 0; frame < frames; ++frame) {
        for (unsigned channel = 0; channel < 2; ++channel) {
            unsigned source = (frame * a->channels + (a->channels == 1 ? 0 : channel)) * (a->bits / 8);
            float value;
            if (a->bits == 16) {
                int16_t sample = int16_t(unsigned(bytes[source]) | unsigned(bytes[source + 1]) << 8);
                value = float(sample) / 32768.0f;
            } else value = (int(bytes[source]) - 128) / 128.0f;
            r->pcm[((write + frame) & (capacity - 1)) * 2 + channel] = value;
        }
    }
    item->header = header; item->end = write + frames;
    header->flags = (header->flags & ~TB_WAVE_DONE) | TB_WAVE_PREPARED | TB_WAVE_INQUEUE;
    if (a->last) a->last->next = item; else a->first = item;
    a->last = item;
    // Publish samples only once the entire PCM block has been copied.
    store(&r->control[Write], write + frames);
    pthread_mutex_unlock(&a->mutex);
    return 1;
}

void tb_audio_reset(TBAudio *a) {
    if (!a) return;
    pthread_mutex_lock(&a->mutex);
    // A compareExchange in the consumer prevents an in-flight callback from
    // overwriting this cursor with an older value after waveOutReset.
    store(&a->ring->control[Read], load(&a->ring->control[Write]));
    while (a->first) {
        Pending *item = a->first; a->first = item->next;
        item->header->flags = (item->header->flags & ~TB_WAVE_INQUEUE) | TB_WAVE_DONE;
        std::free(item);
    }
    a->last = nullptr;
    pthread_mutex_unlock(&a->mutex);
}
void tb_audio_close(TBAudio *a) {
    if (!a) return;
    store(&a->ring->control[Closed], 1);
    tb_audio_reset(a);
    close_audio(a->ring);
    pthread_mutex_destroy(&a->mutex); std::free(a);
}
int tb_audio_volume(TBAudio *a, unsigned volume) {
    if (!a || volume > 128) return 0;
    store(&a->ring->control[Volume], volume); return 1;
}
int tb_audio_devices(void) { return 1; }
unsigned tb_audio_master_get(void) { return __atomic_load_n(&master_volume, __ATOMIC_ACQUIRE); }
int tb_audio_master_set(unsigned volume) {
    if (volume > 65535) return 0;
    __atomic_store_n(&master_volume, volume, __ATOMIC_RELEASE); return 1;
}
int tb_audio_mute_get(void) { return __atomic_load_n(&master_mute, __ATOMIC_ACQUIRE); }
int tb_audio_mute_set(int mute) { __atomic_store_n(&master_mute, !!mute, __ATOMIC_RELEASE); return 1; }
}

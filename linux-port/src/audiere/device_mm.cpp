#include <windows.h>
#include <mmsystem.h>
#include "device_mm.h"
#include "utility.h"


#ifdef TITBIT_WASM_SOURCE
extern "C" void tb_web_audio_poll(void* device);
#endif

namespace audiere {

  static const int RATE = 44100;


  MMAudioDevice*
  MMAudioDevice::create(const ParameterList& parameters) {
    WAVEFORMATEX wfx;
    memset(&wfx, 0, sizeof(wfx));
    wfx.wFormatTag      = WAVE_FORMAT_PCM;
    wfx.nChannels       = 2;
    wfx.nSamplesPerSec  = RATE;
    wfx.nAvgBytesPerSec = RATE * 4;
    wfx.nBlockAlign     = 4;
    wfx.wBitsPerSample  = 16;
    wfx.cbSize          = sizeof(WAVEFORMATEX);

    HWAVEOUT handle;
    MMRESULT result = waveOutOpen(&handle, WAVE_MAPPER, &wfx, 0, 0, 0);
    if (result != MMSYSERR_NOERROR) {
      return 0;
    }

    return new MMAudioDevice(handle, RATE);
  }


  MMAudioDevice::MMAudioDevice(HWAVEOUT device, int rate)
    : MixerDevice(rate)
  {
    ADR_GUARD("MMAudioDevice::MMAudioDevice");

    m_device = device;
    m_current_buffer = 0;

    // fill each buffer with samples and prepare it for output
    for (int i = 0; i < BUFFER_COUNT; ++i) {
      WAVEHDR& wh = m_buffers[i];
      memset(&wh, 0, sizeof(wh));
      wh.lpData         = (char*)m_samples + i * BUFFER_LENGTH;
      wh.dwBufferLength = BUFFER_LENGTH;

      read(BUFFER_LENGTH / 4, wh.lpData);

      MMRESULT result = waveOutPrepareHeader(m_device, &wh, sizeof(wh));
      if (result != MMSYSERR_NOERROR) {
        ADR_LOG("waveOutPrepareHeader failed");
      }

      result = waveOutWrite(m_device, &wh, sizeof(wh));
      if (result != MMSYSERR_NOERROR) {
        ADR_LOG("waveOutWrite failed");
      }
    }
  }


  MMAudioDevice::~MMAudioDevice() {
    waveOutReset(m_device);

    for (int i = 0; i < BUFFER_COUNT; ++i) {
      WAVEHDR& wh = m_buffers[i];
      if (wh.dwFlags & WHDR_PREPARED || wh.dwFlags & WHDR_DONE) {
        waveOutUnprepareHeader(m_device, &wh, sizeof(wh));
      }
    }

    waveOutClose(m_device);
  }


  void
  MMAudioDevice::update() {
#ifdef TITBIT_WASM_SOURCE
    // The worklet consumes PCM independently; acknowledge completed WinMM
    // headers here, on the existing decoder worker, rather than the UI thread.
    tb_web_audio_poll(m_device);
#endif
    // if a buffer is done playing, add it to the queue again
    for (int n = 0; n < BUFFER_COUNT; ++n) {
#ifdef TITBIT_WASM_SOURCE
      // Several headers can finish while a decoder operation holds the mixer
      // lock. Refill in playback order even when the array index wraps.
      int i = m_current_buffer;
#else
      int i = n;
#endif
      WAVEHDR& wh = m_buffers[i];
      if (wh.dwFlags & WHDR_DONE) {

        // unprepare
        MMRESULT result = waveOutUnprepareHeader(m_device, &wh, sizeof(wh));
        if (result != MMSYSERR_NOERROR) {
          ADR_LOG("waveOutUnprepareHeader failed");
        }

        // fill with new samples
        read(BUFFER_LENGTH / 4, wh.lpData);
        wh.dwFlags = 0;

        // prepare
        result = waveOutPrepareHeader(m_device, &wh, sizeof(wh));
        if (result != MMSYSERR_NOERROR) {
          ADR_LOG("waveOutPrepareHeader failed");
        }

        // write
        result = waveOutWrite(m_device, &wh, sizeof(wh));
        if (result != MMSYSERR_NOERROR) {
          ADR_LOG("waveOutWrite failed");
        }
#ifdef TITBIT_WASM_SOURCE
        m_current_buffer = (m_current_buffer + 1) % BUFFER_COUNT;
#endif
      }
#ifdef TITBIT_WASM_SOURCE
      else break;
#endif
    }
    Sleep(10);
  }

}

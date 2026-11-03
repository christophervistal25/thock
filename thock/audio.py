"""Low-latency callback mixer. All samples live in memory; the callback only adds arrays."""
import collections, os, threading, time
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 128          # 2.7 ms per callback
MAX_VOICES = 48


class Mixer:
    def __init__(self, device=None):
        self._pending = collections.deque()
        self._voices = []          # [data, pos, gl, gr, t_trigger]
        self.last_start_delay = None   # seconds from trigger to first mixed block (for latency test)
        self._stream = None
        self.device = device
        self.stats = {"callbacks": 0, "underflows": 0, "limited_blocks": 0, "max_voices": 0}
        self._lim = 1.0

    def start(self):
        kwargs = dict(samplerate=SR, channels=2, dtype="float32", blocksize=BLOCK,
                      latency="low", callback=self._cb)
        dev = self.device
        if dev is None:
            names = [d["name"] for d in sd.query_devices()]
            for cand in ("pipewire", "pulse", "default"):
                if cand in names:
                    dev = cand
                    break
        if dev is not None:
            kwargs["device"] = dev
        self._stream = sd.OutputStream(**kwargs)
        self._stream.start()

    @property
    def output_latency(self):
        return self._stream.latency if self._stream else None

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def play(self, data, gain=1.0, pan=0.5):
        """Queue a mono float32 sample. pan 0=left 1=right (constant power)."""
        if data is None or gain <= 0:
            return
        a = pan * np.pi / 2
        self._pending.append([data, 0, gain * np.cos(a), gain * np.sin(a), time.perf_counter()])

    def _cb(self, out, frames, time_info, status):
        if status.output_underflow:
            self.stats["underflows"] += 1
        self.stats["callbacks"] += 1
        pend = self._pending
        voices = self._voices
        if not voices and not pend:
            out.fill(0)
            return
        while pend:
            v = pend.popleft()
            self.last_start_delay = time.perf_counter() - v[4]
            voices.append(v)
        if len(voices) > MAX_VOICES:
            del voices[: len(voices) - MAX_VOICES]
        out.fill(0)
        L = out[:, 0]
        R = out[:, 1]
        if len(voices) > self.stats["max_voices"]:
            self.stats["max_voices"] = len(voices)
        alive = []
        for v in voices:
            data, pos = v[0], v[1]
            chunk = data[pos: pos + frames]
            n = len(chunk)
            L[:n] += chunk * v[2]
            R[:n] += chunk * v[3]
            v[1] = pos + n
            if v[1] < len(data):
                alive.append(v)
        self._voices[:] = alive
        # peak limiter: instant attack, ~50 ms release, then a hard safety clip
        pk = float(np.abs(out).max())
        target = 0.95 / pk if pk > 0.95 else 1.0
        if target < self._lim:
            self._lim = target
            self.stats["limited_blocks"] += 1
            out *= target
        elif self._lim < 1.0:
            g0 = self._lim
            self._lim = min(1.0, target, g0 + frames / (SR * 0.05))
            out *= np.linspace(g0, self._lim, frames, dtype=np.float32)[:, None]
        np.clip(out, -1.0, 1.0, out=out)

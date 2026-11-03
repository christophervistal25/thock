import json, os, wave
import numpy as np

SR = 48000
PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs")


def _read_wav(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("expected mono 16-bit wav: " + path)
        if w.getframerate() != SR:
            raise ValueError("expected 48 kHz wav: " + path)
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767.0


def list_packs():
    out = []
    for pid in sorted(os.listdir(PACKS_DIR)):
        pj = os.path.join(PACKS_DIR, pid, "pack.json")
        if pid.startswith("_") or not os.path.isfile(pj):
            continue
        with open(pj) as f:
            meta = json.load(f)
        out.append({"id": pid, "name": meta.get("name", pid), "description": meta.get("description", "")})
    return sorted(out, key=lambda p: p["name"].lower())


def tilt(y, tone):
    """Tilt EQ: tone<0 boosts lows / cuts highs (thock); tone>0 the opposite (clack). Loudness matched."""
    if abs(tone) < 1e-3 or len(y) == 0:
        return y
    n = len(y)
    N = 1 << int(np.ceil(np.log2(n + 4096)))
    Y = np.fft.rfft(y.astype(np.float64), N)
    f = np.fft.rfftfreq(N, 1.0 / SR)
    gdb = np.clip(tone * 4.5 * np.log2(np.maximum(f, 40.0) / 1500.0), -13, 13)
    z = np.fft.irfft(Y * 10 ** (gdb / 20.0), N)[:n]
    # short fade so the zero-phase filter cannot leave a click at the end
    fo = min(256, n // 4)
    if fo:
        z[-fo:] *= np.linspace(1, 0, fo)
    r0 = np.sqrt(np.mean(y.astype(np.float64) ** 2)) + 1e-12
    r1 = np.sqrt(np.mean(z ** 2)) + 1e-12
    z *= r0 / r1
    pk = np.abs(z).max()
    if pk > 0.98:
        z *= 0.98 / pk
    return z.astype(np.float32)


class Pack:
    """A loaded, tone-rendered sound pack held entirely in memory."""

    def __init__(self, pid, tone=0.0):
        self.id = pid
        base = os.path.join(PACKS_DIR, pid)
        with open(os.path.join(base, "pack.json")) as f:
            meta = json.load(f)
        self.name = meta.get("name", pid)
        cache = {}

        def get(fn):
            if fn is None:
                return None
            if fn not in cache:
                cache[fn] = tilt(_read_wav(os.path.join(base, fn)), tone)
            return cache[fn]

        self.default = [(get(e["down"]), get(e.get("up"))) for e in meta.get("default", [])]
        self.keys = {int(k): (get(e["down"]), get(e.get("up"))) for k, e in meta.get("keys", {}).items()}
        mdir = os.path.join(PACKS_DIR, "_mouse")
        md = os.path.join(mdir, "down.wav")
        mu = os.path.join(mdir, "up.wav")
        self.mouse = (tilt(_read_wav(md), tone) if os.path.exists(md) else None,
                      tilt(_read_wav(mu), tone) if os.path.exists(mu) else None)

    def pick(self, code, rng):
        s = self.keys.get(code)
        if s is not None:
            return s
        if self.default:
            return self.default[rng.integers(len(self.default))]
        return (None, None)

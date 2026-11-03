"""Build lightweight web copies of the sound packs for the landing page typing test.

Each pack becomes one 32 kHz mono 16-bit WAV "sprite" (all samples back to back with short
silent gaps) plus an entry in docs/assets/packs/packs.json listing where each sample starts and
how long it is. WAV keeps decoding instant and sample-accurate in every browser (no codec priming).

    .venv/bin/python tools/build_web_packs.py
"""
import json, os, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from thock.packs import PACKS_DIR, SR, _read_wav, list_packs  # noqa: E402

OUT = os.path.join(ROOT, "docs", "assets", "packs")
WEB_SR = 32000
GAP = int(0.01 * WEB_SR)
WEB_KEYS = set(range(1, 59))       # typing block only: Esc .. Caps Lock (keeps Buckling Spring small)


def resample(y):
    n = len(y)
    m = int(round(n * WEB_SR / SR))
    Y = np.fft.rfft(y.astype(np.float64))
    Z = Y[: m // 2 + 1]
    z = np.fft.irfft(Z, m) * (m / n)
    fo = min(64, m // 4)
    if fo:
        z[-fo:] *= np.linspace(1, 0, fo)
    return z


class Sprite:
    def __init__(self):
        self.parts, self.pos, self.index = [], 0, {}

    def add(self, path):
        if path in self.index:
            return self.index[path]
        z = resample(_read_wav(path))
        ref = [round(self.pos / WEB_SR, 5), round(len(z) / WEB_SR, 5)]
        self.parts += [z, np.zeros(GAP)]
        self.pos += len(z) + GAP
        self.index[path] = ref
        return ref

    def write(self, fn):
        y = np.concatenate(self.parts) if self.parts else np.zeros(1)
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
        with wave.open(fn, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(WEB_SR); w.writeframes(pcm.tobytes())
        return os.path.getsize(fn)


def pair(sp, base, e):
    up = e.get("up")
    return [sp.add(os.path.join(base, e["down"])), sp.add(os.path.join(base, up)) if up else None]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = {"sampleRate": WEB_SR, "packs": [], "mouse": None}
    total = 0
    for p in list_packs():
        if p["private"]:            # personal packs stay on this machine, never on the website
            continue
        base = os.path.join(PACKS_DIR, p["id"])
        meta = json.load(open(os.path.join(base, "pack.json")))
        sp = Sprite()
        entry = {"id": p["id"], "name": p["name"], "description": p["description"], "file": p["id"] + ".wav",
                 "default": [pair(sp, base, e) for e in meta.get("default", [])],
                 "keys": {k: pair(sp, base, e) for k, e in meta.get("keys", {}).items() if int(k) in WEB_KEYS}}
        size = sp.write(os.path.join(OUT, entry["file"]))
        entry["bytes"] = size
        total += size
        index["packs"].append(entry)
        print(f"{p['id']:14s} {size / 1024:7.0f} KB")
    sp = Sprite()
    md = os.path.join(PACKS_DIR, "_mouse")
    index["mouse"] = {"file": "mouse.wav", "down": sp.add(os.path.join(md, "down.wav")), "up": sp.add(os.path.join(md, "up.wav"))}
    total += sp.write(os.path.join(OUT, "mouse.wav"))
    with open(os.path.join(OUT, "packs.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print(f"total {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()

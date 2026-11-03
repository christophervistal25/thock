"""Build the calm packs (deep, muffled, soft-attack recordings) from CC0 Freesound typing recordings.

    .venv/bin/python tools/build_calm_packs.py [SOURCE_DIR]

SOURCE_DIR holds the Freesound HQ previews named <sound id>.mp3. Missing files are downloaded from
the Freesound CDN (same recording and license as the original upload). Needs ffmpeg.
Output goes straight into packs/<id>/ (old files of these packs are replaced).
Sources and licenses: SOUNDS-LICENSES.md.

Each recording is continuous typing, so individual keystrokes are sliced out (tools/slicer.py):
the loud, clean, spectrally typical strokes become presses, quieter ones become releases. Strokes
that sound unlike the rest (mic bumps, spacebar, double hits) are left out by keeping the slices
closest to the recording's median spectral centroid.
"""
import json, os, shutil, subprocess, sys, urllib.request, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_argv = list(sys.argv)
from slicer import slice_dense, transients  # noqa: E402  (slicer resets sys.argv)
sys.argv = _argv

SR = 48000
PACKS = os.path.join(ROOT, "packs")
TARGET = 0.5                      # peak level of a typical press, same as tools/build_packs.py
SPACE, ENTER, BKSP = 57, 28, 14

# id: (freesound sound id, preview path on cdn.freesound.org, ffmpeg cleanup filter, max "clean" ratio, pack.json meta)
# "clean" = loudest sound in the 40 ms before a stroke / the stroke's peak (tools/slicer.py). Fast typing
# over a noisier floor (Thocky) needs a looser limit to find enough strokes.
SOURCES = {
    "thocky": (869165, "869/869165_19216797-hq.mp3",
               "highpass=f=60,afftdn=nr=15:nf=-50", 0.3,
               {"name": "Thocky", "description": "Deep, muffled thock with a soft, rounded bottom-out. The calmest pack"}),
    "rainy-75": (815614, "815/815614_15899953-hq.mp3",
                 "highpass=f=55:poles=2,afftdn=nr=12:nf=-55", 0.15,
                 {"name": "Rainy 75", "description": "Rainy 75 aluminium board: deep, rounded, marbly thock"}),
    "lubed-tactile": (709460, "709/709460_13652097-hq.mp3",
                      "highpass=f=50,afftdn=nr=10:nf=-60", 0.15,
                      {"name": "Lubed Tactile", "description": "ikki68 Aurora, hand-lubed WS Brown: warm, smooth tactile bump"}),
}


def fetch(src_dir, sid, preview):
    path = os.path.join(src_dir, f"{sid}.mp3")
    if not os.path.exists(path):
        os.makedirs(src_dir, exist_ok=True)
        url = "https://cdn.freesound.org/previews/" + preview
        print("download", url)
        urllib.request.urlretrieve(url, path)
    return path


def load(path, af):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", af, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def env(x, ms=2):
    w = max(1, int(ms * SR / 1000))
    return np.sqrt(np.convolve(x ** 2, np.ones(w) / w, "same")) + 1e-9


def finish(x, maxms=260):
    """Trim to the stroke (1.5 ms pre-roll, tail until it sinks into the floor) and fade both ends.
    Same rules as tools/build_packs.py so every pack is cut the same way."""
    e = env(x); pk = e.max(); floor = np.percentile(e, 10)
    i0 = int(np.argmax(e > pk * 0.2)); i0 = max(0, i0 - int(0.0015 * SR))
    p = int(np.argmax(e))
    thr = max(floor * 1.6, pk * 0.012)
    tail = np.where(e[p:] > thr)[0]
    i1 = p + (tail[-1] if len(tail) else 0) + int(0.004 * SR)
    i1 = min(len(x), i1, i0 + int(maxms * SR / 1000))
    y = x[i0:i1].copy(); n = len(y)
    fi = min(int(0.0005 * SR), n); y[:fi] *= np.linspace(0, 1, fi)
    fo = min(int(0.012 * SR), n // 2); y[-fo:] *= np.linspace(1, 0, fo) ** 2
    return y


def resamp(y, f):
    """Pitch/time scale by factor f (f<1 = lower and longer), used for space/enter variants."""
    n = int(len(y) / f)
    return np.interp(np.arange(n) * f, np.arange(len(y)), y)


def centroid(y):
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / SR)
    return float((Y * f).sum() / (Y.sum() + 1e-18))


def tail_db(y):
    """Level of the 60-85 % stretch of a sample relative to its peak: high = noise or a second key in the tail."""
    n = len(y); t = y[int(n * 0.6):int(n * 0.85)]
    return 20 * np.log10(np.sqrt(np.mean(t ** 2)) / (np.abs(y).max() + 1e-12) + 1e-9)


def pick_strokes(x, max_clean, n_down=8, n_up=6, maxms=150, max_tail_db=-33):
    sl = [c for c in slice_dense(x, maxms) if c["clean"] < max_clean and c["len"] > 0.07]
    # drop strokes whose tail still carries noise or the next key
    sl = [c for c in sl if tail_db(finish(x[c["s"]:c["t"]], maxms)) < max_tail_db]
    if len(sl) < n_down + n_up:
        raise SystemExit(f"only {len(sl)} clean strokes found")
    pk = np.array([c["peak"] for c in sl])
    for c in sl:
        c["cent"] = centroid(x[c["s"]:c["t"]])
    loud = [c for c in sl if c["peak"] >= np.percentile(pk, 55)]
    med = np.median([c["cent"] for c in loud])
    # typical-sounding presses: closest to the median brightness, then the cleanest of those
    loud = sorted(loud, key=lambda c: abs(np.log(c["cent"] / med)))[: n_down * 3]
    downs = sorted(loud, key=lambda c: c["clean"])[:n_down]
    dmed = np.median([c["peak"] for c in downs])
    quiet = [c for c in sl if 0.18 * dmed <= c["peak"] <= 0.55 * dmed]
    ups = sorted(quiet, key=lambda c: c["clean"])[:n_up]
    D = [finish(x[c["s"]:c["t"]], maxms) for c in downs]
    U = [finish(x[c["s"]:c["t"]], 100) for c in ups]
    return [(d, U[i % len(U)] if U else None) for i, d in enumerate(D)]


def write(path, y, gain):
    y = np.clip(y * gain, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())


def save_pack(pid, meta, variants, special):
    out = os.path.join(PACKS, pid)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    g0 = TARGET / np.median([np.abs(d).max() for d, u in variants])
    pj = dict(meta); pj["default"] = []; pj["keys"] = {}

    def put(name, d, u, g):
        write(os.path.join(out, f"{name}-down.wav"), d, g)
        ent = {"down": f"{name}-down.wav"}
        if u is not None:
            write(os.path.join(out, f"{name}-up.wav"), u, g)
            ent["up"] = f"{name}-up.wav"
        return ent

    for i, (d, u) in enumerate(variants):
        # level-match each press to the target, but never lift a soft one more than 2x (keeps natural dynamics)
        g = min(TARGET * 0.95 / np.abs(d).max(), g0 * 2)
        pj["default"].append(put(f"v{i}", d, u, g))
    for code, (d, u) in special.items():
        pj["keys"][str(code)] = put(f"k{code}", d, u, TARGET * 1.05 / np.abs(d).max())
    with open(os.path.join(out, "pack.json"), "w") as f:
        json.dump(pj, f, indent=1)
    lens = [round(len(d) / SR * 1000) for d, u in variants]
    print(f"{pid:14s} {len(variants)} variants, press {min(lens)}-{max(lens)} ms, "
          f"{sum(u is not None for d, u in variants)} with release")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".sources")
    for pid, (sid, preview, af, max_clean, meta) in SOURCES.items():
        x = load(fetch(src, sid, preview), af)
        v = pick_strokes(x, max_clean)
        # bigger keys: the same strokes a little lower and longer, as in the other packs
        special = {SPACE: (finish(resamp(v[0][0], 0.86)), v[0][1]),
                   ENTER: (finish(resamp(v[1][0], 0.92)), v[1][1]),
                   BKSP: (finish(resamp(v[2][0], 0.94)), v[2][1])}
        save_pack(pid, meta, v, special)


if __name__ == "__main__":
    main()

"""Convert the keyboard sound packs bundled with Mechvibes (MIT license) into Thock packs.

    git clone --depth 1 https://github.com/hainguyents13/mechvibes /path/to/mechvibes
    .venv/bin/python tools/build_mechvibes_packs.py /path/to/mechvibes

Each Mechvibes pack is one audio file plus a config.json that gives every key (named like
KeyboardEvent.code: "KeyA", "Space", ...) a press segment and a release segment in milliseconds.
Thock keeps 10 letter keys as random variants for normal typing and the keys that sound different
(Space, Enter, Backspace, Tab, Shift, Caps Lock) under their Linux evdev key codes.
Packs are written to packs/mv-<name>/ (replaced each run) with a copy of the Mechvibes MIT license.
Needs ffmpeg. Sources and license: SOUNDS-LICENSES.md.
"""
import json, os, shutil, subprocess, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
TARGET = 0.5                     # peak of a typical press, same as the other packs

# Mechvibes folder -> (Thock pack id, name, description)
PACKS = {
    "cherrymx-black-abs": ("mv-cherry-black-abs", "Cherry MX Black (ABS)", "Heavy linear, ABS keycaps: deep, smooth, even"),
    "cherrymx-black-pbt": ("mv-cherry-black-pbt", "Cherry MX Black (PBT)", "Heavy linear, PBT keycaps: deeper and drier than ABS"),
    "cherrymx-red-abs": ("mv-cherry-red-abs", "Cherry MX Red (ABS)", "Light linear, ABS keycaps: soft, quick, smooth"),
    "cherrymx-brown-abs": ("mv-cherry-brown-abs", "Cherry MX Brown (ABS)", "Light tactile, ABS keycaps: gentle bump, bright top"),
    "cherrymx-brown-pbt": ("mv-cherry-brown-pbt", "Cherry MX Brown (PBT)", "Light tactile, PBT keycaps: gentle bump, rounder sound"),
    "cherrymx-blue-abs": ("mv-cherry-blue-abs", "Cherry MX Blue (ABS)", "Clicky, ABS keycaps: crisp click on every press"),
    "cherrymx-blue-pbt": ("mv-cherry-blue-pbt", "Cherry MX Blue (PBT)", "Clicky, PBT keycaps: crisp click, a little fuller"),
    "eg-oreo": ("mv-eg-oreo", "Everglide Oreo", "Linear: smooth, muted, rounded"),
    "eg-crystal-purple": ("mv-eg-crystal-purple", "Everglide Crystal Purple", "Tactile: clear bump with a crisp top"),
    "topre-purple-hybrid-pbt": ("mv-topre-purple-hybrid", "Topre Purple Hybrid (PBT)", "Topre domes, PBT keycaps: cushioned, muted thock"),
}

# KeyboardEvent.code -> Linux evdev key code (what Thock's packs are keyed by)
SPECIAL = {"Space": 57, "Enter": 28, "Backspace": 14, "Tab": 15, "ShiftLeft": 42, "ShiftRight": 54, "CapsLock": 58}
VARIANTS = ["KeyA", "KeyS", "KeyD", "KeyF", "KeyJ", "KeyK", "KeyL", "KeyE", "KeyR", "KeyI"]


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def cut(audio, start_ms, end_ms):
    """Slice one segment; short fades at both ends so cuts never click."""
    y = audio[int(start_ms * SR / 1000): int(end_ms * SR / 1000)].copy()
    if len(y) < 32:
        return None
    # segments often start with up to ~30 ms of silence: drop it (keep 1 ms) so the sound lands on the keystroke
    i0 = int(np.argmax(np.abs(y) > np.abs(y).max() * 0.05))
    y = y[max(0, i0 - int(0.001 * SR)):]
    if len(y) < 32:
        return None
    fi, fo = min(48, len(y) // 8), min(int(0.004 * SR), len(y) // 4)
    y[:fi] *= np.linspace(0, 1, fi)
    y[-fo:] *= np.linspace(1, 0, fo) ** 2
    return y


def write(path, y):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


def convert(src_dir, license_text, pid, name, desc):
    cfg = json.load(open(os.path.join(src_dir, "config.json")))
    defs = cfg.get("definitions") or cfg.get("defs")
    audio = decode(os.path.join(src_dir, cfg["audio_file"]))

    def pair(code):
        t = defs.get(code, {}).get("timing", [])
        if not t or len(t) > 2:
            return None
        down = cut(audio, *t[0])
        up = cut(audio, *t[1]) if len(t) == 2 else None
        return (down, up) if down is not None else None

    variants = [p for p in (pair(k) for k in VARIANTS) if p]
    special = {code: p for k, code in SPECIAL.items() if (p := pair(k))}
    if not variants:
        raise SystemExit(f"{src_dir}: no usable key definitions")
    gain = TARGET / np.median([np.abs(d).max() for d, u in variants])   # one gain: keeps the pack's own balance

    out = os.path.join(ROOT, "packs", pid)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    meta = {"name": name, "description": desc + " (from Mechvibes)", "default": [], "keys": {}}

    def put(tag, d, u):
        g = min(gain, 0.95 / max(np.abs(d).max(), 1e-9))
        write(os.path.join(out, f"{tag}-down.wav"), d * g)
        ent = {"down": f"{tag}-down.wav"}
        if u is not None:
            write(os.path.join(out, f"{tag}-up.wav"), u * g)
            ent["up"] = f"{tag}-up.wav"
        return ent

    for i, (d, u) in enumerate(variants):
        meta["default"].append(put(f"v{i}", d, u))
    for code, (d, u) in special.items():
        meta["keys"][str(code)] = put(f"k{code}", d, u)
    with open(os.path.join(out, "pack.json"), "w") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(out, "LICENSE-MIT.txt"), "w") as f:
        f.write(license_text)
    print(f"{pid:24s} {len(variants)} variants, {len(special)} special keys")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    repo = sys.argv[1]
    license_text = open(os.path.join(repo, "LICENSE")).read()
    for folder, (pid, name, desc) in PACKS.items():
        convert(os.path.join(repo, "soundpacks", "keyboard", folder), license_text, pid, name, desc)


if __name__ == "__main__":
    main()

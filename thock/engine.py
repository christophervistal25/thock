"""Turns input events into sounds. Holds no history of keys: only which keys are currently held,
so a held key does not machine-gun, and which release sample belongs to a press."""
import threading
import time
import numpy as np

from .audio import Mixer
from .keymap import key_x
from .packs import Pack

MOUSE_PAN = 0.78
REPEAT_GAIN = 0.85          # repeats a little softer than the first press
REPEAT_MIN_INTERVAL = 0.025  # never more than 40 repeat sounds per second per key
MOUSE_PITCH = {1: 1.0, 2: 0.93, 3: 1.07}


class Engine:
    def __init__(self, config):
        self.cfg = config
        self.rng = np.random.default_rng()
        self.mixer = Mixer()
        self.pack = None
        self._held = {}            # keycode -> [down sample, release sample, last sound time] (cleared on release)
        self._held_buttons = set()
        self._lock = threading.Lock()
        self._loading = threading.Lock()
        self.load_pack(self.cfg["pack"], self.cfg["tone"], sync=True)
        config.on_change(self._on_cfg)

    def start(self):
        self.mixer.start()

    def stop(self):
        self.mixer.stop()

    # ---- packs / tone -------------------------------------------------
    def load_pack(self, pid, tone, sync=False):
        def work():
            with self._loading:
                try:
                    p = Pack(pid, tone)
                except Exception:
                    p = Pack("tactile-brown", tone)
                self.pack = p
        if sync:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def _on_cfg(self, key, value, source):
        if key in ("pack", "tone"):
            self.load_pack(self.cfg["pack"], self.cfg["tone"])

    # ---- playback -----------------------------------------------------
    def _gain(self):
        v = self.cfg["volume"]
        return 1.4 * v ** 1.6

    def _vary(self, data, gain, pitch=1.0):
        if self.cfg["pitch_variation"]:
            pitch *= 1.0 + self.rng.uniform(-0.03, 0.03)
            gain *= 1.0 + self.rng.uniform(-0.08, 0.08)
        if abs(pitch - 1.0) > 1e-4:
            n = int(len(data) / pitch)
            data = np.interp(np.arange(n, dtype=np.float32) * pitch, np.arange(len(data), dtype=np.float32), data).astype(np.float32)
        return data, gain

    def _pan(self, x):
        return x if self.cfg["spatial"] else 0.5

    def key_down(self, code):
        if not self.cfg["enabled"] or self.pack is None:
            return
        now = time.monotonic()
        gain = self._gain()
        with self._lock:
            held = self._held.get(code)
            if held is not None:
                # X auto-repeat: KeyPress again without a KeyRelease
                if not self.cfg["repeat"] or held[0] is None or now - held[2] < REPEAT_MIN_INTERVAL:
                    return
                held[2] = now
                down = held[0]
                gain *= REPEAT_GAIN
            else:
                down, up = self.pack.pick(code, self.rng)
                self._held[code] = [down, up, now]
        if down is not None:
            d, g = self._vary(down, gain)
            self.mixer.play(d, g, self._pan(key_x(code)))

    def key_up(self, code):
        with self._lock:
            held = self._held.pop(code, None)
        up = held[1] if held else None
        if up is None or not self.cfg["enabled"] or not self.cfg["release"]:
            return
        d, g = self._vary(up, self._gain())
        self.mixer.play(d, g, self._pan(key_x(code)))

    def button(self, button, pressed):
        if button not in MOUSE_PITCH:
            return
        if pressed:
            if button in self._held_buttons:
                return
            self._held_buttons.add(button)
        else:
            if button not in self._held_buttons:
                return
            self._held_buttons.discard(button)
        if not self.cfg["enabled"] or not self.cfg["mouse"] or self.pack is None:
            return
        s = self.pack.mouse[0 if pressed else 1]
        if s is None:
            return
        d, g = self._vary(s, self._gain() * 0.9, MOUSE_PITCH[button])
        self.mixer.play(d, g, self._pan(MOUSE_PAN))

    def preview(self, pid=None):
        """Play a short demo phrase with the given pack (used by 'Try' buttons and self-test)."""
        import time
        pack = self.pack if pid is None or (self.pack and self.pack.id == pid) else Pack(pid, self.cfg["tone"])
        seq = [30, 31, 32, 33, 57, 36, 37, 38, 14, 28]
        def run():
            for c in seq:
                down, up = pack.pick(c, self.rng)
                x = self._pan(key_x(c))
                if down is not None:
                    d, g = self._vary(down, self._gain())
                    self.mixer.play(d, g, x)
                time.sleep(0.07)
                if up is not None and self.cfg["release"]:
                    d, g = self._vary(up, self._gain())
                    self.mixer.play(d, g, x)
                time.sleep(0.09)
        threading.Thread(target=run, daemon=True).start()

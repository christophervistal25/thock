"""Engine behaviour tests (no audio device, no X needed): run with  .venv/bin/python -m unittest -v"""
import os, tempfile, unittest
from unittest import mock

import numpy as np

from thock import config as cfgmod
from thock.config import Config


class FakeMixer:
    def __init__(self, *a, **k):
        self.plays = []
    def start(self): pass
    def stop(self): pass
    def play(self, data, gain=1.0, pan=0.5):
        self.plays.append((len(data), gain, pan))


def make_engine(**over):
    from thock import engine as engmod
    d = tempfile.mkdtemp()
    c = Config(os.path.join(d, "config.json"))
    c.data.update({"pitch_variation": False, "volume": 0.6, "pack": "tactile-brown"}, **over)
    with mock.patch.object(engmod, "Mixer", FakeMixer):
        e = engmod.Engine(c)
    return e, c


class RepeatTests(unittest.TestCase):
    def test_default_off_and_persisted(self):
        self.assertIs(cfgmod.DEFAULTS["repeat"], False)
        d = tempfile.mkdtemp(); p = os.path.join(d, "config.json")
        c = Config(p); c.set("repeat", True)
        self.assertTrue(Config(p)["repeat"])

    def test_repeat_off_plays_once(self):
        e, c = make_engine()
        for _ in range(20):
            e.key_down(30)
        e.key_up(30)
        self.assertEqual(len(e.mixer.plays), 2)          # one down, one up

    def test_repeat_on_plays_each_repeat_softer(self):
        e, c = make_engine(repeat=True)
        t = [100.0]
        with mock.patch("thock.engine.time.monotonic", side_effect=lambda: t[0]):
            e.key_down(30)
            for _ in range(30):                           # 30 repeats at 33 ms
                t[0] += 0.033
                e.key_down(30)
            e.key_up(30)
            e.key_up(30)                                  # stray second release: nothing
        plays = e.mixer.plays
        self.assertEqual(len(plays), 1 + 30 + 1)
        first, reps, up = plays[0], plays[1:31], plays[31]
        self.assertTrue(all(abs(r[1] - first[1] * 0.85) < 1e-6 for r in reps))
        self.assertTrue(all(r[0] == first[0] and r[2] == first[2] for r in reps))   # same sample + pan

    def test_repeat_rate_capped(self):
        e, c = make_engine(repeat=True)
        t = [5.0]
        with mock.patch("thock.engine.time.monotonic", side_effect=lambda: t[0]):
            e.key_down(30)
            for _ in range(100):                          # absurd 200/s repeat rate
                t[0] += 0.005
                e.key_down(30)
        self.assertLessEqual(len(e.mixer.plays), 1 + 100 * 0.005 / 0.025 + 1)


class MixerTests(unittest.TestCase):
    def test_dense_repeats_no_clip_no_backlog(self):
        from thock.audio import Mixer, BLOCK
        m = Mixer()
        sample = (np.sin(np.arange(4800) / 3.0) * 0.9).astype(np.float32)
        out = np.zeros((BLOCK, 2), np.float32)
        status = mock.Mock(output_underflow=False)
        peaks = []
        for i in range(48000 * 2 // BLOCK):                 # 2 s of audio
            if i % 12 == 0:                                  # a new voice every 32 ms (~31/s)
                m.play(sample, 1.0, 0.5)
            m._cb(out, BLOCK, None, status)
            peaks.append(np.abs(out).max())
        self.assertLessEqual(max(peaks), 1.0)
        self.assertLessEqual(m.stats["max_voices"], 4)       # voices finish, nothing piles up
        self.assertEqual(len(m._pending), 0)


class PackTests(unittest.TestCase):
    """Pack loading from a throwaway packs folder (no real packs touched)."""

    def _make_pack(self, root, pid, meta, files):
        import json, wave
        d = os.path.join(root, pid)
        os.makedirs(d)
        for fn, n in files.items():
            with wave.open(os.path.join(d, fn), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes((np.ones(n) * 1000).astype("<i2").tobytes())
        with open(os.path.join(d, "pack.json"), "w") as f:
            json.dump(meta, f)

    def _packs_dir(self):
        root = tempfile.mkdtemp()
        self._make_pack(root, "_mouse", {}, {"down.wav": 100, "up.wav": 110})
        self._make_pack(root, "shared", {"name": "Shared", "default": [{"down": "d.wav"}]}, {"d.wav": 200})
        self._make_pack(root, "own", {"name": "Own", "private": True, "default": [{"down": "d.wav"}],
                                      "mouse": {"down": "md.wav", "up": "mu.wav"}},
                        {"d.wav": 200, "md.wav": 300, "mu.wav": 310})
        return root

    def test_pack_uses_own_mouse_clicks_else_shared(self):
        from thock import packs
        with mock.patch.object(packs, "PACKS_DIR", self._packs_dir()):
            self.assertEqual([len(s) for s in packs.Pack("shared").mouse], [100, 110])
            self.assertEqual([len(s) for s in packs.Pack("own").mouse], [300, 310])

    def test_private_flag_listed(self):
        from thock import packs
        with mock.patch.object(packs, "PACKS_DIR", self._packs_dir()):
            flags = {p["id"]: p["private"] for p in packs.list_packs()}
        self.assertEqual(flags, {"own": True, "shared": False})


if __name__ == "__main__":
    unittest.main()

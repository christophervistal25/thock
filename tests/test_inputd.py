"""Wayland input path tests (no evdev, root or running service needed): run with  .venv/bin/python -m unittest -v"""
import importlib.util
import os
import socket
import struct
import tempfile
import unittest

from thock import inputd as client
from thock import listener

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("thock_inputd_helper", os.path.join(ROOT, "helper", "thock-inputd.py"))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

LETTERS_DIGITS = list(range(2, 14)) + list(range(16, 28)) + list(range(30, 42)) + list(range(43, 54))


class BackendTests(unittest.TestCase):
    def test_x11_session_uses_x_record(self):
        self.assertEqual(listener.backend({"XDG_SESSION_TYPE": "x11"}), "x11")

    def test_unknown_session_uses_x_record(self):
        self.assertEqual(listener.backend({}), "x11")

    def test_wayland_session_uses_inputd(self):
        self.assertEqual(listener.backend({"XDG_SESSION_TYPE": "wayland"}), "inputd")

    def test_override(self):
        self.assertEqual(listener.backend({"XDG_SESSION_TYPE": "wayland", "THOCK_INPUT": "x11"}), "x11")
        self.assertEqual(listener.backend({"XDG_SESSION_TYPE": "x11", "THOCK_INPUT": "inputd"}), "inputd")

    def test_bad_override_is_ignored(self):
        self.assertEqual(listener.backend({"XDG_SESSION_TYPE": "wayland", "THOCK_INPUT": "evdev"}), "inputd")

    def test_wayland_listener_has_the_same_interface(self):
        lis = listener.make_listener(print, print, print, environ={"XDG_SESSION_TYPE": "wayland"})
        self.assertIsInstance(lis, client.InputdListener)
        self.assertTrue(callable(lis.start) and callable(lis.stop))


class CoarseTests(unittest.TestCase):
    def test_every_text_key_is_in_a_zone(self):
        for code in LETTERS_DIGITS:
            self.assertIn(code, helper.ZONE_OF, code)

    def test_zones_do_not_overlap(self):
        flat = [c for z in helper.ZONES for c in z]
        self.assertEqual(len(flat), len(set(flat)))

    def test_special_keys_stay_exact(self):
        c = helper.Coarsener()
        for code in (1, 14, 15, 28, 29, 42, 54, 56, 57, 58, 97, 100, 103, 125):
            self.assertEqual(c(code, 1), code)

    def test_single_key_maps_to_zone_head(self):
        c = helper.Coarsener()
        for z in helper.ZONES:
            for code in z:
                self.assertEqual(c(code, 1), z[0])
                self.assertEqual(c(code, 0), z[0])

    def test_rollover_in_one_zone_keeps_pairs_apart(self):
        c = helper.Coarsener()
        a, s = c(30, 1), c(31, 1)        # A down, S down (same zone)
        self.assertNotEqual(a, s)
        self.assertEqual(c(30, 2), a)    # A auto-repeat keeps its code
        self.assertEqual(c(30, 0), a)    # A up
        self.assertEqual(c(31, 0), s)    # S up
        self.assertEqual(c.sent, {})

    def test_sent_code_does_not_depend_on_which_key(self):
        for code in helper.ZONES[2]:
            c = helper.Coarsener()
            self.assertEqual(c(code, 1), helper.ZONES[2][0])


class ConfTests(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf")
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_defaults_to_coarse(self):
        self.assertEqual(helper.read_conf(self._write("user = alice\n")), ("alice", "coarse"))

    def test_rejects_unknown_detail(self):
        with self.assertRaises(SystemExit):
            helper.read_conf(self._write("user = alice\ndetail = everything\n"))

    def test_requires_user(self):
        with self.assertRaises(SystemExit):
            helper.read_conf(self._write("detail = exact\n"))


class GateTests(unittest.TestCase):
    def test_unlocked_active_is_open(self):
        self.assertTrue(helper.SessionGate.decide("4", {"Active": "yes", "LockedHint": "no"})[0])

    def test_locked_is_muted(self):
        self.assertFalse(helper.SessionGate.decide("4", {"Active": "yes", "LockedHint": "yes"})[0])

    def test_inactive_is_muted(self):
        self.assertFalse(helper.SessionGate.decide("4", {"Active": "no", "LockedHint": "no"})[0])

    def test_missing_answers_fail_closed(self):
        self.assertFalse(helper.SessionGate.decide("4", {})[0])
        self.assertFalse(helper.SessionGate.decide("4", {"Active": "yes"})[0])

    def test_logind_error_fails_closed(self):
        g = helper.SessionGate("nobody-here")
        g._loginctl = lambda *a: (_ for _ in ()).throw(RuntimeError("Transport endpoint is not connected"))
        state, reason = g.state()
        self.assertFalse(state)
        self.assertIn("Transport endpoint", reason)


class WireTests(unittest.TestCase):
    def test_same_format_both_sides(self):
        self.assertEqual(helper.MSG.format, client.MSG.format)

    def test_listener_dispatch(self):
        got = []
        lis = client.InputdListener(lambda c: got.append(("down", c)), lambda c: got.append(("up", c)),
                                    lambda b, p: got.append(("btn", b, p)))
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        for m in ((b"K", 30, 1), (b"K", 30, 2), (b"K", 30, 0), (b"B", 1, 1), (b"B", 1, 0)):
            a.send(struct.pack("<cHB", *m))
        a.close()
        lis._read(b)
        b.close()
        self.assertEqual(got, [("down", 30), ("down", 30), ("up", 30), ("btn", 1, True), ("btn", 1, False)])


if __name__ == "__main__":
    unittest.main()

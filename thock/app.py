import argparse, os, signal, sys, time

APP_ID = "dev.local.Thock"


def _log(msg):
    # Status messages only. Never key names or codes.
    print(f"[thock] {msg}", flush=True)


def self_test(args):
    from .config import Config
    from .engine import Engine
    from .packs import list_packs
    from .keymap import key_x
    cfg = Config()
    eng = Engine(cfg)
    eng.start()
    _log(f"audio stream open, output latency {eng.mixer.output_latency*1000:.1f} ms, block 128 frames")
    packs = [p["id"] for p in list_packs()] if args.all_packs else [cfg["pack"]]
    # left-to-right sweep: Esc/`, a few letters, space, enter, backspace, then mouse
    seq = [41, 16, 30, 44, 34, 57, 24, 38, 28, 14]
    for pid in packs:
        eng.load_pack(pid, cfg["tone"], sync=True)
        _log(f"pack {pid}: playing {len(seq)} down/up pairs, left -> right")
        for c in seq:
            eng.key_down(c); time.sleep(0.08); eng.key_up(c); time.sleep(0.1)
        for b in (1, 3, 2):
            eng.button(b, True); time.sleep(0.07); eng.button(b, False); time.sleep(0.12)
    delays = eng.mixer.last_start_delay
    _log(f"last trigger->mix delay {delays*1000:.2f} ms; underflows {eng.mixer.stats['underflows']}")
    time.sleep(0.4)
    eng.stop()
    return 0


def latency_test(args):
    """Inject harmless key events with XTest (a keycode with no symbol) and time the whole path."""
    from Xlib import display, X
    from Xlib.ext import xtest
    from .config import Config
    from .engine import Engine
    from .xinput import XInputListener, EVDEV_OFFSET
    import numpy as np
    d = display.Display()
    mn, mx = d.display.info.min_keycode, d.display.info.max_keycode
    free = [kc for kc in range(mx, mn, -1) if d.keycode_to_keysym(kc, 0) == 0]
    if not free:
        _log("no unmapped keycode available for a safe test"); return 1
    kc = free[0]
    cfg = Config()
    eng = Engine(cfg)
    # make sure the injected code has a sound even if it is not in the pack
    eng.start()
    marks = {}
    orig_down = eng.key_down

    def down(code):
        marks["event"] = time.perf_counter()
        orig_down(code)
        marks["queued"] = time.perf_counter()
    lis = XInputListener(down, eng.key_up, eng.button)
    lis.start()
    time.sleep(0.5)
    ev_lat, mix_lat = [], []
    for i in range(args.n):
        marks.clear(); eng.mixer.last_start_delay = None
        t0 = time.perf_counter()
        xtest.fake_input(d, X.KeyPress, kc); d.sync()
        while "queued" not in marks and time.perf_counter() - t0 < 0.5:
            time.sleep(0.0002)
        while eng.mixer.last_start_delay is None and time.perf_counter() - t0 < 0.5:
            time.sleep(0.0002)
        xtest.fake_input(d, X.KeyRelease, kc); d.sync()
        if "event" in marks and eng.mixer.last_start_delay is not None:
            ev_lat.append((marks["event"] - t0) * 1000)
            mix_lat.append((marks["queued"] - t0) * 1000 + eng.mixer.last_start_delay * 1000)
        time.sleep(0.15)
    out_ms = eng.mixer.output_latency * 1000
    lis.stop(); eng.stop()
    if not ev_lat:
        _log("no events captured"); return 1
    e, m = np.array(ev_lat), np.array(mix_lat)
    _log(f"{len(e)} injected presses on an unmapped keycode")
    _log(f"X event -> app: median {np.median(e):.2f} ms, max {e.max():.2f} ms")
    _log(f"X event -> sample in audio buffer: median {np.median(m):.2f} ms, max {m.max():.2f} ms")
    _log(f"audio device output latency (reported): {out_ms:.1f} ms")
    _log(f"estimated key -> sound total: median {np.median(m)+out_ms:.1f} ms")
    return 0


def run_app(argv):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gio, GLib
    from .config import Config
    from .engine import Engine
    from .xinput import XInputListener
    from .ui import Tray, SettingsWindow

    class ThockApp(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.window = None
            self.engine = None
            self.listener = None

        def do_startup(self):
            Gtk.Application.do_startup(self)
            self.hold()
            self.cfg = Config()
            self.engine = Engine(self.cfg)
            self.engine.start()
            _log(f"audio ready (output latency {self.engine.mixer.output_latency*1000:.1f} ms)")
            self.listener = XInputListener(self.engine.key_down, self.engine.key_up, self.engine.button)
            self.listener.start()
            _log("listening for key and mouse events via X RECORD")
            self.tray = Tray(self)
            _log("tray icon ready")
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._sig)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._sig)

        def _sig(self):
            self.quit(); return False

        def do_command_line(self, cmd):
            args = cmd.get_arguments()[1:]
            if "--quit" in args:
                self.quit()
            elif "--settings" in args:
                self.show_settings()
            return 0

        def show_settings(self):
            if self.window is None:
                self.window = SettingsWindow(self)
                self.add_window(self.window)
            self.window.show_all()
            self.window.present()

        def do_shutdown(self):
            _log("shutting down")
            try:
                self.listener and self.listener.stop()
                self.engine and self.engine.stop()
            finally:
                Gtk.Application.do_shutdown(self)

    return ThockApp().run([sys.argv[0]] + argv)


def main():
    p = argparse.ArgumentParser(prog="thock", add_help=True)
    p.add_argument("--settings", action="store_true", help="open the settings window")
    p.add_argument("--quit", action="store_true", help="quit the running instance")
    p.add_argument("--self-test", action="store_true", help="play a left-to-right test sequence and exit")
    p.add_argument("--all-packs", action="store_true", help="with --self-test, play every pack")
    p.add_argument("--latency-test", action="store_true", help="measure key -> sound latency with XTest")
    p.add_argument("-n", type=int, default=30)
    args, rest = p.parse_known_args()
    if args.self_test:
        return self_test(args)
    if args.latency_test:
        return latency_test(args)
    fw = [a for a in ("--settings", "--quit") if getattr(args, a[2:])]
    return run_app(fw)

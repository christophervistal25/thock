"""Key and mouse-button events from the thock-inputd service, for Wayland sessions.

Wayland does not let a desktop app hear key presses system-wide, so a small system service
(helper/thock-inputd.py) reads /dev/input and forwards the events over a Unix socket. This is the
app side. Same constructor, start()/stop() and callbacks as thock.xinput.XInputListener:
on_key_down(evdev keycode), on_key_up(evdev keycode), on_button(1|2|3, pressed).
Nothing is logged or stored: each event goes straight to the callbacks.
"""
import os
import socket
import struct
import threading
import time

SOCK = os.environ.get("THOCK_INPUTD_SOCK", "/run/thock-inputd/inputd.sock")
MSG = struct.Struct("<cHB")   # must match helper/thock-inputd.py
RETRY_S = 2.0


def _log(msg):
    # Status messages only. Never key names or codes.
    print(f"[thock] {msg}", flush=True)


class InputdListener:
    def __init__(self, on_key_down, on_key_up, on_button):
        self.on_key_down, self.on_key_up, self.on_button = on_key_down, on_key_up, on_button
        self.events_seen = 0
        self._stop = threading.Event()
        self._sock = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="thock-inputd", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        s = self._sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _run(self):
        warned = False
        while not self._stop.is_set():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                s.connect(SOCK)
            except OSError as e:
                s.close()
                if not warned:
                    _log(f"cannot reach thock-inputd at {SOCK} ({e.strerror}); retrying every {RETRY_S:.0f} s. "
                         "Set it up with helper/install-inputd.sh, check with: systemctl status thock-inputd")
                    warned = True
                self._stop.wait(RETRY_S)
                continue
            self._sock = s
            _log("connected to thock-inputd")
            warned = False
            try:
                self._read(s)
            finally:
                self._sock = None
                s.close()
            if not self._stop.is_set():
                _log("thock-inputd went away; reconnecting")
                time.sleep(0.2)

    def _read(self, s):
        while not self._stop.is_set():
            try:
                data = s.recv(64)
            except OSError:
                return
            if not data:
                return
            if len(data) != MSG.size:
                continue
            kind, code, value = MSG.unpack(data)
            self.events_seen += 1
            if kind == b"K":
                if value == 0:
                    self.on_key_up(code)
                else:   # 1 = press, 2 = auto-repeat (the engine applies its own repeat setting)
                    self.on_key_down(code)
            elif kind == b"B":
                self.on_button(code, value == 1)

"""System-wide key and mouse-button events via the X11 RECORD extension (no root needed).

Only the event type and keycode are read, passed straight to the engine and discarded.
Nothing is logged or written anywhere.
"""
import threading
from Xlib import X, display
from Xlib.ext import record
from Xlib.protocol import rq

EVDEV_OFFSET = 8   # X keycode = evdev keycode + 8


class XInputListener:
    def __init__(self, on_key_down, on_key_up, on_button):
        self.on_key_down, self.on_key_up, self.on_button = on_key_down, on_key_up, on_button
        self._ctrl = display.Display()
        self._rec = display.Display()
        if not self._rec.has_extension("RECORD"):
            raise RuntimeError("X server has no RECORD extension")
        self._ctx = None
        self._thread = None
        self.events_seen = 0

    def start(self):
        self._ctx = self._rec.record_create_context(0, [record.AllClients], [{
            "core_requests": (0, 0), "core_replies": (0, 0),
            "ext_requests": (0, 0, 0, 0), "ext_replies": (0, 0, 0, 0),
            "delivered_events": (0, 0),
            "device_events": (X.KeyPress, X.ButtonRelease),
            "errors": (0, 0), "client_started": False, "client_died": False,
        }])
        self._thread = threading.Thread(target=self._run, name="thock-xrecord", daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._rec.record_enable_context(self._ctx, self._cb)
        finally:
            try:
                self._rec.record_free_context(self._ctx)
            except Exception:
                pass

    def stop(self):
        if self._ctx is not None:
            try:
                self._ctrl.record_disable_context(self._ctx)
                self._ctrl.flush()
            except Exception:
                pass

    def _cb(self, reply):
        if reply.category != record.FromServer or reply.client_swapped or not len(reply.data):
            return
        data = reply.data
        evs = []
        while len(data):
            ev, data = rq.EventField(None).parse_binary_value(data, self._rec.display, None, None)
            evs.append((ev.type, ev.detail, ev.time))
        self.events_seen += len(evs)
        i = 0
        n = len(evs)
        while i < n:
            t, code, tm = evs[i]
            if t == X.KeyRelease:
                # Server auto-repeat shows up as Release+Press with the same timestamp: skip both.
                if i + 1 < n and evs[i + 1][0] == X.KeyPress and evs[i + 1][1] == code and evs[i + 1][2] == tm:
                    i += 2
                    continue
                self.on_key_up(code - EVDEV_OFFSET)
            elif t == X.KeyPress:
                self.on_key_down(code - EVDEV_OFFSET)
            elif t == X.ButtonPress:
                self.on_button(code, True)
            elif t == X.ButtonRelease:
                self.on_button(code, False)
            i += 1

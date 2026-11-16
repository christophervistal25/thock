"""Picks where key and mouse-button events come from.

X11 session: the X RECORD extension (thock.xinput.XInputListener, unchanged).
Wayland session: the thock-inputd system service (thock.inputd.InputdListener), because Wayland
does not let apps hear key presses system-wide. THOCK_INPUT=x11 or THOCK_INPUT=inputd overrides
the choice. Both listeners take the same callbacks and have start()/stop().
"""
import os

LABELS = {"x11": "X RECORD", "inputd": "thock-inputd (Wayland)"}


def backend(environ=os.environ):
    forced = environ.get("THOCK_INPUT", "").strip().lower()
    if forced in LABELS:
        return forced
    return "inputd" if environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" else "x11"


def make_listener(on_key_down, on_key_up, on_button, environ=os.environ):
    if backend(environ) == "inputd":
        from .inputd import InputdListener
        return InputdListener(on_key_down, on_key_up, on_button)
    from .xinput import XInputListener
    return XInputListener(on_key_down, on_key_up, on_button)

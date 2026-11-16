#!/usr/bin/python3
"""thock-inputd: reads key and mouse-button events from /dev/input and passes them to Thock.

Runs as a systemd system service under its own system user (thock-inputd), whose only extra
right is reading input devices (group input). Wayland does not let a desktop app hear key presses system-wide, so this
small service does it instead and hands the events to the Thock app over a Unix socket.

What it does to keep that safe:
- Only the one desktop user named in /etc/thock-inputd.conf may connect (checked with SO_PEERCRED).
- By default ("detail = coarse") letter, digit and symbol keys are reported only as one of five
  zones of the keyboard, never the exact key, so a program listening on the socket cannot
  reconstruct what you type. Space, Enter, Backspace, modifiers, F-keys and arrows stay exact
  because packs have special sounds for them and they say little about what you typed.
- Nothing is sent while that user's session is locked or not in the foreground
  (logind Active / LockedHint), so lock-screen passwords never reach the socket.
- Nothing is logged except status messages. Devices are only read, never grabbed or written.

Wire format: one SOCK_SEQPACKET message per event, struct "<cHB":
  b"K", evdev keycode, 1 = down / 2 = auto-repeat / 0 = up
  b"B", mouse button (1 left, 2 middle, 3 right), 1 = down / 0 = up
"""
import configparser
import glob
import os
import pwd
import select
import socket
import struct
import subprocess
import sys
import threading
import time

CONF = "/etc/thock-inputd.conf"
SOCK_DIR = os.environ.get("RUNTIME_DIRECTORY", "/run/thock-inputd")
SOCK = os.path.join(SOCK_DIR, "inputd.sock")
MSG = struct.Struct("<cHB")
RESCAN_S = 2.0          # look for new or removed input devices this often
SESSION_CHECK_S = 1.0   # re-read lock / foreground state this often

EV_KEY = 1
KEY_A, KEY_Z = 30, 44
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
MOUSE = {BTN_LEFT: 1, BTN_MIDDLE: 2, BTN_RIGHT: 3}

# Coarse mode: every text key is reported as a key from its zone (evdev codes are physical
# positions, so this holds for any layout). Zone = roughly which fifth of the keyboard, plus the
# numpad. The first code of a zone is what is sent; when two keys of the same zone are held at
# once (fast typing rolls over), the next free code of the zone is used so the press/release
# pairs stay separate. Which code is sent depends only on how many zone keys are held, not on
# which key it is.
ZONES = (
    (30, 31, 16, 17, 2, 3, 44, 45, 41, 86),                   # A S Q W 1 2 Z X ` <>
    (32, 33, 18, 19, 4, 5, 46, 47),                           # D F E R 3 4 C V
    (35, 34, 21, 20, 7, 6, 49, 48),                           # H G Y T 6 5 N B
    (37, 36, 23, 22, 9, 8, 50, 51),                           # K J I U 8 7 M ,
    (39, 38, 25, 24, 11, 10, 40, 26, 27, 12, 13, 43, 52, 53),  # ; L P O 0 9 ' [ ] - = \ . /
    (76, 75, 77, 72, 80, 71, 73, 79, 81, 82, 83, 55, 74, 78, 96, 98, 117, 121),  # numpad
)
ZONE_OF = {code: i for i, codes in enumerate(ZONES) for code in codes}


class Coarsener:
    def __init__(self):
        self.sent = {}   # real code -> code sent for it, while held

    def __call__(self, code, value):
        z = ZONE_OF.get(code)
        if z is None:
            return code
        if value == 0:
            return self.sent.pop(code, ZONES[z][0])
        if code not in self.sent:
            used = set(self.sent.values())
            self.sent[code] = next((c for c in ZONES[z] if c not in used), ZONES[z][0])
        return self.sent[code]


def log(msg):
    print(f"thock-inputd: {msg}", flush=True)


def read_conf(path=CONF):
    cp = configparser.ConfigParser()
    with open(path) as f:
        cp.read_string("[main]\n" + f.read())
    m = cp["main"]
    user = m.get("user", "").strip()
    if not user:
        raise SystemExit(f"{path}: 'user = <desktop user>' is required")
    detail = m.get("detail", "coarse").strip()
    if detail not in ("coarse", "exact"):
        raise SystemExit(f"{path}: detail must be 'coarse' or 'exact'")
    return user, detail


class SessionGate(threading.Thread):
    """Keeps .open True while the user's graphical session is unlocked and in the foreground of its seat.

    Asks logind over D-Bus (loginctl): its state files in /run/systemd hold Active but not
    LockedHint. Runs in its own thread so a slow answer never delays a key sound.
    Any doubt (no session, logind unreachable) means muted, and the reason is logged."""

    def __init__(self, user):
        super().__init__(name="session-gate", daemon=True)
        self.user = user
        self.open = False
        self._last = None

    @staticmethod
    def _loginctl(*args):
        r = subprocess.run(["loginctl", *args], capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"loginctl exit {r.returncode}")
        return r.stdout.strip()

    def state(self):
        """(open, reason) for the user's display session."""
        try:
            sid = self._loginctl("show-user", self.user, "-p", "Display", "--value")
            if not sid:
                return False, "no graphical session"
            props = dict(l.split("=", 1) for l in self._loginctl(
                "show-session", sid, "-p", "Active", "-p", "LockedHint").splitlines() if "=" in l)
        except Exception as e:
            return False, f"cannot ask logind ({e})"
        return self.decide(sid, props)

    @staticmethod
    def decide(sid, props):
        if props.get("Active") != "yes":
            return False, f"session {sid} not in the foreground"
        if props.get("LockedHint") != "no":
            return False, f"session {sid} locked"
        return True, f"session {sid} unlocked and active"

    def run(self):
        while True:
            state, reason = self.state()
            if (state, reason) != self._last:
                log(f"{reason}: {'forwarding' if state else 'muted'}")
                self._last = (state, reason)
            self.open = state
            time.sleep(SESSION_CHECK_S)


class Devices:
    """Every keyboard (has KEY_A..KEY_Z) and mouse (has BTN_LEFT) under /dev/input, re-scanned for hotplug."""

    def __init__(self):
        import evdev
        self.evdev = evdev
        self.by_fd = {}
        self.paths = set()
        self._skip = set()   # non-keyboard/mouse devices, so they are not reopened every scan

    def scan(self):
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in self.paths or path in self._skip:
                continue
            try:
                d = self.evdev.InputDevice(path)
                keys = set(d.capabilities().get(EV_KEY, []))
            except OSError:
                continue
            if keys & set(range(KEY_A, KEY_Z + 1)) or BTN_LEFT in keys:
                self.by_fd[d.fd] = d
                self.paths.add(path)
                log(f"watching {path} ({d.name})")
            else:
                d.close()
                self._skip.add(path)
        self._skip &= set(glob.glob("/dev/input/event*"))  # forget removed paths, they may be reused

    def drop(self, fd):
        d = self.by_fd.pop(fd, None)
        if d is not None:
            self.paths.discard(d.path)
            log(f"device gone: {d.path}")
            try:
                d.close()
            except OSError:
                pass


class Server:
    def __init__(self, uid):
        self.uid = uid
        os.makedirs(SOCK_DIR, exist_ok=True)
        try:
            os.unlink(SOCK)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.sock.bind(SOCK)
        os.chmod(SOCK, 0o666)   # anyone may connect; the peer uid is checked right after accept()
        self.sock.listen(4)
        self.sock.setblocking(False)
        self.clients = {}

    def accept(self):
        try:
            c, _ = self.sock.accept()
        except BlockingIOError:
            return
        pid, uid, gid = struct.unpack("3i", c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != self.uid:
            log(f"refused a client with uid {uid}")
            c.close()
            return
        c.setblocking(False)
        self.clients[c.fileno()] = c
        log(f"client connected (pid {pid}); {len(self.clients)} connected")

    def drop(self, fd):
        c = self.clients.pop(fd, None)
        if c is not None:
            c.close()
            log(f"client disconnected; {len(self.clients)} connected")

    def send(self, msg):
        for fd, c in list(self.clients.items()):
            try:
                c.send(msg)
            except BlockingIOError:
                pass            # client is behind: drop this event rather than block typing sounds
            except OSError:
                self.drop(fd)


def main():
    user, detail = read_conf()
    uid = pwd.getpwnam(user).pw_uid
    srv = Server(uid)
    devs = Devices()
    gate = SessionGate(user)
    gate.start()
    coarse = None if detail == "exact" else Coarsener()
    log(f"forwarding to {user} (uid {uid}), detail = {detail}")
    next_scan = 0.0
    while True:
        now = time.monotonic()
        if now >= next_scan:
            devs.scan()
            next_scan = now + RESCAN_S
        fds = [srv.sock.fileno(), *devs.by_fd, *srv.clients]
        ready, _, _ = select.select(fds, [], [], max(0.05, next_scan - time.monotonic()))
        for fd in ready:
            if fd == srv.sock.fileno():
                srv.accept()
            elif fd in srv.clients:
                srv.drop(fd)    # clients never send anything; readable means closed
            elif fd in devs.by_fd:
                try:
                    events = list(devs.by_fd[fd].read())
                except OSError:
                    devs.drop(fd)
                    continue
                if not srv.clients or not gate.open:
                    continue
                for e in events:
                    if e.type != EV_KEY:
                        continue
                    if e.code in MOUSE:
                        if e.value in (0, 1):
                            srv.send(MSG.pack(b"B", MOUSE[e.code], e.value))
                    elif e.code < 0x100 or e.code >= 0x160:   # keys, not joystick/tablet buttons
                        code = e.code if coarse is None else coarse(e.code, e.value)
                        srv.send(MSG.pack(b"K", code, e.value))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

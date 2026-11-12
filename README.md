<p align="center"><img src="data/thock.svg" width="96" alt="Thock icon"></p>

<h1 align="center">Thock</h1>

<p align="center"><strong>Mechanical keyboard sounds for your Linux desktop.</strong><br>
Every key you press plays a real switch recording. It lives in your tray and stays out of the way.</p>

<p align="center">
  <a href="https://github.com/christophervistal25/thock/releases/latest/download/thock-linux.tar.gz"><strong>Download for Linux</strong></a> ·
  <a href="https://christophervistal25.github.io/thock/">Website</a>
</p>

## Requirements

Ubuntu 22.04+ or another Debian-based Linux. X11 works out of the box; Wayland needs a one-time setup with
sudo (see [Wayland](#wayland)). `echo $XDG_SESSION_TYPE` tells you which one you're on.

## Install

```sh
cd ~ && wget -qO- https://github.com/christophervistal25/thock/releases/latest/download/thock-linux.tar.gz | tar xz && cd thock && ./install.sh && bin/thock
```

Start it from the app menu or with `bin/thock`. Open settings from the tray icon or with `bin/thock --settings`.

## Wayland

On X11, Thock hears key presses through the X RECORD extension. Wayland doesn't let an app hear key presses
system-wide, so there Thock gets them from **thock-inputd**, a small system service that reads `/dev/input`
and passes key and mouse-button events to your session over a Unix socket. `install.sh` offers to set it up
when it sees a Wayland session; you can also run it yourself (needs sudo, python3-evdev is added with apt):

```sh
helper/install-inputd.sh              # install or update; events go to the user who runs it
helper/install-inputd.sh --uninstall  # remove it again
```

Thock picks the source by itself (`XDG_SESSION_TYPE`); `THOCK_INPUT=x11` or `THOCK_INPUT=inputd` overrides it.

Why a service and not "add yourself to the `input` group": that would let **every program you run** read every
key, including passwords. thock-inputd gives your session less:

- It runs as its own system user (`thock-inputd`) whose only extra right is the `input` group: no root, no
  capabilities, no network, read-only system, system-call filter (`systemd-analyze security thock-inputd`
  rates it 0.9, "SAFE"). It reads devices, never grabs or writes to them, and logs no keys.
- Only the user named in `/etc/thock-inputd.conf` may connect (`SO_PEERCRED`).
- Nothing is sent while that user's session is locked or not in front (logind `LockedHint` / `Active`).
- With `detail = coarse` (the default), letter, digit and symbol keys are sent only as one of five keyboard
  zones, so whatever reads the socket can't tell what you typed. Space, Enter, Backspace, modifiers, F-keys and
  arrows stay exact. Every pack sounds the same as on X11 except **Buckling Spring**, which has a recording per
  key and plays the zone's recording instead. `detail = exact` in `/etc/thock-inputd.conf` gives every key its
  own recording, at the cost that any program you run could read your keystrokes from the socket.

Check it: `systemctl status thock-inputd` and `journalctl -u thock-inputd -f` ("watching /dev/input/eventN",
"client connected", "session ... forwarding/muted"); Thock's own output says `connected to thock-inputd`.
`--latency-test` needs X11 (XTest) and isn't available on Wayland. If you used the community
thock-wayland-addon before, run its `uninstall.sh` first, then `helper/install-inputd.sh`.

## More

Sound packs, usage, troubleshooting, uninstall, privacy and sound credits are on the
[website](https://christophervistal25.github.io/thock/). Sound sources and licenses: [SOUNDS-LICENSES.md](SOUNDS-LICENSES.md).

Inspired by [Hayyoth](https://www.youtube.com/@hayyoth-org) and their calm, hand-coded programming videos.

## Development

Run the tests: `.venv/bin/python -m unittest discover -s tests -v`

## License

Code: [MIT](LICENSE). Sound packs keep their own licenses: see [SOUNDS-LICENSES.md](SOUNDS-LICENSES.md).
Add-on authors: stable interfaces are listed in [CHANGELOG.md](CHANGELOG.md).

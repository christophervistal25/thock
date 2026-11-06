<p align="center"><img src="data/thock.svg" width="96" alt="Thock icon"></p>

<h1 align="center">Thock</h1>

<p align="center"><strong>Mechanical keyboard sounds for your Linux desktop.</strong><br>
Every key you press plays a real switch recording. It lives in your tray and stays out of the way.</p>

<p align="center">
  <a href="https://github.com/christophervistal25/thock/releases/latest/download/thock-linux.tar.gz"><strong>Download for Linux</strong></a> ·
  <a href="https://christophervistal25.github.io/thock/">Website</a>
</p>

## Requirements

Ubuntu 22.04+ or another Debian-based Linux, in an **X11** session (`echo $XDG_SESSION_TYPE` should print `x11`).
On Wayland, see the community [thock-wayland-addon](https://github.com/vitorhmcorreia/thock-wayland-addon) (third-party, not maintained here).

## Install

```sh
cd ~ && wget -qO- https://github.com/christophervistal25/thock/releases/latest/download/thock-linux.tar.gz | tar xz && cd thock && ./install.sh && bin/thock
```

Start it from the app menu or with `bin/thock`. Open settings from the tray icon or with `bin/thock --settings`.

## More

Sound packs, usage, troubleshooting, uninstall, privacy and sound credits are on the
[website](https://christophervistal25.github.io/thock/). Sound sources and licenses: [SOUNDS-LICENSES.md](SOUNDS-LICENSES.md).

Inspired by [Hayyoth](https://www.youtube.com/@hayyoth-org) and their calm, hand-coded programming videos.

## Development

Run the tests: `.venv/bin/python -m unittest discover -s tests -v`

## License

Code: [MIT](LICENSE). Sound packs keep their own licenses: see [SOUNDS-LICENSES.md](SOUNDS-LICENSES.md).
Add-on authors: stable interfaces are listed in [CHANGELOG.md](CHANGELOG.md).

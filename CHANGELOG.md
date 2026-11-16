# Changelog

## Stable interfaces for add-ons

Add-ons such as [thock-wayland-addon](https://github.com/vitorhmcorreia/thock-wayland-addon) build on these.
They stay stable; any change will be announced here first.

- `thock.xinput.XInputListener(on_key_down, on_key_up, on_button)` with `start()` and `stop()`.
  Callbacks get evdev key codes (`on_key_down(code)`, `on_key_up(code)`) and mouse buttons (`on_button(1|2|3, pressed)`).
- `thock.autostart.desktop_entry(autostart=False)` returns the `.desktop` file text.

## Unreleased

- Wayland support: key and mouse-button events come from thock-inputd, a small sandboxed system service
  (`helper/`), chosen automatically in a Wayland session. `install.sh` offers to set it up. X11 is unchanged.
- MIT license for the code (sound packs keep their own licenses, see SOUNDS-LICENSES.md).
- Calm sound packs: Thocky, Rainy 75, Lubed Tactile.
- Coding Relax pack (personal use, not under a free license).
- A pack can ship its own mouse clicks.
- Plain HTML website with FAQ, troubleshooting and full sound credits.

## 1.0.0 (2026-11-03)

- First release.

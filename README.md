# Thock

Personal mechanical-keyboard sound app for Ubuntu (X11). Plays a key-down and key-up sound for every key,
plus optional mouse clicks, panned left/right by key position, with subtle natural variation and a
thock <-> clack tone control. Lives in the system tray.

- Open settings: app menu -> **Thock**, or `bin/thock --settings`, or tray icon -> Settings…
- Start: `bin/thock` (starts automatically at login)
- Quit: tray -> Quit Thock, or `bin/thock --quit`
- Turn off autostart: Settings -> Start at login (off), or `rm ~/.config/autostart/thock.desktop`
- Test: `bin/thock --self-test [--all-packs]`, `bin/thock --latency-test`
- Settings file: `~/.config/thock/config.json` (preferences only)

Privacy: input is read with the X RECORD extension; only event type + keycode are used in memory to pick
and pan a sound and are dropped immediately. Nothing typed is logged, stored or sent. No network use.

Rebuild packs from sources: `tools/build_packs.py` (needs the source downloads; see SOUNDS-LICENSES.md).

#!/bin/sh
# Sets up the venv, app-menu launcher and login autostart for Thock. Safe to re-run.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# System packages Thock needs (GTK, tray icon, X11 input, audio).
DEPS="python3-venv python3-gi python3-xlib gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 libportaudio2"
if command -v dpkg-query >/dev/null 2>&1; then
  MISSING=""
  for p in $DEPS; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || MISSING="$MISSING $p"
  done
  if [ -n "$MISSING" ]; then
    echo "Installing missing system packages:$MISSING"
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
    $SUDO apt-get update -q
    $SUDO apt-get install -y $MISSING
  fi
else
  echo "Not a Debian/Ubuntu system; make sure these are installed: $DEPS"
fi

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && ! systemctl is-active --quiet thock-inputd 2>/dev/null; then
  echo
  echo "This is a Wayland session. Wayland doesn't let apps hear key presses system-wide, so Thock"
  echo "needs a small system service, thock-inputd, that reads /dev/input and passes key and mouse-button"
  echo "events to your session only (see 'Wayland' in README.md). Setting it up needs sudo."
  ANSWER=""
  if [ -r /dev/tty ]; then
    printf "Set up thock-inputd now? [y/N] "
    read -r ANSWER </dev/tty || ANSWER=""
  fi
  case "$ANSWER" in
    y|Y|yes|YES) "$HERE/helper/install-inputd.sh" ;;
    *) echo "Skipped. Set it up later with: $HERE/helper/install-inputd.sh" ;;
  esac
  echo
fi

[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -r requirements.txt

# Fail early with a clear message if something is still missing.
.venv/bin/python -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import Gtk, AyatanaAppIndicator3; import Xlib, sounddevice, numpy" \
  || { echo "Thock's dependencies are not all available; see the error above."; exit 1; }

.venv/bin/python - <<'PY'
import os
from thock import autostart
apps = os.path.expanduser("~/.local/share/applications")
os.makedirs(apps, exist_ok=True)
open(os.path.join(apps, "thock.desktop"), "w").write(autostart.desktop_entry(False))
autostart.set_enabled(True)
print("launcher:", os.path.join(apps, "thock.desktop"))
print("autostart:", autostart.AUTOSTART)
PY
echo "Done. Start it now with: $HERE/bin/thock"

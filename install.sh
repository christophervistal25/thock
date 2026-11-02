#!/bin/sh
# Sets up the venv, app-menu launcher and login autostart for Thock. Safe to re-run.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -r requirements.txt
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

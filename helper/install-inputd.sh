#!/bin/sh
# Sets up (or removes) thock-inputd, the small system service that gives Thock key presses on Wayland.
# Run as your desktop user; it uses sudo. Safe to re-run.
#   helper/install-inputd.sh              install or update, events go to the user running it
#   helper/install-inputd.sh --uninstall  stop and remove the service and its system user
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LIB=/usr/local/lib/thock
UNIT=/etc/systemd/system/thock-inputd.service
SYSUSERS=/etc/sysusers.d/thock-inputd.conf
CONF=/etc/thock-inputd.conf
[ "$(id -u)" -ne 0 ] || { echo "Run as your desktop user, not root (it uses sudo)." >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  sudo systemctl disable --now thock-inputd.service 2>/dev/null || true
  sudo rm -f "$UNIT" "$SYSUSERS"
  sudo rm -rf "$LIB"
  sudo systemctl daemon-reload
  id thock-inputd >/dev/null 2>&1 && sudo userdel thock-inputd || true
  echo "thock-inputd removed. Kept $CONF (delete it by hand if you like)."
  exit 0
fi

# python-evdev for the system Python the service runs on.
if ! /usr/bin/python3 -c "import evdev" 2>/dev/null; then
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y python3-evdev
  else echo "Install python-evdev for /usr/bin/python3 (package python3-evdev / python-evdev), then re-run." >&2; exit 1; fi
fi

sudo install -d -m 0755 "$LIB"
sudo install -m 0755 "$HERE/thock-inputd.py" "$LIB/thock-inputd.py"
# Stop a running copy first: while a DynamicUser= service with the same name runs (early versions of
# the community add-on), systemd-sysusers sees the name as taken and skips creating the real user.
sudo systemctl stop thock-inputd.service 2>/dev/null || true
sudo install -D -m 0644 "$HERE/thock-inputd.sysusers" "$SYSUSERS"
sudo systemd-sysusers "$SYSUSERS"    # system user thock-inputd, member of group input
getent passwd thock-inputd | grep -q '/usr/sbin/nologin$' && id -nG thock-inputd | grep -qw input \
  || { echo "System user thock-inputd was not created (or is not in group input)." >&2; exit 1; }
sudo install -m 0644 "$HERE/thock-inputd.service" "$UNIT"
if [ -f "$CONF" ]; then
  echo "Keeping existing $CONF (user = $(sudo sed -n 's/^user *= *//p' "$CONF"))"
else
  sed "s/^user = CHANGE_ME/user = $(id -un)/" "$HERE/thock-inputd.conf" | sudo tee "$CONF" >/dev/null
  sudo chmod 0644 "$CONF"
fi
sudo systemctl daemon-reload
sudo systemctl enable thock-inputd.service >/dev/null
sudo systemctl restart thock-inputd.service

if [ -d /usr/local/lib/thock-wayland-addon ]; then
  echo "Note: /usr/local/lib/thock-wayland-addon is left over from the community add-on and is no longer used;"
  echo "      remove it with: sudo rm -rf /usr/local/lib/thock-wayland-addon"
fi
sleep 1
if systemctl is-active --quiet thock-inputd; then echo "thock-inputd: running"
else echo "thock-inputd did not start; see: journalctl -u thock-inputd" >&2; exit 1; fi

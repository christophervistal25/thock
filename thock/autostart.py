import os

AUTOSTART = os.path.expanduser("~/.config/autostart/thock.desktop")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def desktop_entry(autostart=False):
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Thock",
        "Comment=Mechanical keyboard sounds while you type",
        f"Exec={ROOT}/bin/thock" + ("" if autostart else " --settings"),
        f"Icon={ROOT}/data/thock.svg",
        "Terminal=false",
        "Categories=Utility;Audio;",
        "StartupNotify=false",
    ]
    if autostart:
        lines += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=3", "NoDisplay=true"]
    return "\n".join(lines) + "\n"


def is_enabled():
    return os.path.isfile(AUTOSTART)


def set_enabled(on):
    if on:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, "w") as f:
            f.write(desktop_entry(True))
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)

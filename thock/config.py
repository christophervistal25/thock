import json, os, threading

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "thock")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "enabled": True,
    "pack": "tactile-brown",
    "volume": 0.6,          # 0..1
    "tone": 0.0,            # -1 = deep thock, +1 = bright clack
    "mouse": True,
    "spatial": True,
    "release": True,        # play key-up sounds
    "pitch_variation": True,
    "repeat": False,        # play the key-down sound again on X auto-repeat
}


class Config:
    """Settings store. Holds preferences only; never anything typed."""

    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._listeners = []
        self.data = dict(DEFAULTS)
        try:
            with open(self.path) as f:
                stored = json.load(f)
            for k, v in stored.items():
                if k in DEFAULTS and (type(v) is type(DEFAULTS[k]) or (k in ("volume", "tone") and type(v) in (int, float))):
                    self.data[k] = v
        except (OSError, ValueError):
            pass
        self.data["volume"] = float(min(1.0, max(0.0, self.data["volume"])))
        self.data["tone"] = float(min(1.0, max(-1.0, self.data["tone"])))

    def __getitem__(self, k):
        return self.data[k]

    def set(self, key, value, source=None):
        if self.data.get(key) == value:
            return
        self.data[key] = value
        self.save()
        for cb in list(self._listeners):
            cb(key, value, source)

    def on_change(self, cb):
        self._listeners.append(cb)

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)

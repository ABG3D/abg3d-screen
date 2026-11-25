"""Persistent settings. Written atomically and fsync'd so a power cut cannot corrupt them."""
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("ABG3D_CONFIG_DIR", Path.home() / ".config" / "abg3d-screen"))
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "theme": "midnight",
    "printer_family": None,
    "printer_model": None,
    "mouse_pointer": True,          # True = pointer visible, False = hidden
    "moonraker_url": "http://127.0.0.1:7125",
    "show_splash": True,
    "setup_done": False,
    "mmu_enabled": False,   # MMU tab only exists when this is on (and an MMU is detected)
    "allow_quit": False,    # the Quit button only appears when this is on
    "monitor_disabled": [],  # sensors the user has switched off on the Home monitor
    "macro_favs": [],        # Klipper macros pinned as favourites
    "macro_hidden": [],      # Klipper macros hidden from the macro list
    "pin_bedfans": False,    # enable bed fan controls on the Control tab
    "pin_caselight": False,  # enable case light control on the Control tab
}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            loaded = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if isinstance(loaded, dict):
            self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, **values):
        self.data.update({k: v for k, v in values.items() if k in DEFAULTS})
        self.save()

"""Themes and resolution scaling. Pages are laid out on an 800x480 grid and scaled to the real screen."""
import json

from . import ASSETS_DIR

FONT_SCALE = 0.88


class Theme:
    def __init__(self, key, data):
        self.key = key
        self.name = data["name"]
        self.colors = data["colors"]

    def __getitem__(self, name):
        return self.colors[name]


class Scale:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.s = max(0.6, min(2.0, min(width / 800.0, height / 480.0)))

    def px(self, value):
        return max(1, int(round(value * self.s)))

    def font(self, size, weight="normal"):
        # FONT_SCALE trims all text so labels fit the 800x480 grid
        return ("DejaVu Sans", max(7, int(round(size * self.s * FONT_SCALE))), weight)


def load_themes():
    data = json.loads((ASSETS_DIR / "data" / "themes.json").read_text())
    return {key: Theme(key, value) for key, value in data["themes"].items()}

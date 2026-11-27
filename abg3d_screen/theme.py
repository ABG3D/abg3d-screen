"""Display detection, proportional UI scaling and theme palettes -> GTK CSS."""
import logging
import math
import os

log = logging.getLogger("abg3d.theme")

THEMES = {
    "midnight": {"name": "Midnight", "bg": "#0e1016", "surface": "#181b24", "surface2": "#222633",
                 "border": "#2f3546", "fg": "#e6e8ee", "muted": "#9aa3b5", "accent": "#3a82f7",
                 "accent_fg": "#ffffff"},
    "ember": {"name": "Ember", "bg": "#130c0a", "surface": "#21150f", "surface2": "#2e1d15",
              "border": "#4a2d20", "fg": "#f4e7df", "muted": "#bb9f8f", "accent": "#f26b1d",
              "accent_fg": "#ffffff"},
    "forest": {"name": "Forest", "bg": "#0b120e", "surface": "#132019", "surface2": "#1b2c22",
               "border": "#2a4334", "fg": "#e3efe6", "muted": "#95ad9d", "accent": "#3fbf68",
               "accent_fg": "#06140b"},
    "ocean": {"name": "Ocean", "bg": "#091117", "surface": "#0f1f28", "surface2": "#152a36",
              "border": "#234253", "fg": "#e0eef5", "muted": "#8eabba", "accent": "#1fb5c9",
              "accent_fg": "#03161a"},
    "graphite": {"name": "Graphite", "bg": "#111111", "surface": "#1b1b1b", "surface2": "#262626",
                 "border": "#3a3a3a", "fg": "#ececec", "muted": "#a0a0a0", "accent": "#e0a526",
                 "accent_fg": "#161004"},
    "amethyst": {"name": "Amethyst", "bg": "#110e18", "surface": "#1c1727", "surface2": "#272035",
                 "border": "#3b3150", "fg": "#ece6f5", "muted": "#a99cbd", "accent": "#a66cf0",
                 "accent_fg": "#ffffff"},
}
DEFAULT_THEME = "midnight"
STATUS = {"danger": "#c62f26", "danger_hi": "#e0443a", "warn": "#c4841f", "ok": "#3fbf68", "bad": "#ff6b5e"}

# (width, height) -> assumed diagonal (inches) when the panel reports no usable physical size
RES_GUESS = {(480, 272): 4.3, (800, 480): 7.0, (1024, 600): 7.0}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgba(h, a):
    r, g, b = hex_rgb(h)
    return "rgba(%d,%d,%d,%.3f)" % (r * 255, g * 255, b * 255, a)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Ui:
    """Scaling metrics derived from the active display resolution and DPI."""

    def __init__(self, width, height, width_mm=0, height_mm=0, diagonal=0.0, font_override=0, x=0, y=0):
        self.w, self.h = int(width), int(height)
        self.x, self.y = int(x), int(y)
        diag_px = math.hypot(self.w, self.h)
        dpi = None
        if diagonal and diagonal > 2:
            dpi = diag_px / float(diagonal)
        elif width_mm and height_mm and width_mm > 30 and height_mm > 20:
            d = diag_px / (math.hypot(width_mm, height_mm) / 25.4)
            if 70 <= d <= 330:
                dpi = d
        if dpi is None:
            guess = RES_GUESS.get((self.w, self.h))
            if guess is None:
                guess = 4.3 if self.h <= 300 else 7.0
            dpi = diag_px / guess
        self.dpi = dpi
        self.diag_in = diag_px / dpi
        self.small = self.h < 360 or self.diag_in < 4.8
        self.min_touch = 40 if self.small else 48
        self.scale = _clamp(min(self.w / 800.0, self.h / 480.0), 0.55, 1.45)
        dpi_adj = _clamp(math.sqrt(dpi / 140.0), 0.92, 1.12)
        # 800x480 (5"/7") is vertically tight: hold targets at the 48px minimum and the font at
        # 15px regardless of DPI, so header + content + nav always fit inside 480px.
        self.tight = self.h <= 480 and not self.small
        if self.tight:
            dpi_adj = min(dpi_adj, 1.0)
        self.touch = max(self.min_touch, int(round(48 * self.scale * dpi_adj)))
        self.fs = font_override or max(10, int(round(15 * self.scale * dpi_adj)))
        self.fs_s = max(9, int(self.fs * 0.82))
        self.fs_l = int(self.fs * 1.35)
        self.fs_xl = int(self.fs * 2.0)
        self.pad = max(3, int(round((5 if self.tight else 8) * self.scale)))
        self.sp = max(3, int(round((4 if self.tight else 6) * self.scale)))
        self.rad = max(5, int(round(10 * self.scale)))
        self.icon = max(16, int(self.touch * 0.52))
        self.icon_s = max(14, int(self.touch * 0.42))
        self.header_h = max(28, int(round(40 * self.scale)))
        self.nav_left = self.h >= 400
        self.hdr_btn = max(self.min_touch, self.header_h - 6)
        self.header_h = max(self.header_h, self.hdr_btn + 4)
        if self.nav_left:
            avail = self.h - self.header_h - 4 * self.sp
            self.nav_btn_h = max(self.min_touch, min(self.touch, avail // 7 - self.sp // 2))
        else:
            self.nav_btn_h = self.min_touch
        # rail wide enough for the longest label ("Settings") at the scaled small font
        self.nav_size = (max(self.touch, int(round(76 * self.scale)), int(self.fs_s * 5.6) + 14)
                         if self.nav_left else self.nav_btn_h)
        self.nav_labels = not self.small
        self.cols = 3 if self.w < 600 else 4 if self.w < 900 else 5
        self.thumb_home = 0 if self.small else int(min(150, self.h * 0.26))
        self.thumb_list = max(self.touch, int(self.touch * 1.25))
        self.graph_h = max(70, int(self.h * (0.30 if self.small else 0.36)))
        self.hex_r = max(6.0, 9.0 * self.scale)
        log.info("display %dx%d dpi=%.0f diag=%.1fin scale=%.2f touch=%d font=%d nav=%s",
                 self.w, self.h, self.dpi, self.diag_in, self.scale, self.touch, self.fs,
                 "left" if self.nav_left else "bottom")


def build_css(template_path, ui, theme_key):
    t = dict(THEMES.get(theme_key) or THEMES[DEFAULT_THEME])
    t.update(STATUS)
    with open(template_path) as f:
        css = f.read()
    tokens = {
        "FS_XL": ui.fs_xl, "FS_L": ui.fs_l, "FS_S": ui.fs_s, "FS": ui.fs,
        "TOUCH": ui.touch, "HALF": max(14, ui.touch // 2), "PAD2": ui.pad * 2, "PAD": ui.pad,
        "SP": ui.sp, "RAD": ui.rad, "HEADER": ui.header_h, "NAVH": ui.nav_btn_h, "HDRBTN": ui.hdr_btn, "KEY": max(ui.min_touch, int(ui.touch * 0.86)),
    }
    for k in sorted(tokens, key=len, reverse=True):
        css = css.replace("@%s@" % k, str(tokens[k]))
    colors = {
        "SURFACE_A": rgba(t["surface"], 0.86), "SURFACE2_A": rgba(t["surface2"], 0.92),
        "ACCENT_SOFT": rgba(t["accent"], 0.22), "MODAL_BG": rgba(t["bg"], 0.78),
    }
    for k in ("accent_fg", "surface2", "surface", "danger_hi", "danger", "border", "accent",
              "muted", "warn", "bad", "ok", "bg", "fg"):
        colors[k.upper()] = t[k]
    for k in sorted(colors, key=len, reverse=True):
        css = css.replace("@%s@" % k, colors[k])
    return css


def theme_colors(theme_key):
    return THEMES.get(theme_key) or THEMES[DEFAULT_THEME]


def detect_geometry(Gdk, cfg_w, cfg_h, fullscreen):
    """Return (x, y, w, h, width_mm, height_mm) of the active monitor (or configured window size)."""
    if not fullscreen:
        return 0, 0, cfg_w, cfg_h, 0, 0
    disp = Gdk.Display.get_default()
    mon = None
    if disp:
        mon = disp.get_primary_monitor() or (disp.get_monitor(0) if disp.get_n_monitors() else None)
    if not mon:
        return 0, 0, cfg_w, cfg_h, 0, 0
    geo = mon.get_geometry()
    return geo.x, geo.y, geo.width, geo.height, mon.get_width_mm(), mon.get_height_mm()


def env_flag(name):
    return os.environ.get(name, "").lower() in ("1", "true", "yes")

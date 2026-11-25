"""Honeycomb backdrop.

Hexagon outlines fade from the theme accent (top-left) to the theme background
(bottom-right). HexFrame is a canvas that paints the pattern and can hold packed or
placed children on top of it. Tk widgets are opaque, so the pattern shows wherever
no child covers it: the splash, the header, the tab bar and the page margins.
"""
import math
import tkinter as tk

HEX_R = 22            # base px radius of one hexagon
MAX_STRENGTH = 0.22   # how far the top-left outlines move toward the accent colour


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


class HexFrame(tk.Canvas):
    def __init__(self, master, app, **kw):
        self.app = app
        self.sc = app.scale
        super().__init__(master, bg=app.theme["bg"], highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", lambda _e: self.paint())

    def paint(self):
        self.delete("hex")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        t = self.app.theme
        r = self.sc.px(HEX_R)
        dx, dy = r * math.sqrt(3), 1.5 * r
        cols, rows = int(w / dx) + 2, int(h / dy) + 2
        for row in range(rows):
            for col in range(cols):
                cx = col * dx + (dx / 2 if row % 2 else 0)
                cy = row * dy
                f = (cx / w + cy / h) / 2           # 0 top-left, 1 bottom-right
                colour = mix(t["bg"], t["accent"], MAX_STRENGTH * max(0.0, 1 - f) ** 1.6)
                pts = []
                for k in range(6):
                    a = math.radians(60 * k - 30)
                    pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
                self.create_polygon(pts, outline=colour, fill="", width=1, tags="hex")

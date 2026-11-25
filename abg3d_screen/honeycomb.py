"""Honeycomb backdrop.

Hexagon outlines fade from the theme accent (top-left) to the surface colour (bottom-right).
HexFrame is a canvas that paints the pattern and holds packed or placed children on top.
base_key picks the surface colour: "bg" for the page backdrop, "panel" for cards. Outlines
are blended from that colour, so they follow the active theme. The pattern is repainted
whenever the widget changes size, and the whole UI is rebuilt when the theme changes.
"""
import math
import tkinter as tk

HEX_R = 22            # base px radius of one hexagon
MAX_STRENGTH = 0.30   # how far the top-left outlines move from the surface colour toward the accent


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


class HexFrame(tk.Canvas):
    def __init__(self, master, app, base_key="bg", **kw):
        self.app = app
        self.sc = app.scale
        self.base_key = base_key
        super().__init__(master, bg=app.theme[base_key], highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", lambda _e: self.paint())

    def paint(self):
        self.delete("hex")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        t = self.app.theme
        base = t[self.base_key]
        self.configure(bg=base)
        r = self.sc.px(HEX_R)
        dx, dy = r * math.sqrt(3), 1.5 * r
        cols, rows = int(w / dx) + 2, int(h / dy) + 2
        for row in range(rows):
            for col in range(cols):
                cx = col * dx + (dx / 2 if row % 2 else 0)
                cy = row * dy
                f = (cx / w + cy / h) / 2           # 0 top-left, 1 bottom-right
                colour = mix(base, t["accent"], MAX_STRENGTH * max(0.0, 1 - f) ** 1.6)
                pts = []
                for k in range(6):
                    a = math.radians(60 * k - 30)
                    pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
                self.create_polygon(pts, outline=colour, fill="", width=1, tags="hex")

"""Temperature monitor: live readings for every sensor and heater, with a 5-minute graph.

Tap a sensor to switch it on or off. Enabled sensors show live data, a coloured bar on
their left edge, and a line on the graph. The on/off choice is saved in settings.
"""
import collections
import time
import tkinter as tk

from .detect import temp_object_names
from .widgets import ScrollList

WINDOW_S = 300        # graph window in seconds
SAMPLE_S = 1.0        # one graph sample per second
COLOURS = ["#f29c38", "#5aa9e6", "#8fd17a", "#e06c75", "#c792ea", "#e5c36b", "#6fc9a0", "#f0a0c0"]


def display_name(obj):
    if obj == "extruder":
        return "Nozzle"
    if obj.startswith("extruder"):
        return f"Nozzle {obj[len('extruder'):]}"
    if obj == "heater_bed":
        return "Bed"
    for prefix, suffix in (("temperature_sensor ", ""), ("temperature_fan ", " fan"),
                           ("heater_generic ", ""), ("temperature_probe ", " probe")):
        if obj.startswith(prefix):
            return obj[len(prefix):] + suffix
    return obj


class MonitorView(tk.Frame):
    def __init__(self, master, app):
        self.app = app
        self.t = app.theme
        self.sc = app.scale
        super().__init__(master, bg=self.t["bg"])
        self.history = collections.deque(maxlen=WINDOW_S)
        self._last_sample = 0.0
        self._names = []
        self._colour = {}
        self._rows = {}
        self._values = {}

        side = tk.Frame(self, bg=self.t["panel"], width=self.sc.px(200))
        side.pack(side="left", fill="y", padx=(0, self.sc.px(6)))
        side.pack_propagate(False)
        tk.Label(side, text="Sensors", font=self.sc.font(12, "bold"), fg=self.t["accent"],
                 bg=self.t["panel"]).pack(anchor="w", padx=self.sc.px(10), pady=(self.sc.px(8), self.sc.px(4)))
        self.rows = ScrollList(side, self.app, visible_rows=5, row_h=46, bg=self.t["panel"])
        self.rows.pack(fill="both", expand=True, padx=self.sc.px(6))
        self.canvas = tk.Canvas(self, bg=self.t["panel"], highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw())

    # ---- enable / disable ---------------------------------------------
    def _disabled(self):
        return set(self.app.settings.get("monitor_disabled") or [])

    def _toggle(self, obj):
        off = self._disabled()
        if obj in off:
            off.discard(obj)
        else:
            off.add(obj)
        self.app.settings.set("monitor_disabled", sorted(off))
        self._redraw_rows()
        self._draw()

    # ---- data ----------------------------------------------------------
    def refresh(self, st):
        names = temp_object_names(list(st.keys()))
        if names != self._names:
            self._rebuild(names)
        readings = {}
        for obj in names:
            data = st.get(obj) or {}
            temp, target = data.get("temperature"), data.get("target")
            readings[obj] = temp
            text = "--" if temp is None else f"{temp:.1f}°"
            if target is not None:
                text += f"  → {target:.0f}°" if target else "  → off"
            self._values[obj] = text
        self._redraw_rows()
        now = time.time()
        if now - self._last_sample >= SAMPLE_S:
            self._last_sample = now
            self.history.append((now, {o: t for o, t in readings.items() if t is not None}))
            self._draw()

    # ---- rows ------------------------------------------------------------
    def _rebuild(self, names):
        self.rows.clear()
        self._names = names
        self._colour = {}
        self._rows = {}
        for i, obj in enumerate(names):
            self._colour[obj] = COLOURS[i % len(COLOURS)]
            row = tk.Canvas(self.rows.inner, height=self.sc.px(46), bg=self.t["panel"],
                            highlightthickness=0, bd=0)
            row.pack(fill="x", pady=self.sc.px(3))
            row.bind("<ButtonRelease-1>", lambda _e, o=obj: self._toggle(o))
            row.bind("<Configure>", lambda _e, o=obj: self._draw_row(o))
            self._rows[obj] = row

    def _redraw_rows(self):
        for obj in self._names:
            self._draw_row(obj)

    def _draw_row(self, obj):
        c = self._rows.get(obj)
        if c is None:
            return
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 2:
            return
        on = obj not in self._disabled()
        t = self.t
        if on:
            # KlipperScreen-style light bar on the left edge
            c.create_rectangle(0, 0, self.sc.px(5), h, fill=self._colour[obj], outline="")
        name_fg = t["text"] if on else t["subtext"]
        c.create_text(self.sc.px(14), int(h * 0.32), text=display_name(obj), anchor="w",
                      fill=name_fg, font=self.sc.font(10, "bold"))
        detail = self._values.get(obj, "--") if on else "tap to enable"
        c.create_text(self.sc.px(14), int(h * 0.74), text=detail, anchor="w",
                      fill=t["text"] if on else t["subtext"], font=self.sc.font(10))

    # ---- graph -----------------------------------------------------------
    def _draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 80 or h < 80:
            return
        left, right = self.sc.px(44), self.sc.px(12)
        top, bottom = self.sc.px(12), self.sc.px(24)
        pw, ph = w - left - right, h - top - bottom
        off = self._disabled()
        shown = [n for n in self._names if n not in off]
        samples = list(self.history)
        values = [v for _, d in samples for k, v in d.items() if k in shown]
        lo_v, hi_v = (min(values), max(values)) if values else (20.0, 60.0)
        span = max(15.0, hi_v - lo_v)
        lo = lo_v - 0.1 * span
        hi = lo + 1.2 * span
        now = time.time()
        grid, sub = self.t["border"], self.t["subtext"]
        for i in range(5):
            frac = i / 4
            y = top + ph * (1 - frac)
            c.create_line(left, y, left + pw, y, fill=grid)
            c.create_text(left - self.sc.px(6), y, text=f"{lo + (hi - lo) * frac:.0f}",
                          anchor="e", fill=sub, font=self.sc.font(8))
        for label, age in (("5 min", WINDOW_S), ("2 min", 120), ("now", 0)):
            x = left + pw * (1 - age / WINDOW_S)
            c.create_text(x, h - self.sc.px(4), text=label, anchor="s", fill=sub,
                          font=self.sc.font(8))
        for obj in shown:
            pts = []
            for t, d in samples:
                if obj in d:
                    x = left + pw * (1 - (now - t) / WINDOW_S)
                    y = top + ph * (1 - (d[obj] - lo) / (hi - lo))
                    pts.extend((x, y))
            if len(pts) >= 4:
                c.create_line(*pts, fill=self._colour[obj], width=max(2, self.sc.px(2)))

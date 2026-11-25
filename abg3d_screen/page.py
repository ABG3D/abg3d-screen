"""Base class for tab pages, plus shared helpers."""
import tkinter as tk
from types import SimpleNamespace

from .honeycomb import HexFrame
from .widgets import Meter, RoundButton


def fmt_time(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {secs:02d}s"


class Page(HexFrame):
    def __init__(self, master, app):
        self.app = app
        super().__init__(master, app)
        self.t = app.theme
        self.sc = app.scale
        self.build()

    def px(self, value):
        return self.sc.px(value)

    def font(self, size, weight="normal"):
        return self.sc.font(size, weight)

    def label(self, parent, text, size=12, weight="normal", color=None, bg=None, **kw):
        return tk.Label(parent, text=text, font=self.font(size, weight),
                        fg=color or self.t["text"], bg=bg or parent.cget("bg"), **kw)

    def panel(self, parent, **kw):
        return tk.Frame(parent, bg=self.t["panel"], **kw)

    def button(self, parent, text, command, style="secondary", **kw):
        return RoundButton(parent, text, command, self.app, style=style, **kw)

    def meter(self, parent, height=12):
        return Meter(parent, self.app, height=height)

    def gcode(self, script, message=None):
        self.app.run_async(lambda: self.app.backend.gcode(script), message)

    def temp_card(self, parent, name):
        card = self.panel(parent)
        top = tk.Frame(card, bg=self.t["panel"])
        top.pack(fill="x", padx=self.px(12), pady=(self.px(10), 0))
        self.label(top, name, 11, color=self.t["subtext"], bg=self.t["panel"]).pack(side="left")
        value = self.label(top, "--", 18, "bold", bg=self.t["panel"])
        value.pack(side="right")
        bar = self.meter(card, height=8)
        bar.pack(fill="x", padx=self.px(12), pady=(self.px(6), self.px(10)))
        return SimpleNamespace(frame=card, value=value, bar=bar)

    def set_temp(self, card, data):
        data = data or {}
        cur = float(data.get("temperature") or 0)
        tgt = float(data.get("target") or 0)
        card.value.configure(text=f"{cur:.0f}° / {tgt:.0f}°")
        if tgt <= 0:
            card.bar.set(0, self.t["subtext"])
        elif abs(cur - tgt) <= 3:
            card.bar.set(1, self.t["ok"])
        else:
            card.bar.set(min(1, cur / tgt), self.t["warn"])

    def build(self):
        pass

    def refresh(self, status, online, demo):
        pass

    def on_show(self):
        pass

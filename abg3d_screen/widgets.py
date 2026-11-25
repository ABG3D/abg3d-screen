"""Reusable Tk widgets: rounded buttons, progress meters and cursor helpers."""
import tkinter as tk


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
           x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def shade(hex_colour, factor=0.82):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def apply_cursor(widget, cursor):
    """Set the mouse cursor on a widget and all of its children ('none' hides it)."""
    try:
        widget.configure(cursor=cursor)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        apply_cursor(child, cursor)


STYLE_COLOURS = {"primary": "accent", "secondary": "panel_alt", "danger": "danger",
                 "ok": "ok", "ghost": "panel"}
TEXT_ON_FILL = {"primary", "ok", "danger"}


class RoundButton(tk.Canvas):
    """Touch-friendly rounded button. Fires on release, so a drag-off cancels the tap."""

    def __init__(self, master, text, command, app, style="secondary", height=56,
                 font=14, confirm=False, enabled=True, icon=None):
        self.t = app.theme
        self.sc = app.scale
        self.icon = icon  # optional PhotoImage; drawn above the caption when text is given
        self.base_text = self.text = text
        self.command = command
        self.style = style
        self.font_size = font
        self.confirm = confirm
        self.enabled = enabled
        self._armed = False
        self._down = False
        super().__init__(master, height=self.sc.px(height), width=self.sc.px(60),
                         bg=master.cget("bg"), highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 1 else int(float(self.cget("width")))
        h = self.winfo_height() if self.winfo_height() > 1 else int(float(self.cget("height")))
        t = self.t
        fill = t[STYLE_COLOURS.get(self.style, "panel_alt")]
        fg = t["accent_text"] if self.style in TEXT_ON_FILL else t["text"]
        if not self.enabled:
            fill, fg = t["panel_alt"], t["subtext"]
        elif self._down:
            fill = shade(fill)
        outline = t["border"] if self.style == "ghost" else ""
        round_rect(self, 2, 2, w - 2, h - 2, self.sc.px(14), fill=fill, outline=outline)
        if self.icon is not None and self.text:
            self.create_image(w // 2, int(h * 0.40), image=self.icon)
            self.create_text(w // 2, int(h * 0.80), text=self.text, fill=fg,
                             font=self.sc.font(self.font_size - 3, "bold"), width=max(40, w - 8))
        elif self.icon is not None:
            self.create_image(w // 2, h // 2, image=self.icon)
        else:
            self.create_text(w // 2, h // 2, text=self.text, fill=fg,
                             font=self.sc.font(self.font_size, "bold"),
                             width=max(40, w - 16), justify="center")

    def set_icon(self, image):
        if image is not self.icon:
            self.icon = image
            self.draw()

    def set_text(self, text):
        if text != self.base_text:
            self.base_text = self.text = text
            self.draw()

    def set_enabled(self, on):
        if on != self.enabled:
            self.enabled = on
            self.draw()

    def set_style(self, style):
        if style != self.style:
            self.style = style
            self.draw()

    def _press(self, _event):
        if self.enabled:
            self._down = True
            self.draw()

    def _release(self, event):
        if not self.enabled or not self._down:
            return
        self._down = False
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if not inside:
            self.draw()
            return
        if self.confirm and not self._armed:
            self._armed = True
            self.text = "Tap again to confirm"
            self.draw()
            self.after(3000, self._disarm)
            return
        self._disarm()
        if self.command:
            self.command()

    def _disarm(self):
        self._armed = False
        self.text = self.base_text
        try:
            self.draw()
        except tk.TclError:
            pass  # widget was destroyed while the confirm timer was pending


class Meter(tk.Canvas):
    """Thin rounded progress bar."""

    def __init__(self, master, app, height=12):
        self.t = app.theme
        self.sc = app.scale
        self.frac = 0.0
        self.color = self.t["accent"]
        super().__init__(master, height=self.sc.px(height), bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda _e: self.draw())

    def set(self, frac, color=None):
        frac = max(0.0, min(1.0, float(frac)))
        color = color or self.t["accent"]
        if frac == self.frac and color == self.color:
            return
        self.frac, self.color = frac, color
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            return
        r = h // 2
        round_rect(self, 0, 0, w, h, r, fill=self.t["panel_alt"], outline="")
        fill_w = int(w * self.frac)
        if fill_w >= h:
            round_rect(self, 0, 0, fill_w, h, r, fill=self.color, outline="")


class Switch(tk.Canvas):
    """On/off toggle: label on the left, sliding switch on the right. Fires on tap."""

    def __init__(self, master, text, command, app, on=False, height=44):
        self.t = app.theme
        self.sc = app.scale
        self.text = text
        self.command = command
        self.on = on
        super().__init__(master, height=self.sc.px(height), width=self.sc.px(220),
                         bg=master.cget("bg"), highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 1 else int(float(self.cget("width")))
        h = self.winfo_height() if self.winfo_height() > 1 else int(float(self.cget("height")))
        t = self.t
        track_w, track_h = self.sc.px(52), self.sc.px(26)
        x2 = w - self.sc.px(6)
        x1 = x2 - track_w
        y1 = (h - track_h) // 2
        y2 = y1 + track_h
        if self.on:
            round_rect(self, x1, y1, x2, y2, track_h // 2, fill=t["ok"], outline="")
        else:
            round_rect(self, x1, y1, x2, y2, track_h // 2, fill=t["panel_alt"], outline=t["border"])
        inset = self.sc.px(3)
        d = track_h - 2 * inset
        kx = x2 - inset - d if self.on else x1 + inset
        self.create_oval(kx, y1 + inset, kx + d, y1 + inset + d, fill="#ffffff", outline="")
        self.create_text(self.sc.px(8), h // 2, text=self.text, anchor="w", fill=t["text"],
                         font=self.sc.font(12, "bold"))
        self.create_text(x1 - self.sc.px(10), h // 2, text="ON" if self.on else "OFF", anchor="e",
                         fill=t["ok"] if self.on else t["subtext"], font=self.sc.font(10, "bold"))

    def _release(self, event):
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.on = not self.on
            self.draw()
            if self.command:
                self.command()

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
        if drag_moved():
            self.draw()
            return
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


_LISTS = []                       # every live ScrollList
_DRAG = {"owner": None, "start": 0, "last": 0, "moved": False}


def _owner_of(widget):
    w = widget
    while w is not None:
        for lst in _LISTS:
            if w is lst.inner or w is lst.viewport:
                return lst
        w = getattr(w, "master", None)
    return None


def drag_press(event):
    """Installed once on the root window. Records a touch that starts inside a scroll list."""
    if not isinstance(event.widget, tk.Misc):
        return
    _DRAG.update(owner=_owner_of(event.widget), start=event.y_root, last=event.y_root, moved=False)


def drag_motion(event):
    owner = _DRAG["owner"]
    if owner is None:
        return
    y = event.y_root
    if not _DRAG["moved"]:
        if abs(_DRAG["start"] - y) < owner.sc.px(8):
            return  # still a tap
        _DRAG["moved"] = True
    owner.offset = max(0, min(owner.max_offset, owner.offset + _DRAG["last"] - y))
    _DRAG["last"] = y
    owner._place()


def drag_moved():
    """True when the current touch has become a drag. Buttons then ignore the release."""
    return _DRAG["moved"]


class ScrollList(tk.Frame):
    """Scrollable container: clipped viewport, thumb track, up/down buttons and touch drag.

    visible_rows=N shows N rows of fixed height. visible_rows=None fills the parent, and any
    widget packed into .inner scrolls. Taps are unaffected unless the touch becomes a drag.
    """

    def __init__(self, master, app, visible_rows=3, row_h=36, bg=None):
        self.app = app
        self.t = app.theme
        self.sc = app.scale
        bg = bg or self.t["panel_alt"]
        super().__init__(master, bg=bg)
        self.row_base = row_h
        self.row_px = self.sc.px(row_h) + 2 * self.sc.px(3)
        self.fixed = visible_rows is not None
        self.clip_h = self.row_px * visible_rows if self.fixed else 0
        self.offset = 0
        self.max_offset = 0
        column = tk.Frame(self, bg=bg, width=self.sc.px(44))
        column.pack(side="right", fill="y")
        column.pack_propagate(False)
        if self.fixed:
            self.viewport = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=self.clip_h)
        else:
            self.viewport = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=1)
        self.viewport.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.viewport, bg=bg)
        self.win = self.viewport.create_window(0, 0, window=self.inner, anchor="nw")
        self.viewport.bind("<Configure>", lambda _e: self._fit())
        self.inner.bind("<Configure>", lambda _e: self._fit())
        RoundButton(column, "\u25b2", lambda: self.yview_scroll(-1, "units"), app, "secondary",
                    height=36, font=10).pack(fill="x", padx=2, pady=(2, 0))
        self.track = tk.Canvas(column, bg=bg, highlightthickness=0, bd=0)
        self.track.pack(fill="both", expand=True, padx=12, pady=4)
        self.track.bind("<Configure>", lambda _e: self._thumb())
        RoundButton(column, "\u25bc", lambda: self.yview_scroll(1, "units"), app, "secondary",
                    height=36, font=10).pack(fill="x", padx=2, pady=(0, 2))
        _LISTS.append(self)

    def destroy(self):
        if self in _LISTS:
            _LISTS.remove(self)
        super().destroy()

    def _clip(self):
        return self.clip_h if self.fixed else max(1, self.viewport.winfo_height())

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.offset = 0
        self._fit()

    def add(self, text, command, style="secondary"):
        btn = RoundButton(self.inner, text, command, self.app, style, height=self.row_base, font=10)
        btn.pack(fill="x", padx=self.sc.px(4), pady=self.sc.px(3))
        return btn

    def yview_scroll(self, number, what="units"):
        """Scroll by rows ('units') or by one visible page ('pages'), like Tk's yview_scroll."""
        step = self.row_px if what == "units" else self._clip()
        self.offset = max(0, min(self.max_offset, self.offset + number * step))
        self._place()

    def _fit(self):
        width = self.viewport.winfo_width()
        if width > 4:
            self.viewport.itemconfigure(self.win, width=width)
        self.max_offset = max(0, self.inner.winfo_reqheight() - self._clip())
        self.offset = min(self.offset, self.max_offset)
        self._place()

    def _place(self):
        self.viewport.coords(self.win, 0, -self.offset)
        self._thumb()

    def _thumb(self):
        c = self.track
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 4 or h <= 4:
            return
        clip = self._clip()
        content = self.max_offset + clip
        thumb = max(12, int(h * clip / content))
        y = int((h - thumb) * (self.offset / self.max_offset)) if self.max_offset else 0
        round_rect(c, 2, y, w - 2, y + thumb, 6, fill=self.t["accent"], outline="")


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
        if drag_moved():
            return
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.on = not self.on
            self.draw()
            if self.command:
                self.command()

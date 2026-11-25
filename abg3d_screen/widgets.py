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
    drag_guard = None  # set by a scrollable parent; True means a drag happened, so no tap

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
        if self.drag_guard and self.drag_guard():
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


class ScrollList(tk.Frame):
    """Touch-scrollable list: clipped viewport, thumb track, up/down buttons and drag to scroll.

    A press that moves further than a few pixels becomes a drag. Buttons inside the list
    then ignore that release, so scrolling never fires a tap.
    """

    def __init__(self, master, app, visible_rows=3, row_h=36, bg=None):
        self.app = app
        self.t = app.theme
        self.sc = app.scale
        bg = bg or self.t["panel_alt"]
        super().__init__(master, bg=bg)
        self.row_base = row_h
        self.row_px = self.sc.px(row_h) + 2 * self.sc.px(3)
        self.clip_h = self.row_px * visible_rows
        self.offset = 0
        self.max_offset = 0
        self.moved = False
        self._start_y = None
        self._last_y = None
        column = tk.Frame(self, bg=bg, width=self.sc.px(44))
        column.pack(side="right", fill="y")
        column.pack_propagate(False)
        self.viewport = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=self.clip_h)
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
        self._bind_drag(self.viewport)
        self._bind_drag(self.inner)

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.offset = 0
        self._fit()

    def add(self, text, command, style="secondary"):
        btn = RoundButton(self.inner, text, command, self.app, style, height=self.row_base, font=10)
        btn.pack(fill="x", padx=self.sc.px(4), pady=self.sc.px(3))
        btn.drag_guard = lambda: self.moved
        self._bind_drag(btn)
        return btn

    def yview_scroll(self, number, what="units"):
        """Scroll by rows ('units') or by a whole visible page ('pages'), like Tk's yview_scroll."""
        step = self.row_px if what == "units" else self.clip_h
        self.offset = max(0, min(self.max_offset, self.offset + number * step))
        self._place()

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._press, add="+")
        widget.bind("<B1-Motion>", self._motion, add="+")

    def _press(self, event):
        self.moved = False
        self._start_y = self._last_y = event.y_root

    def _motion(self, event):
        if self._last_y is None:
            return
        if not self.moved and abs(self._start_y - event.y_root) < self.sc.px(8):
            return
        self.moved = True
        self.offset = max(0, min(self.max_offset, self.offset + self._last_y - event.y_root))
        self._last_y = event.y_root
        self._place()

    def _fit(self):
        width = self.viewport.winfo_width()
        if width > 4:
            self.viewport.itemconfigure(self.win, width=width)
        self.max_offset = max(0, self.inner.winfo_reqheight() - self.clip_h)
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
        content = self.max_offset + self.clip_h
        thumb = max(12, int(h * self.clip_h / content))
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
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.on = not self.on
            self.draw()
            if self.command:
                self.command()

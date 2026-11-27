"""Shared touch widgets: buttons, icon buttons, keypad, keyboard, Cairo graph, thumbnails."""
import math
import posixpath
import time
import urllib.parse
from collections import OrderedDict

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from .icons import Icon  # noqa: E402

GRAPH_COLORS = [(1.00, 0.38, 0.25), (0.27, 0.60, 1.00), (0.33, 0.85, 0.45), (0.98, 0.76, 0.20),
                (0.76, 0.47, 0.98), (0.20, 0.86, 0.86), (0.98, 0.45, 0.70), (0.70, 0.70, 0.70)]

# populated by App from theme.Ui before any widget is built
M = {"icon": 24, "icon_s": 18, "touch": 48, "sp": 6, "pad": 8, "small": False}


# ------------------------------------------------------------------ helpers
def add_cls(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        if c:
            ctx.add_class(c)
    return widget


def rm_cls(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.remove_class(c)
    return widget


def set_cls(widget, cls, on):
    (add_cls if on else rm_cls)(widget, cls)


def Btn(label, cb=None, *classes, wrap=False):
    b = Gtk.Button(label=label)
    b.set_can_focus(False)
    child = b.get_child()
    if isinstance(child, Gtk.Label):
        if wrap:
            child.set_line_wrap(True)
            child.set_justify(Gtk.Justification.CENTER)
        else:
            child.set_ellipsize(Pango.EllipsizeMode.END)
    add_cls(b, *classes)
    if cb:
        b.connect("clicked", lambda _w: cb())
    return b


def icon_content(icon, label=None, vertical=False, size=None):
    ic = Icon(icon, size or M["icon"])
    if not label:
        return ic
    lb = Gtk.Label(label=label)
    lb.set_ellipsize(Pango.EllipsizeMode.END)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                  spacing=2 if vertical else M["sp"])
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    box.pack_start(ic, False, False, 0)
    box.pack_start(lb, False, False, 0)
    box.label = lb
    box.icon = ic
    return box


def IconBtn(icon, label=None, cb=None, *classes, vertical=False, size=None, toggle=False):
    b = Gtk.ToggleButton() if toggle else Gtk.Button()
    b.set_can_focus(False)
    b.add(icon_content(icon, label, vertical, size))
    add_cls(b, "iconbtn" if not label else "iconlabel", *classes)
    if cb:
        b.connect("toggled" if toggle else "clicked", lambda w: cb(w) if toggle else cb())
    return b


def set_btn(btn, icon=None, label=None):
    """Update the icon and/or label of a button built with IconBtn."""
    c = btn.get_child()
    ic = c if isinstance(c, Icon) else getattr(c, "icon", None)
    lb = getattr(c, "label", None)
    if icon and ic:
        ic.set_icon(icon)
    if label is not None and lb:
        lb.set_text(label)


def Lbl(text="", *classes, xalign=0.0, ellipsize=False, wrap=False):
    lb = Gtk.Label(label=text)
    lb.set_xalign(xalign)
    if ellipsize:
        lb.set_ellipsize(Pango.EllipsizeMode.END)
    if wrap:
        lb.set_line_wrap(True)
        lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    add_cls(lb, *classes)
    return lb


def HBox(*children, spacing=None, homogeneous=False, expand=None):
    return _box(Gtk.Orientation.HORIZONTAL, children, spacing, homogeneous, expand)


def VBox(*children, spacing=None, homogeneous=False, expand=None):
    return _box(Gtk.Orientation.VERTICAL, children, spacing, homogeneous, expand)


def _box(orient, children, spacing, homogeneous, expand):
    b = Gtk.Box(orientation=orient, spacing=M["sp"] if spacing is None else spacing)
    b.set_homogeneous(homogeneous)
    for i, c in enumerate(children):
        if c is None:
            continue
        ex = homogeneous or (expand is not None and i in expand)
        b.pack_start(c, ex, ex, 0)
    return b


class DragScroll:
    """Touch/mouse drag-to-scroll (+ fling) for a Gtk.ScrolledWindow via Gtk.GestureDrag.

    Works for panels that report as a touchscreen *and* for resistive/USB panels that only
    emulate a mouse (where GTK's built-in kinetic scrolling never activates). Taps are left
    alone; once a drag passes the threshold the sequence is claimed, so the button under the
    finger is cancelled instead of clicked.
    """

    def __init__(self, sw, horizontal):
        self.sw, self.horizontal = sw, horizontal
        self.dragging = False
        self.start = 0.0
        self.samples = []
        self.velocity = 0.0
        self.fling_src = None
        self.threshold = max(6, int(M["touch"] * 0.18))
        g = Gtk.GestureDrag.new(sw)
        g.set_button(0)
        g.set_touch_only(False)
        g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        g.connect("drag-begin", self._begin)
        g.connect("drag-update", self._update)
        g.connect("drag-end", self._end)
        g.connect("cancel", lambda *_: self._stop())
        self.gesture = g

    def _adj(self):
        return self.sw.get_hadjustment() if self.horizontal else self.sw.get_vadjustment()

    def _set(self, value):
        a = self._adj()
        a.set_value(max(a.get_lower(), min(value, a.get_upper() - a.get_page_size())))

    def _stop(self):
        if self.fling_src:
            GLib.source_remove(self.fling_src)
            self.fling_src = None

    def _begin(self, _g, _x, _y):
        self._stop()
        self.dragging = False
        self.start = self._adj().get_value()
        self.samples = [(time.monotonic(), 0.0)]

    def _update(self, g, dx, dy):
        d = dx if self.horizontal else dy
        if not self.dragging:
            a = self._adj()
            if abs(d) < self.threshold or a.get_upper() - a.get_page_size() <= a.get_lower():
                return
            self.dragging = True
            g.set_state(Gtk.EventSequenceState.CLAIMED)
        self._set(self.start - d)
        now = time.monotonic()
        self.samples.append((now, d))
        self.samples = [smp for smp in self.samples if now - smp[0] < 0.12]

    def _end(self, _g, dx, dy):
        if not self.dragging:
            return
        self.dragging = False
        if len(self.samples) >= 2:
            (t0, d0), (t1, d1) = self.samples[0], self.samples[-1]
            if t1 - t0 > 0.005:
                self.velocity = -(d1 - d0) / (t1 - t0) / 1000.0  # px per ms
                if abs(self.velocity) > 0.25:
                    self.fling_src = GLib.timeout_add(16, self._fling)

    def _fling(self):
        a = self._adj()
        before = a.get_value()
        self._set(before + self.velocity * 16)
        self.velocity *= 0.94
        if abs(self.velocity) < 0.05 or a.get_value() == before:
            self.fling_src = None
            return False
        return True


def Scroller(child, horizontal=False, vertical=True):
    """Drag-scrollable window (transparent so the honeycomb shows through).

    vexpand=True, propagate-natural-height=False and AUTOMATIC policies: the window never asks
    for its content's height, so pages always fit the screen and their content scrolls instead.
    """
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC if horizontal else Gtk.PolicyType.NEVER,
                  Gtk.PolicyType.AUTOMATIC if vertical else Gtk.PolicyType.NEVER)
    sw.set_propagate_natural_height(False)
    sw.set_propagate_natural_width(False)
    sw.set_min_content_height(0)
    sw.set_kinetic_scrolling(False)       # replaced by DragScroll (works for mouse-emulating panels too)
    sw.set_capture_button_press(False)
    sw.set_overlay_scrolling(False)
    sw.set_hexpand(True)
    sw.set_vexpand(vertical)
    sw.add(child)
    vp = sw.get_child()
    if isinstance(vp, Gtk.Viewport):
        vp.set_shadow_type(Gtk.ShadowType.NONE)
    sw.drag_scroll = DragScroll(sw, horizontal and not vertical)
    return sw


def radio_row(options, active, cb, fmt=str, icons=None):
    """Row of mutually exclusive toggle buttons. cb(value)."""
    box = HBox(spacing=max(2, M["sp"] // 2), homogeneous=True)
    group = None
    btns = {}
    for val in options:
        rb = Gtk.RadioButton.new_from_widget(group)
        if icons and icons.get(val):
            rb.add(icon_content(icons[val], fmt(val) if fmt else None))
        else:
            rb.add(Lbl(fmt(val), xalign=0.5, ellipsize=True))
        rb.set_mode(False)
        rb.set_can_focus(False)
        group = group or rb
        btns[val] = rb
        box.pack_start(rb, True, True, 0)
    if active in btns:
        btns[active].set_active(True)
    for val, rb in btns.items():
        rb.connect("toggled", lambda w, v=val: w.get_active() and cb(v))
    return box, btns


def subtabs(pages, on_change=None, extra=None):
    """Icon-only sub-tab bar + stack. pages: [(key, icon, widget)]. Returns (box, stack, buttons)."""
    stack = Gtk.Stack()
    stack.set_transition_type(Gtk.StackTransitionType.NONE)
    stack.set_hhomogeneous(False)
    stack.set_vhomogeneous(False)
    tabs = HBox(spacing=max(2, M["sp"] // 2), homogeneous=True)
    group = None
    btns = {}
    for key, icon, widget in pages:
        stack.add_named(widget, key)
        rb = Gtk.RadioButton.new_from_widget(group)
        rb.add(Icon(icon, M["icon"]))
        rb.set_mode(False)
        rb.set_can_focus(False)
        add_cls(rb, "subtab")
        group = group or rb
        btns[key] = rb
        rb.connect("toggled", lambda w, k=key: w.get_active() and (stack.set_visible_child_name(k),
                                                                     on_change and on_change(k)))
        tabs.pack_start(rb, True, True, 0)
    bar = HBox(tabs, extra, expand=(0,)) if extra else tabs
    add_cls(bar, "subtabs")
    box = VBox(bar, stack, expand=(1,))
    return box, stack, btns


def Section(text, icon=None):
    if not icon:
        return Lbl(text, "section")
    box = HBox(Icon(icon, M["icon_s"]), Lbl(text, "section"), spacing=M["sp"])
    add_cls(box, "section-row")
    return box


def Row(*children, expand=(0,)):
    r = HBox(*children, expand=expand)
    add_cls(r, "row")
    return r


def fmt_time(sec):
    if sec is None or sec < 0:
        return "--"
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    if h:
        return "%dh %02dm" % (h, m)
    if m:
        return "%dm %02ds" % (m, s)
    return "%ds" % s


def fmt_len(mm):
    if not mm:
        return "--"
    return "%.2f m" % (mm / 1000.0) if mm >= 1000 else "%.0f mm" % mm


def fmt_num(v):
    return ("%.3f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def display_name(obj):
    if obj == "extruder":
        return "Hotend"
    if obj.startswith("extruder") and obj[8:].isdigit():
        return "Hotend %s" % obj[8:]
    if obj == "heater_bed":
        return "Bed"
    if obj == "fan":
        return "Part Fan"
    name = obj.split(" ", 1)[-1]
    return name.replace("_", " ").title()


def set_temp_cmd(obj, target):
    target = max(0, float(target))
    if obj.startswith("temperature_fan "):
        return "SET_TEMPERATURE_FAN_TARGET TEMPERATURE_FAN=%s TARGET=%g" % (obj.split(" ", 1)[1], target)
    heater = obj.split(" ", 1)[1] if obj.startswith("heater_generic ") else obj
    return "SET_HEATER_TEMPERATURE HEATER=%s TARGET=%g" % (heater, target)


# ------------------------------------------------------------------- modals
def confirm(app, text, cb, ok="Confirm", danger=False):
    box = VBox()
    lb = Lbl(text, "modal-title", xalign=0.5, wrap=True)
    lb.set_max_width_chars(36)
    box.pack_start(lb, False, False, 0)
    holder = {}

    def yes():
        app.close_modal(holder["m"])
        cb()
    row = HBox(IconBtn("close", "Cancel", lambda: app.close_modal(holder["m"])),
               IconBtn("warning" if danger else "check", ok, yes, "danger" if danger else "primary"),
               homogeneous=True)
    box.pack_start(row, False, False, 0)
    holder["m"] = app.show_modal(box)


class Keypad(Gtk.Box):
    """Numeric keypad shown as an in-window modal. cb(float)."""

    def __init__(self, app, title, initial, cb, allow_neg=False, decimals=True, maxval=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=M["sp"])
        self.app, self.cb, self.maxval = app, cb, maxval
        self.text = "" if initial in (None, "") else fmt_num(initial)
        self.fresh = True
        self.disp = Lbl(self.text or "0", "keypad-display", xalign=1.0)
        title_lbl = Lbl(title, "modal-title", xalign=0.5, wrap=True)
        if M["small"] or app.ui.h < 520:
            title_lbl.set_max_width_chars(10)
            self.pack_start(HBox(title_lbl, self.disp, expand=(1,)), False, False, 0)
        else:
            self.pack_start(title_lbl, False, False, 0)
            self.pack_start(self.disp, False, False, 0)
        grid = Gtk.Grid(row_spacing=M["sp"], column_spacing=M["sp"])
        grid.set_row_homogeneous(True)
        grid.set_column_homogeneous(True)
        keys = ["7", "8", "9", "4", "5", "6", "1", "2", "3",
                "-" if allow_neg else "", "0", "." if decimals else ""]
        for i, k in enumerate(keys):
            if k:
                grid.attach(Btn(k, lambda k=k: self._key(k), "key"), i % 3, i // 3, 1, 1)
        grid.attach(IconBtn("back", None, self._back, "key"), 3, 0, 1, 1)
        grid.attach(Btn("C", self._clear, "key"), 3, 1, 1, 1)
        grid.attach(IconBtn("close", None, lambda: app.close_modal(self.modal), "key"), 3, 2, 1, 1)
        grid.attach(IconBtn("check", None, self._ok, "primary", "key"), 3, 3, 1, 1)
        self.pack_start(grid, True, True, 0)
        self.modal = app.show_modal(self)

    def _key(self, k):
        if self.fresh:
            self.text, self.fresh = "", False
        if k == "-":
            self.text = self.text[1:] if self.text.startswith("-") else "-" + self.text
        elif k == "." and "." in self.text:
            return
        elif len(self.text) < 9:
            self.text += k
        self.disp.set_text(self.text or "0")

    def _back(self):
        self.fresh = False
        self.text = self.text[:-1]
        self.disp.set_text(self.text or "0")

    def _clear(self):
        self.fresh = False
        self.text = ""
        self.disp.set_text("0")

    def _ok(self):
        try:
            val = float(self.text) if self.text not in ("", "-", ".", "-.") else 0.0
        except ValueError:
            return
        if self.maxval is not None and val > self.maxval:
            self.app.toast("Maximum is %g" % self.maxval, error=True)
            return
        self.app.close_modal(self.modal)
        self.cb(val)


class Keyboard(Gtk.Box):
    """On-screen QWERTY keyboard typing into a Gtk.Entry."""
    LAYOUTS = {
        "abc": ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm_.-"],
        "sym": ["1234567890", "!@#$%^&*()", "=+[]{}:;\"/", "<>,?\\|~`_ "],
    }

    def __init__(self, entry, on_enter=None, on_hide=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=max(2, M["sp"] // 2))
        add_cls(self, "keyboard")
        self.entry, self.on_enter, self.on_hide = entry, on_enter, on_hide
        self.layout, self.upper = "abc", True
        self.keys = []
        for _r in range(4):
            row = HBox(spacing=max(2, M["sp"] // 2), homogeneous=True)
            rk = []
            for _c in range(10):
                b = Btn("", None, "kbkey")
                b.connect("clicked", self._press)
                row.pack_start(b, True, True, 0)
                rk.append(b)
            self.keys.append(rk)
            self.pack_start(row, True, True, 0)
        self.shift = Btn("ABC", self._toggle_case, "kbkey")
        self.sym = Btn("#+=", self._toggle_sym, "kbkey")
        kids = [self.shift, self.sym, Btn("space", lambda: self._type(" "), "kbkey"),
                IconBtn("back", None, self._back, "kbkey"),
                IconBtn("send" if on_enter else "check", None, self._enter, "kbkey", "primary")]
        if on_hide:
            kids.append(IconBtn("keyboard_hide", None, on_hide, "kbkey"))
        bottom = HBox(*kids, spacing=max(2, M["sp"] // 2), expand=(2,))
        self.pack_start(bottom, True, True, 0)
        self._relabel()

    def _relabel(self):
        rows = self.LAYOUTS[self.layout]
        for r, rk in enumerate(self.keys):
            for c, b in enumerate(rk):
                ch = rows[r][c] if c < len(rows[r]) else ""
                if self.layout == "abc" and self.upper:
                    ch = ch.upper()
                b.set_label(ch)
                b.set_sensitive(bool(ch.strip()) or ch == " ")
        self.shift.set_label("ABC" if self.upper else "abc")
        self.sym.set_label("ABC" if self.layout == "sym" else "#+=")

    def _press(self, btn):
        self._type(btn.get_label())

    def _pos(self):
        t = self.entry.get_text()
        p = self.entry.get_position()
        return t, (len(t) if p < 0 or p > len(t) else p)

    def _type(self, ch):
        if not ch:
            return
        t, p = self._pos()
        self.entry.set_text(t[:p] + ch + t[p:])
        self.entry.set_position(p + len(ch))

    def _back(self):
        t, p = self._pos()
        if p > 0:
            self.entry.set_text(t[:p - 1] + t[p:])
            self.entry.set_position(p - 1)

    def _enter(self):
        if self.on_enter:
            self.on_enter()

    def _toggle_case(self):
        self.upper = not self.upper
        self._relabel()

    def _toggle_sym(self):
        self.layout = "abc" if self.layout == "sym" else "sym"
        self._relabel()


def ask_text(app, title, initial, cb, password=False):
    """Modal text entry with on-screen keyboard. cb(str)."""
    entry = Gtk.Entry()
    entry.set_text(initial or "")
    entry.set_visibility(not password)
    entry.set_hexpand(True)
    holder = {}

    def ok():
        txt = entry.get_text()
        app.close_modal(holder["m"])
        cb(txt)
    kb = Keyboard(entry, on_enter=ok, on_hide=lambda: app.close_modal(holder["m"]))
    kids = [Lbl(title, "modal-title", ellipsize=True), entry]
    if password:
        show = IconBtn("lock", None, lambda w: entry.set_visibility(w.get_active()), toggle=True)
        kids.append(show)
    box = VBox(HBox(*kids, expand=(1,)), kb, expand=(1,))
    box.set_size_request(int(app.ui.w * 0.94), -1)
    holder["m"] = app.show_modal(box, valign=Gtk.Align.END)
    entry.set_position(-1)


# ------------------------------------------------------------------- graph
class TempGraph(Gtk.DrawingArea):
    """Cairo temperature history graph fed by TempHistory; honours hidden series."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.h = app.history
        self.set_size_request(80, 40)
        add_cls(self, "graph")
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        ctx = self.get_style_context()
        fg = ctx.get_color(ctx.get_state())
        hidden = set(self.app.settings.get("graph_hidden", []))
        n = self.h.size
        series = [(i, name, self.h.series[name]) for i, name in enumerate(self.h.order)
                  if self.h.series.get(name) and name not in hidden]
        top = 50.0
        for _, _, d in series:
            for t, tg in d:
                if t > top:
                    top = t
                if tg > top:
                    top = tg
        top = math.ceil((top + 5) / 50.0) * 50
        fsz = max(8, M.get("fs_s", 10) - 1)
        L, R, T, B = fsz * 3, 4, 4, fsz + 5
        pw, ph = W - L - R, H - T - B
        if pw < 20 or ph < 20:
            return
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(fsz)
        cr.set_line_width(1)
        step = 50 if top <= 300 else 100
        if ph < 90 and top > 150:
            step *= 2
        for v in range(0, int(top) + 1, step):
            y = round(T + ph - v / top * ph) + 0.5
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            cr.move_to(L, y)
            cr.line_to(W - R, y)
            cr.stroke()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.move_to(1, y + fsz / 2.5)
            cr.show_text(str(v))
        mins = n // 60
        for m in range(0, mins + 1, 2 if pw > 260 else 5):
            x = L + pw - (m * 60.0 / max(1, n - 1)) * pw
            if x < L + 8:
                break
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.07)
            cr.move_to(round(x) + 0.5, T)
            cr.line_to(round(x) + 0.5, T + ph)
            cr.stroke()
            if m:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.5)
                cr.move_to(x - fsz, H - 3)
                cr.show_text("-%dm" % m)
        dx = pw / float(max(1, n - 1))
        for i, name, d in series:
            r, g, b = GRAPH_COLORS[i % len(GRAPH_COLORS)]
            cnt = len(d)
            x0 = L + pw - (cnt - 1) * dx
            heater = self.h.has_target(name)
            if heater and any(tg > 0 for _, tg in d):
                cr.set_source_rgba(r, g, b, 0.55)
                cr.set_dash([4, 4])
                cr.set_line_width(1)
                for k, (_, tg) in enumerate(d):
                    y = T + ph - min(tg, top) / top * ph
                    (cr.line_to if k else cr.move_to)(x0 + k * dx, y)
                cr.stroke()
                cr.set_dash([])
            cr.set_source_rgba(r, g, b, 1.0 if heater else 0.7)
            cr.set_line_width(2 if heater else 1.3)
            for k, (t, _) in enumerate(d):
                y = T + ph - min(max(t, 0), top) / top * ph
                (cr.line_to if k else cr.move_to)(x0 + k * dx, y)
            cr.stroke()


class ActiveBar(Gtk.DrawingArea):
    """KlipperScreen-style vertical colour bar marking a sensor active in the graph."""

    def __init__(self, color):
        super().__init__()
        self.color = color
        self.active = True
        self.set_size_request(max(5, M["sp"]), -1)
        self.connect("draw", self._draw)

    def set_active(self, on):
        self.active = on
        self.queue_draw()

    def _draw(self, _w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        r = W / 2.0
        cr.new_sub_path()
        cr.arc(r, r + 2, r, math.pi, 0)
        cr.arc(r, H - r - 2, r, 0, math.pi)
        cr.close_path()
        rr, g, b = self.color
        if self.active:
            cr.set_source_rgba(rr, g, b, 1.0)
            cr.fill()
        else:
            cr.set_source_rgba(rr, g, b, 0.45)
            cr.set_line_width(1.2)
            cr.stroke()


class Dropdown(Gtk.Box):
    """Touch dropdown: header button reveals a height-limited kinetic scroll list."""

    def __init__(self, items, active, cb, max_h=200):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=max(2, M["sp"] // 2))
        self.items, self.cb = items, cb
        self.head_lbl = Lbl("", xalign=0.0, ellipsize=True)
        head = Gtk.Button()
        head.set_can_focus(False)
        head.add(HBox(self.head_lbl, Icon("down", M["icon_s"]), expand=(0,)))
        head.connect("clicked", lambda _b: self.rev.set_reveal_child(not self.rev.get_reveal_child()))
        add_cls(head, "dropdown")
        # the list scrolls with the page it sits in (no nested scrolled window to fight over drags)
        self.list = VBox(spacing=max(2, M["sp"] // 2))
        add_cls(self.list, "dropdown-list")
        self.btns = {}
        for key, label in items:
            b = Btn(label, lambda k=key: self._pick(k), "dropdown-item")
            self.btns[key] = b
            self.list.pack_start(b, False, False, 0)
        self.rev = Gtk.Revealer()
        self.rev.set_transition_type(Gtk.RevealerTransitionType.NONE)
        self.rev.add(self.list)
        self.pack_start(head, False, False, 0)
        self.pack_start(self.rev, False, False, 0)
        self._mark(active)

    def _mark(self, key):
        self.head_lbl.set_text(dict(self.items).get(key, key))
        for k, b in self.btns.items():
            set_cls(b, "selected", k == key)

    def _pick(self, key):
        self._mark(key)
        self.rev.set_reveal_child(False)
        self.cb(key)


# --------------------------------------------------------------- thumbnails
def pick_thumb(thumbs, size):
    thumbs = [t for t in (thumbs or []) if t.get("relative_path")]
    if not thumbs:
        return None
    thumbs.sort(key=lambda t: t.get("width", 0))
    for t in thumbs:
        if t.get("width", 0) >= size:
            return t
    return thumbs[-1]


class ThumbCache:
    """Small LRU of scaled pixbufs; fetched on a single background HTTP worker."""

    def __init__(self, mr, maxsize=48):
        self.mr, self.maxsize = mr, maxsize
        self.cache = OrderedDict()
        self.pending = {}

    def load(self, gcode_path, thumbs, size, cb):
        t = pick_thumb(thumbs, size)
        if not t or size <= 0:
            cb(None)
            return
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(gcode_path), t["relative_path"]))
        key = (rel, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            cb(self.cache[key])
            return
        if key in self.pending:
            self.pending[key].append(cb)
            return
        self.pending[key] = [cb]
        self.mr.http("GET", "/server/files/gcodes/" + urllib.parse.quote(rel), raw=True, q="thumb",
                     cb=lambda data, err: self._done(key, size, data, err))

    def _done(self, key, size, data, err):
        pb = None
        if data and not err:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                src = loader.get_pixbuf()
                w, h = src.get_width(), src.get_height()
                s = min(size / float(w), size / float(h))
                pb = src.scale_simple(max(1, int(w * s)), max(1, int(h * s)), GdkPixbuf.InterpType.BILINEAR)
            except Exception:
                pb = None
        if pb:
            self.cache[key] = pb
            while len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)
        for cb in self.pending.pop(key, []):
            try:
                cb(pb)
            except Exception:
                pass

    def clear(self):
        self.cache.clear()


class Debounce:
    """Run fn(value) after `ms` of quiet; tracks recent user interaction."""

    def __init__(self, fn, ms=250):
        self.fn, self.ms = fn, ms
        self.src = None
        self.value = None
        self.last = 0.0

    def __call__(self, value):
        self.value = value
        self.last = time.monotonic()
        if self.src:
            GLib.source_remove(self.src)
        self.src = GLib.timeout_add(self.ms, self._fire)

    def _fire(self):
        self.src = None
        self.fn(self.value)
        return False

    def busy(self, hold=2.0):
        return self.src is not None or time.monotonic() - self.last < hold

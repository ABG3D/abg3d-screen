"""Resolution-independent Cairo icon set, tinted from the widget's CSS colour.

Every icon is drawn in a 24x24 unit box with round 2-unit strokes, so it scales
cleanly with the display profile and follows the active theme automatically.
"""
import math

import gi
import cairo
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, Gtk  # noqa: E402

PI = math.pi


def _poly(cr, pts, close=False):
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    if close:
        cr.close_path()


def _line(cr, x1, y1, x2, y2):
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()


def _text(cr, ch, x, y, size, bold=True):
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    ext = cr.text_extents(ch)
    cr.move_to(x - ext.width / 2 - ext.x_bearing, y - ext.height / 2 - ext.y_bearing)
    cr.show_text(ch)
    cr.new_path()


def _house(cr, door=True):
    _poly(cr, [(2.5, 11.5), (12, 3.5), (21.5, 11.5)])
    cr.stroke()
    _poly(cr, [(5.5, 9.5), (5.5, 20.5), (18.5, 20.5), (18.5, 9.5)])
    cr.stroke()
    if door:
        _poly(cr, [(10, 20.5), (10, 14.5), (14, 14.5), (14, 20.5)])
        cr.stroke()


def _home(cr):
    _house(cr)


def _home_letter(ch):
    def f(cr):
        _house(cr, door=False)
        _text(cr, ch, 12, 15.2, 8 if len(ch) == 1 else 5.4)
    return f


def _arrow(angle):
    def f(cr):
        cr.save()
        cr.translate(12, 12)
        cr.rotate(angle)
        _line(cr, 0, 8, 0, -8)
        _poly(cr, [(-6.5, -1.5), (0, -8), (6.5, -1.5)])
        cr.stroke()
        cr.restore()
    return f


def _z_arrow(up):
    def f(cr):
        cr.save()
        cr.translate(7, 12)
        if not up:
            cr.scale(1, -1)
        _line(cr, 0, 8, 0, -8)
        _poly(cr, [(-4.5, -3.5), (0, -8), (4.5, -3.5)])
        cr.stroke()
        cr.restore()
        _text(cr, "Z", 17, 12, 11)
    return f


def _control(cr):
    for x, k in ((6, 8), (12, 15), (18, 10)):
        _line(cr, x, 3.5, x, 20.5)
        cr.arc(x, k, 2.6, 0, 2 * PI)
        cr.fill()


def _files(cr):
    _poly(cr, [(2.5, 6), (9, 6), (11, 8.5), (21.5, 8.5), (21.5, 19.5), (2.5, 19.5)], close=True)
    cr.stroke()


def _file(cr):
    _poly(cr, [(5, 2.5), (14, 2.5), (19, 7.5), (19, 21.5), (5, 21.5)], close=True)
    cr.stroke()
    _poly(cr, [(14, 2.5), (14, 7.5), (19, 7.5)])
    cr.stroke()


def _console(cr):
    _line(cr, 4.5, 19.5, 10.5, 4.5)
    _poly(cr, [(13.5, 7.5), (19.5, 12), (13.5, 16.5)])
    cr.stroke()


def _code(cr):
    _poly(cr, [(7.5, 7), (2.5, 12), (7.5, 17)])
    cr.stroke()
    _line(cr, 14, 4, 10, 20)
    _poly(cr, [(16.5, 7), (21.5, 12), (16.5, 17)])
    cr.stroke()


def _power(cr):
    cr.arc(12, 13, 7.8, -PI / 2 + 0.75, 1.5 * PI - 0.75)
    cr.stroke()
    _line(cr, 12, 2.5, 12, 11.5)


def _gear(cr):
    cr.save()
    cr.translate(12, 12)
    cr.set_line_width(3.0)
    for i in range(8):
        a = i * PI / 4
        _line(cr, 7.2 * math.cos(a), 7.2 * math.sin(a), 10 * math.cos(a), 10 * math.sin(a))
    cr.set_line_width(2.0)
    cr.arc(0, 0, 6.6, 0, 2 * PI)
    cr.stroke()
    cr.arc(0, 0, 2.6, 0, 2 * PI)
    cr.stroke()
    cr.restore()


def _spool(cr):
    cr.arc(12, 12, 9.3, 0, 2 * PI)
    cr.stroke()
    cr.arc(12, 12, 3, 0, 2 * PI)
    cr.stroke()
    for a in (0, 2 * PI / 3, 4 * PI / 3):
        _line(cr, 12 + 4.5 * math.cos(a), 12 + 4.5 * math.sin(a), 12 + 7.5 * math.cos(a), 12 + 7.5 * math.sin(a))


def _palette(cr):
    cr.arc(12, 12, 9.5, 0.35, 2 * PI - 0.15)
    cr.curve_to(19, 13, 15, 13.5, 16.5, 17.5)
    cr.stroke()
    for x, y in ((8, 8.5), (12.5, 6.5), (16.5, 8.5), (7.5, 13.5)):
        cr.arc(x, y, 1.6, 0, 2 * PI)
        cr.fill()


def _mouse(cr):
    _rrect(cr, 6.5, 2.5, 11, 19, 5.5)
    cr.stroke()
    _line(cr, 12, 2.5, 12, 9)


def _display(cr):
    _rrect(cr, 2.5, 3.5, 19, 13, 1.5)
    cr.stroke()
    _line(cr, 12, 16.5, 12, 20.5)
    _line(cr, 7.5, 20.5, 16.5, 20.5)


def _hotend(cr):
    _line(cr, 12, 1.5, 12, 4.5)
    _rrect(cr, 5.5, 4.5, 13, 8.5, 1)
    cr.stroke()
    _poly(cr, [(8, 13), (16, 13), (13.5, 18), (10.5, 18)], close=True)
    cr.stroke()
    _line(cr, 12, 18, 12, 21.5)


def _wifi(cr):
    for r in (4.5, 9, 13.5):
        cr.arc(12, 19.5, r, -PI * 0.75, -PI * 0.25)
        cr.stroke()
    cr.arc(12, 19.5, 1.7, 0, 2 * PI)
    cr.fill()


def _hash(cr):
    _line(cr, 9.5, 3.5, 7.5, 20.5)
    _line(cr, 16.5, 3.5, 14.5, 20.5)
    _line(cr, 4, 9, 20.5, 9)
    _line(cr, 3.5, 15, 20, 15)


def _thermo(cr):
    cr.move_to(10, 14.2)
    cr.line_to(10, 5)
    cr.arc(12, 5, 2, PI, 0)
    cr.line_to(14, 14.2)
    cr.stroke()
    cr.arc(12, 17.5, 3.8, -PI / 2 - 0.55, 1.5 * PI + 0.55)
    cr.stroke()
    cr.arc(12, 17.5, 1.8, 0, 2 * PI)
    cr.fill()
    _line(cr, 12, 15.5, 12, 9)


def _move(cr):
    _line(cr, 12, 2.5, 12, 21.5)
    _line(cr, 2.5, 12, 21.5, 12)
    for pts in ([(9, 5.5), (12, 2.5), (15, 5.5)], [(9, 18.5), (12, 21.5), (15, 18.5)],
                [(5.5, 9), (2.5, 12), (5.5, 15)], [(18.5, 9), (21.5, 12), (18.5, 15)]):
        _poly(cr, pts)
        cr.stroke()


def _fan(cr):
    cr.arc(12, 12, 10, 0, 2 * PI)
    cr.stroke()
    for i in range(3):
        a = -PI / 2 + i * 2 * PI / 3
        cr.save()
        cr.translate(12, 12)
        cr.rotate(a)
        cr.move_to(0, 0)
        cr.curve_to(2.5, -2, 6.5, -1.5, 7.5, 1.2)
        cr.curve_to(5, 3, 2, 2.5, 0, 0)
        cr.fill()
        cr.restore()
    cr.arc(12, 12, 1.8, 0, 2 * PI)
    cr.fill()


def _bulb(cr):
    cr.arc(12, 9.5, 6.3, 0.75 * PI, 2.25 * PI)
    cr.line_to(15, 16.5)
    cr.line_to(9, 16.5)
    cr.close_path()
    cr.stroke()
    _line(cr, 9.5, 19, 14.5, 19)
    _line(cr, 10.5, 21.5, 13.5, 21.5)


def _motors_off(cr):
    _rrect(cr, 3.5, 7, 12, 10, 1.5)
    cr.stroke()
    _line(cr, 15.5, 12, 20.5, 12)
    _line(cr, 3, 21, 21, 3)


def _trash(cr):
    _line(cr, 3.5, 6, 20.5, 6)
    _poly(cr, [(9, 6), (9, 3), (15, 3), (15, 6)])
    cr.stroke()
    _poly(cr, [(5.5, 6), (7, 21), (17, 21), (18.5, 6)])
    cr.stroke()
    _line(cr, 10, 10, 10, 17)
    _line(cr, 14, 10, 14, 17)


def _send(cr):
    _poly(cr, [(2.5, 11), (21.5, 3), (14, 21.5), (11, 13)], close=True)
    cr.stroke()
    _line(cr, 11, 13, 21.5, 3)


def _pause(cr):
    _rrect(cr, 5.5, 4, 4.5, 16, 1)
    cr.fill()
    _rrect(cr, 14, 4, 4.5, 16, 1)
    cr.fill()


def _play(cr):
    _poly(cr, [(7, 3.5), (19.5, 12), (7, 20.5)], close=True)
    cr.fill()


def _stop(cr):
    _rrect(cr, 5, 5, 14, 14, 2)
    cr.fill()


def _estop(cr):
    pts = [(12 + 9.8 * math.cos(PI / 8 + i * PI / 4), 12 + 9.8 * math.sin(PI / 8 + i * PI / 4)) for i in range(8)]
    _poly(cr, pts, close=True)
    cr.stroke()
    _line(cr, 12, 6.5, 12, 13.5)
    cr.arc(12, 17, 1.4, 0, 2 * PI)
    cr.fill()


def _snow(cr):
    for i in range(3):
        a = i * PI / 3
        dx, dy = 9.5 * math.cos(a), 9.5 * math.sin(a)
        _line(cr, 12 - dx, 12 - dy, 12 + dx, 12 + dy)
        for s in (1, -1):
            cx, cy = 12 + s * 6.3 * math.cos(a), 12 + s * 6.3 * math.sin(a)
            for b in (0.6, -0.6):
                ang = a + (0 if s > 0 else PI) + PI + b
                _line(cr, cx, cy, cx + 3 * math.cos(ang + PI), cy + 3 * math.sin(ang + PI))


def _refresh(cr):
    cr.arc(12, 12, 8, -PI * 0.35, PI * 1.45)
    cr.stroke()
    _poly(cr, [(12.5, 1.8), (16.6, 5), (13, 8.2)])
    cr.stroke()


def _back(cr):
    _line(cr, 20, 12, 4, 12)
    _poly(cr, [(10.5, 5.5), (4, 12), (10.5, 18.5)])
    cr.stroke()


def _folder_up(cr):
    _files(cr)
    _line(cr, 12, 17, 12, 11)
    _poly(cr, [(9, 13.5), (12, 10.5), (15, 13.5)])
    cr.stroke()


def _keyboard(cr):
    _rrect(cr, 2, 6, 20, 12, 2)
    cr.stroke()
    for y in (9.5, 12.5):
        for x in (6, 9.5, 13, 16.5):
            cr.rectangle(x - 0.9, y - 0.9, 1.8, 1.8)
    cr.fill()
    _line(cr, 7.5, 15.3, 16.5, 15.3)


def _keyboard_hide(cr):
    _rrect(cr, 2, 3, 20, 11, 2)
    cr.stroke()
    _line(cr, 7.5, 10, 16.5, 10)
    _poly(cr, [(8, 17), (12, 21), (16, 17)])
    cr.stroke()


def _check(cr):
    _poly(cr, [(4.5, 12.5), (9.5, 17.5), (19.5, 6.5)])
    cr.stroke()


def _close(cr):
    _line(cr, 6, 6, 18, 18)
    _line(cr, 18, 6, 6, 18)


def _plus(cr):
    _line(cr, 12, 5, 12, 19)
    _line(cr, 5, 12, 19, 12)


def _minus(cr):
    _line(cr, 5, 12, 19, 12)


def _quit(cr):
    _poly(cr, [(13, 7), (13, 3.5), (3.5, 3.5), (3.5, 20.5), (13, 20.5), (13, 17)])
    cr.stroke()
    _line(cr, 9, 12, 21, 12)
    _poly(cr, [(17, 8), (21, 12), (17, 16)])
    cr.stroke()


def _chip(cr):
    _rrect(cr, 6.5, 6.5, 11, 11, 1.5)
    cr.stroke()
    for k in (9.5, 14.5):
        _line(cr, k, 3, k, 6.5)
        _line(cr, k, 17.5, k, 21)
        _line(cr, 3, k, 6.5, k)
        _line(cr, 17.5, k, 21, k)


def _info(cr):
    cr.arc(12, 12, 9.5, 0, 2 * PI)
    cr.stroke()
    _line(cr, 12, 11, 12, 17)
    cr.arc(12, 7.5, 1.3, 0, 2 * PI)
    cr.fill()


def _warning(cr):
    _poly(cr, [(12, 3), (21.5, 20), (2.5, 20)], close=True)
    cr.stroke()
    _line(cr, 12, 9, 12, 14)
    cr.arc(12, 17, 1.2, 0, 2 * PI)
    cr.fill()


def _speed(cr):
    cr.arc(12, 15, 9, PI, 2 * PI)
    cr.stroke()
    _line(cr, 12, 15, 17, 9)
    cr.arc(12, 15, 1.8, 0, 2 * PI)
    cr.fill()


def _drop(cr):
    cr.move_to(12, 2.5)
    cr.curve_to(15, 7, 18.5, 11, 18.5, 14.5)
    cr.arc(12, 14.5, 6.5, 0, PI)
    cr.curve_to(5.5, 11, 9, 7, 12, 2.5)
    cr.close_path()
    cr.stroke()


def _zoff(cr):
    _line(cr, 3, 20.5, 21, 20.5)
    _hotend_small(cr)


def _hotend_small(cr):
    _rrect(cr, 7, 3, 10, 6.5, 1)
    cr.stroke()
    _poly(cr, [(9, 9.5), (15, 9.5), (13, 13.5), (11, 13.5)], close=True)
    cr.stroke()
    _line(cr, 12, 15.5, 12, 18.5)


def _sort(cr):
    for i, w in enumerate((16, 11, 6)):
        _line(cr, 4, 6 + i * 6, 4 + w, 6 + i * 6)


def _lock(cr):
    _rrect(cr, 5, 10.5, 14, 10.5, 2)
    cr.stroke()
    cr.arc(12, 10.5, 4.5, PI, 2 * PI)
    cr.stroke()


def _restart(cr):
    _refresh(cr)


def _service(cr):
    _gear(cr)


def _dot(cr):
    cr.arc(12, 12, 4, 0, 2 * PI)
    cr.fill()


def _box(cr):
    _rrect(cr, 4, 4, 16, 16, 2)
    cr.stroke()


def _extrude(cr):
    _hotend_small(cr)
    _poly(cr, [(9, 18), (12, 21.5), (15, 18)])
    cr.stroke()


def _retract(cr):
    _hotend_small(cr)
    _poly(cr, [(9, 20.5), (12, 17), (15, 20.5)])
    cr.stroke()


def _network(cr):
    for x, y in ((12, 4.5), (5, 19), (19, 19)):
        cr.arc(x, y, 2.5, 0, 2 * PI)
        cr.stroke()
    _line(cr, 12, 7, 12, 13)
    _poly(cr, [(5, 16.5), (5, 13), (19, 13), (19, 16.5)])
    cr.stroke()


def _rrect(cr, x, y, w, h, r):
    r = min(r, w / 2.0, h / 2.0)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -PI / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, PI / 2)
    cr.arc(x + r, y + h - r, r, PI / 2, PI)
    cr.arc(x + r, y + r, r, PI, 1.5 * PI)
    cr.close_path()


ICONS = {
    "home": _home, "home_all": _home_letter("XYZ"), "home_x": _home_letter("X"),
    "home_y": _home_letter("Y"), "home_z": _home_letter("Z"), "home_xy": _home_letter("XY"),
    "control": _control, "files": _files, "file": _file, "folder": _files, "folder_up": _folder_up,
    "console": _console, "code": _code, "system": _power, "power": _power, "settings": _gear,
    "gear": _gear, "mmu": _spool, "spool": _spool, "palette": _palette, "mouse": _mouse,
    "display": _display, "hotend": _hotend, "wifi": _wifi, "hash": _hash, "thermometer": _thermo,
    "move": _move, "fan": _fan, "led": _bulb, "bulb": _bulb, "motors_off": _motors_off,
    "trash": _trash, "clear": _trash, "send": _send, "pause": _pause, "play": _play, "resume": _play,
    "stop": _stop, "cancel": _stop, "estop": _estop, "cooldown": _snow, "refresh": _refresh,
    "restart": _restart, "back": _back, "keyboard": _keyboard, "keyboard_hide": _keyboard_hide,
    "check": _check, "close": _close, "plus": _plus, "minus": _minus, "quit": _quit, "chip": _chip,
    "info": _info, "warning": _warning, "speed": _speed, "flow": _drop, "zoffset": _zoff,
    "sort": _sort, "lock": _lock, "service": _service, "dot": _dot, "box": _box,
    "up": _arrow(0), "down": _arrow(PI), "left": _arrow(-PI / 2), "right": _arrow(PI / 2),
    "z_up": _z_arrow(True), "z_down": _z_arrow(False), "extrude": _extrude, "retract": _retract,
    "network": _network,
}


def paint_icon(cr, name, x, y, size, rgba_color, line=2.0):
    cr.save()
    cr.translate(x, y)
    s = size / 24.0
    cr.scale(s, s)
    cr.set_source_rgba(*rgba_color)
    cr.set_line_width(line)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    ICONS.get(name, _box)(cr)
    cr.new_path()
    cr.restore()


class Icon(Gtk.DrawingArea):
    """Theme-tinted vector icon; colour follows the CSS `color` of its node."""

    def __init__(self, name, size):
        super().__init__()
        self.name = name
        self.size = size
        self.set_size_request(size, size)
        self.get_style_context().add_class("icon")
        self.connect("draw", self._draw)
        self.connect("style-updated", lambda *_: self.queue_draw())
        self.connect("state-flags-changed", lambda *_: self.queue_draw())

    def set_icon(self, name):
        if name != self.name:
            self.name = name
            self.queue_draw()

    def _draw(self, _w, cr):
        ctx = self.get_style_context()
        c = ctx.get_color(ctx.get_state())
        W, H = self.get_allocated_width(), self.get_allocated_height()
        sz = min(W, H, self.size)
        paint_icon(cr, self.name, (W - sz) / 2.0, (H - sz) / 2.0, sz, (c.red, c.green, c.blue, c.alpha))
        return False


def icon_pixbuf(name, size, color=(0.9, 0.9, 0.92, 1.0)):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    paint_icon(cr, name, 0, 0, size, color)
    surf.flush()
    return Gdk.pixbuf_get_from_surface(surf, 0, 0, size, size)

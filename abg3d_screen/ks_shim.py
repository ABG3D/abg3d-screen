"""Lightweight KlipperScreen-compatible shim.

Hosts native KlipperScreen GTK panels (BoxTurtle AFC's `AFC.py` from
~/AFC-Klipper-Screen-Add-On, Happy Hare's panels from ~/KlipperScreen/happy_hare)
inside abg3d-screen without running KlipperScreen itself.

It provides virtual `ks_includes.*` modules (ScreenPanel, KlippyGtk, KlippyGcodes,
functions) backed by abg3d-screen's Moonraker client, modals, toasts and keyboard.
Unknown KlipperScreen APIs resolve to harmless no-ops so a panel degrades instead
of crashing; anything else KlipperScreen-specific is loaded from a real
~/KlipperScreen/ks_includes checkout if one exists.
"""
import builtins
import glob
import importlib.util
import json
import logging
import os
import re
import sys
import types
import urllib.parse
import urllib.request

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk, Pango  # noqa: E402

from .icons import icon_pixbuf
from .widgets import GRAPH_COLORS, Scroller, add_cls

log = logging.getLogger("abg3d.ks_shim")
HOME = os.path.expanduser("~")
KS_DIR = os.path.join(HOME, "KlipperScreen")

KS_ICON_MAP = {
    "arrow-left": "back", "arrow-right": "right", "arrow-up": "up", "arrow-down": "down",
    "home": "home", "stop": "cancel", "cancel": "close", "pause": "pause", "resume": "play",
    "refresh": "refresh", "settings": "gear", "extrude": "extrude", "retract": "retract",
    "filament": "spool", "spool": "spool", "heat-up": "thermometer", "fan": "fan", "light": "bulb",
    "complete": "check", "info": "info", "warning": "warning", "emergency": "estop",
    "console": "console", "files": "files", "motor-off": "motors_off", "increase": "plus",
    "decrease": "minus", "delete": "trash", "keyboard": "keyboard", "load": "extrude",
    "unload": "retract", "hotend": "hotend", "extruder": "hotend", "shutdown": "power",
}


class Noop:
    """Absorbs attribute access and calls for KlipperScreen APIs the shim does not implement."""

    def __init__(self, name="noop"):
        self._name = name

    def __call__(self, *a, **k):
        log.debug("ks_shim: no-op call %s", self._name)
        return None

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Noop("%s.%s" % (self._name, n))

    def __bool__(self):
        return False

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __getitem__(self, k):
        return Noop("%s[%r]" % (self._name, k))

    def __contains__(self, k):
        return False


class _Fallback:
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        log.debug("ks_shim: missing %s.%s -> no-op", type(self).__name__, n)
        return Noop("%s.%s" % (type(self).__name__, n))


# ----------------------------------------------------------------- KlippyGtk
class GtkShim(_Fallback):
    def __init__(self, app):
        ui = app.ui
        self.app = app
        self.width, self.height = ui.w, ui.h
        self.content_width = ui.w - (ui.nav_size if ui.nav_left else 0)
        self.content_height = ui.h - ui.header_h - (0 if ui.nav_left else ui.nav_size)
        self.font_size = ui.fs
        self.font_ratio = [33, 49]
        self.img_width = self.img_height = ui.icon
        self.img_scale = ui.icon
        self.button_image_scale = 1.38
        self.bsidescale = 0.65
        self.dialog_buttons_height = ui.touch
        self.keyboard_height = int(ui.h * 0.4)
        self.ultra_tall = False
        self.color_list = {}
        self.image_dirs = self._image_dirs()

    @staticmethod
    def _image_dirs():
        pats = [os.path.join(KS_DIR, "styles", t, "images") for t in ("material-dark", "z-bolt", "colorized")]
        pats += sorted(glob.glob(os.path.join(KS_DIR, "styles", "*", "images")))
        pats += [os.path.join(HOME, "AFC-Klipper-Screen-Add-On", d) for d in ("images", "icons", ".")]
        pats += sorted(glob.glob(os.path.join(HOME, "AFC-Klipper-Screen-Add-On", "styles", "*", "images")))
        pats += [os.path.join(KS_DIR, "happy_hare", d) for d in ("images", "icons")]
        seen, out = set(), []
        for p in pats:
            if os.path.isdir(p) and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    # --- images
    def _find(self, name):
        if not name:
            return None
        if os.path.isfile(name):
            return name
        for d in self.image_dirs:
            for ext in (".svg", ".png", ""):
                p = os.path.join(d, name + ext)
                if os.path.isfile(p):
                    return p
        return None

    def PixbufFromIcon(self, filename, width=None, height=None):
        w = int(width or self.img_width)
        h = int(height or self.img_height)
        path = self._find(filename)
        if path:
            try:
                return GdkPixbuf.Pixbuf.new_from_file_at_size(path, w, h)
            except Exception:
                pass
        return icon_pixbuf(KS_ICON_MAP.get(filename or "", "box"), max(8, min(w, h)))

    def PixbufFromFile(self, filename, width=-1, height=-1):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(filename, int(width), int(height))
        except Exception:
            return None

    def PixbufFromHttp(self, resource, width=-1, height=-1):
        mr = self.app.mr
        try:
            with urllib.request.urlopen(mr.url("/server/files/" + urllib.parse.quote(resource)), timeout=4) as r:
                data = r.read()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pb = loader.get_pixbuf()
            if width > 0 and height > 0:
                pb = pb.scale_simple(int(width), int(height), GdkPixbuf.InterpType.BILINEAR)
            return pb
        except Exception:
            return None

    def Image(self, image_name=None, width=None, height=None):
        pb = self.PixbufFromIcon(image_name, width, height) if image_name else None
        return Gtk.Image.new_from_pixbuf(pb) if pb else Gtk.Image()

    # --- widgets
    def Label(self, label, style=None, *a, **k):
        lb = Gtk.Label(label=label)
        lb.set_line_wrap(True)
        lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if style:
            add_cls(lb, style)
        return lb

    def Button(self, image_name=None, label=None, style=None, scale=None, position=Gtk.PositionType.TOP,
               lines=2, *a, **k):
        b = Gtk.Button()
        b.set_can_focus(False)
        b.set_hexpand(True)
        b.set_vexpand(True)
        vertical = position in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=2)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        if image_name:
            sz = int(self.img_width * (scale or self.button_image_scale))
            box.pack_start(self.Image(image_name, sz, sz), False, False, 0)
        if label is not None:
            lb = Gtk.Label(label=label)
            lb.set_line_wrap(True)
            lb.set_lines(lines)
            lb.set_ellipsize(Pango.EllipsizeMode.END)
            lb.set_justify(Gtk.Justification.CENTER)
            box.pack_start(lb, False, False, 0)
        b.add(box)
        if style:
            add_cls(b, style)
        return b

    def HomogeneousGrid(self, width=None, height=None, *a, **k):
        g = Gtk.Grid()
        g.set_row_homogeneous(True)
        g.set_column_homogeneous(True)
        return g

    def ScrolledWindow(self, steppers=True, **kwargs):
        sw = Scroller(Gtk.Box())
        sw.remove(sw.get_child())
        sw.set_hexpand(True)
        sw.set_vexpand(True)
        return sw

    def Dialog(self, title, buttons, content, callback=None, *args):
        app = self.app
        dlg = DialogShim(app)
        row = Gtk.Box(spacing=app.ui.sp)
        row.set_homogeneous(True)
        for spec in buttons or []:
            b = Gtk.Button(label=spec.get("name", "OK"))
            b.set_can_focus(False)
            if spec.get("style"):
                add_cls(b, spec["style"])
            resp = spec.get("response", Gtk.ResponseType.OK)
            b.connect("clicked", lambda _b, r=resp: callback(dlg, r, *args) if callback else dlg.destroy())
            row.pack_start(b, True, True, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=app.ui.sp)
        if isinstance(title, str) and title:
            lb = Gtk.Label(label=title)
            add_cls(lb, "modal-title")
            box.pack_start(lb, False, False, 0)
        if content is not None:
            if content.get_parent():
                content.get_parent().remove(content)
            box.pack_start(content, True, True, 0)
        box.pack_start(row, False, False, 0)
        box.set_size_request(int(app.ui.w * 0.8), -1)
        dlg.modal = app.show_modal(box)
        return dlg

    def remove_dialog(self, dialog, *a, **k):
        if dialog is not None and hasattr(dialog, "destroy"):
            dialog.destroy()

    def get_temp_color(self, device):
        names = self.app.history.order
        i = names.index(device) if device in names else len(names)
        r, g, b = GRAPH_COLORS[i % len(GRAPH_COLORS)]
        return True, "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    def reset_temp_color(self, *a):
        pass

    def get_font_size(self):
        return self.font_size

    def get_image_width(self):
        return self.img_width

    def get_image_height(self):
        return self.img_height

    def get_content_width(self):
        return self.content_width

    def get_content_height(self):
        return self.content_height

    def get_keyboard_height(self):
        return self.keyboard_height


class DialogShim(_Fallback):
    def __init__(self, app):
        self.app = app
        self.modal = None

    def destroy(self, *a):
        if self.modal is not None:
            self.app.close_modal(self.modal)
            self.modal = None

    hide = destroy

    def show_all(self, *a):
        pass


# -------------------------------------------------------------- Printer / WS
class PrinterShim(_Fallback):
    def __init__(self, mr, configfile):
        self.mr = mr
        self.config = (configfile or {}).get("config", {}) or {}
        self.settings = (configfile or {}).get("settings", {}) or {}
        self.available_commands = {}
        self.spoolman = False
        self.power_devices = {}
        self.system_info = {}
        self.busy = False

    @property
    def data(self):
        return self.mr.data

    @property
    def state(self):
        return self.mr.klippy_state

    @property
    def tools(self):
        return self.get_tools()

    @property
    def extrudercount(self):
        return len(self.get_tools())

    def get_stat(self, stat, substat=None):
        d = self.mr.data.get(stat, {})
        if substat is not None:
            return d.get(substat, {}) if isinstance(d, dict) else {}
        return d

    def get_dev_stat(self, dev, stat):
        return self.mr.data.get(dev, {}).get(stat)

    def get_config_section(self, section):
        return self.config.get(section, False)

    def get_config_section_list(self, search=""):
        return [s for s in self.config if s.startswith(search)]

    def config_section_exists(self, section):
        return section in self.config

    def get_tools(self):
        return sorted(o for o in self.mr.objects if self.mr._is_extruder(o))

    def get_heaters(self):
        return [h for h in self.mr.heaters() if not self.mr._is_extruder(h)]

    def get_temp_devices(self):
        return self.mr.heaters() + self.mr.temp_fans() + self.mr.sensors()

    def get_fans(self):
        return [o for o in self.mr.objects if o == "fan" or o.split(" ", 1)[0] in
                ("fan_generic", "controller_fan", "heater_fan", "temperature_fan")]

    def get_output_pins(self):
        return [o for o in self.mr.objects if o.startswith("output_pin ")]

    def get_gcode_macros(self):
        return self.mr.macros()

    get_macros = get_gcode_macros

    def get_has_heated_bed(self):
        return "heater_bed" in self.mr.objects

    def get_power_devices(self):
        return []

    def get_led_list(self):
        return []

    def get_probe(self):
        return self.mr.config.get("probe")

    def get_printer_status_data(self):
        return {"printer": {"extruders": {"count": self.extrudercount}, "gcode_macros": {"list": self.get_macros()}}}

    def get_extruder_count(self):
        return self.extrudercount


class KlippyShim(_Fallback):
    """Subset of KlipperScreen's KlippyWebsocket.klippy action API."""

    def __init__(self, ws):
        self._ws = ws

    def _m(self, method, params=None, callback=None, *args):
        return self._ws.send_method(method, params or {}, callback, *args)

    def gcode_script(self, script, callback=None, *args):
        return self._m("printer.gcode.script", {"script": script}, callback, *args)

    def emergency_stop(self, *a):
        return self._m("printer.emergency_stop")

    def print_pause(self, callback=None, *args):
        return self._m("printer.print.pause", None, callback, *args)

    def print_resume(self, callback=None, *args):
        return self._m("printer.print.resume", None, callback, *args)

    def print_cancel(self, callback=None, *args):
        return self._m("printer.print.cancel", None, callback, *args)

    def print_start(self, filename, callback=None, *args):
        return self._m("printer.print.start", {"filename": filename}, callback, *args)

    def restart(self, *a):
        return self._m("printer.restart")

    def restart_firmware(self, *a):
        return self._m("printer.firmware_restart")

    def get_file_metadata(self, filename, callback=None, *args):
        return self._m("server.files.metadata", {"filename": filename}, callback, *args)

    def get_file_list(self, callback=None, *args):
        return self._m("server.files.list", {"root": "gcodes"}, callback, *args)

    def object_subscription(self, *a, **k):
        return True


class WsShim(_Fallback):
    def __init__(self, mr):
        self.mr = mr
        self.klippy = KlippyShim(self)

    @property
    def connected(self):
        return self.mr.connected

    def send_method(self, method, params=None, callback=None, *args):
        def cb(res, err):
            if callback:
                callback({"error": err} if err else {"result": res}, method, params or {}, *args)
        self.mr.call(method, params or {}, cb)
        return True


class ApiShim(_Fallback):
    """Synchronous REST helper (KlippyRest); short timeouts keep the UI responsive."""

    def __init__(self, mr):
        self.mr = mr

    def _req(self, path, method="GET", body=None, json_resp=True, timeout=4):
        try:
            data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
            headers = {"Content-Type": "application/json"} if body is not None else {}
            if self.mr.api_key:
                headers["X-Api-Key"] = self.mr.api_key
            req = urllib.request.Request(self.mr.url("/" + path.lstrip("/")), data=data, method=method,
                                         headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
            return json.loads(payload) if json_resp else payload
        except Exception as e:
            log.warning("ks_shim REST %s %s failed: %s", method, path, e)
            return False

    def send_request(self, method, json=True, timeout=4):
        return self._req(method, "GET", None, json, timeout)

    def post_request(self, method, json=None, json_response=True, timeout=4):
        return self._req(method, "POST", json, json_response, timeout)

    def get_server_info(self):
        return self.send_request("server/info")

    def get_printer_info(self):
        return self.send_request("printer/info")

    def get_thumbnail_stream(self, thumbnail):
        return self._req("server/files/gcodes/" + urllib.parse.quote(thumbnail), json_resp=False)


class _Section(dict):
    def get(self, key, fallback=None, **k):
        return super().get(key, fallback if fallback is not None else k.get("fallback"))

    def getboolean(self, key, fallback=False, **k):
        v = dict.get(self, key)
        return fallback if v is None else str(v).lower() in ("1", "true", "yes", "on")

    def getint(self, key, fallback=0, **k):
        try:
            return int(dict.get(self, key, fallback))
        except (TypeError, ValueError):
            return fallback

    def getfloat(self, key, fallback=0.0, **k):
        try:
            return float(dict.get(self, key, fallback))
        except (TypeError, ValueError):
            return fallback


class ConfigShim(_Fallback):
    def __init__(self):
        self.main = _Section({"24htime": "True", "theme": "material-dark", "show_cursor": "False",
                              "use_dpms": "True", "font_size": "medium", "side_macro_shortcut": "True"})

    def get_main_config(self):
        return self.main

    def get_printer_config(self, *a):
        return _Section()

    def get_menu_items(self, *a, **k):
        return []

    def get_preheat_options(self):
        return {}

    def get_debug(self):
        return False

    def get_spoolman(self):
        return False


class ScreenShim(_Fallback):
    def __init__(self, app, printer, gtk):
        self.app = app
        self.printer = printer
        self.gtk = gtk
        self._ws = WsShim(app.mr)
        self.apiclient = ApiShim(app.mr)
        self._config = ConfigShim()
        self.files = Noop("files")
        self.width, self.height = app.ui.w, app.ui.h
        self.vertical_mode = False
        self.lang_ltr = True
        self.connected_printer = "abg3d"
        self.panels = {}
        self.panels_modules = {}
        self._cur_panels = []
        self.base_panel = Noop("base_panel")
        self.windowed = False
        self.use_dpms = True
        self.theme = "material-dark"
        self._kb_close = None

    @property
    def server_info(self):
        return self.app.mr.server_info

    def show_popup_message(self, message, level=3, *a, **k):
        self.app.toast(message, error=level >= 3)

    def close_popup_message(self, *a, **k):
        pass

    def show_panel(self, panel, *a, **k):
        self.app.toast("Panel '%s' is not available in abg3d-screen" % panel)

    def _menu_go_back(self, *a, **k):
        pass

    _menu_go_home = _menu_go_back

    def _send_action(self, widget, method, params=None, *a):
        self._ws.send_method(method, params or {})

    def _confirm_send_action(self, widget, text, method, params=None, *a):
        self.app.confirm(text, lambda: self._send_action(widget, method, params))

    def show_keyboard(self, entry=None, event=None, *a, **k):
        if isinstance(entry, Gtk.Entry):
            self._kb_close = self.app.keyboard_popup(entry, on_close=lambda: setattr(self, "_kb_close", None))

    def remove_keyboard(self, *a, **k):
        if self._kb_close:
            self._kb_close()


# -------------------------------------------------------------- ScreenPanel
class ScreenPanel:
    def __init__(self, screen, title, *args, **kwargs):
        self.menu = None
        self._screen = screen
        self._config = screen._config
        self._files = screen.files
        self._printer = screen.printer
        self._gtk = screen.gtk
        self.labels = {}
        self.control = {}
        self.title = title
        self.ks_printer_cfg = None
        self.bts = screen.gtk.bsidescale
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.set_hexpand(True)
        self.content.set_vexpand(True)

    def _autoscroll(self, scroll, *a):
        adj = scroll.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())

    def emergency_stop(self, *a):
        self._screen._ws.klippy.emergency_stop()

    def menu_item_clicked(self, widget, item, *a):
        self._screen.show_panel(item.get("panel", "?") if isinstance(item, dict) else item)

    def load_menu(self, *a, **k):
        pass

    def get_file_image(self, *a, **k):
        return None

    def activate(self):
        pass

    def deactivate(self):
        pass

    def process_update(self, *args):
        pass

    def get_title(self):
        return self.title

    @staticmethod
    def format_time(seconds):
        if seconds is None or seconds <= 0:
            return "-"
        seconds = int(seconds)
        d, h, m, s = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60, seconds % 60
        return ("%dd " % d if d else "") + ("%dh " % h if h else "") + "%dm %ds" % (m, s)

    @staticmethod
    def format_size(size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return "%.1f %s" % (size, unit)
            size /= 1024.0
        return "%.1f TB" % size

    @staticmethod
    def prettify(name):
        return name.replace("_", " ").strip().title() if isinstance(name, str) else name

    def format_eta(self, total, elapsed):
        return self.format_time(max(0, total - elapsed))


class KlippyGcodes:
    HOME = "G28"
    HOME_X = "G28 X"
    HOME_Y = "G28 Y"
    HOME_Z = "G28 Z"
    HOME_XY = "G28 X Y"
    Z_TILT = "Z_TILT_ADJUST"
    QUAD_GANTRY_LEVEL = "QUAD_GANTRY_LEVEL"
    MOVE = "G1"
    MOVE_ABSOLUTE = "G90"
    MOVE_RELATIVE = "G91"
    EXTRUDE_ABS = "M82"
    EXTRUDE_REL = "M83"
    SET_EXT_TEMP = "M104"
    SET_BED_TEMP = "M140"
    SET_EXT_FACTOR = "M221"
    SET_FAN_SPEED = "M106"
    SET_SPD_FACTOR = "M220"
    PROBE_CALIBRATE = "PROBE_CALIBRATE"
    BED_MESH_CALIBRATE = "BED_MESH_CALIBRATE"
    SAVE_CONFIG = "SAVE_CONFIG"

    @staticmethod
    def set_bed_temp(temp):
        return "M140 S%s" % temp

    @staticmethod
    def set_ext_temp(temp, tool=0):
        return "M104 T%s S%s" % (tool, temp)

    @staticmethod
    def set_heater_temp(heater, temp):
        return 'SET_HEATER_TEMPERATURE heater="%s" target=%s' % (heater, temp)

    @staticmethod
    def set_temp_fan_temp(fan, temp):
        return 'SET_TEMPERATURE_FAN_TARGET temperature_fan="%s" target=%s' % (fan, temp)

    @staticmethod
    def set_fan_speed(speed):
        return "M106 S%d" % int(float(speed) * 255 / 100)

    @staticmethod
    def set_extrusion_rate(rate):
        return "M221 S%s" % rate

    @staticmethod
    def set_speed_rate(rate):
        return "M220 S%s" % rate

    @staticmethod
    def testz_move(dist):
        return "TESTZ Z=%s" % dist

    @staticmethod
    def extrude(dist, speed=500):
        return "G1 E%s F%s" % (dist, speed)


def find_widget(widget, wanted_type):
    if isinstance(widget, wanted_type):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_widget(child, wanted_type)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------- loading
def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


def install_modules():
    real = os.path.join(KS_DIR, "ks_includes")
    pkg = _module("ks_includes")
    pkg.__path__ = [real] if os.path.isdir(real) else []
    widgets_pkg = _module("ks_includes.widgets")
    widgets_pkg.__path__ = [os.path.join(real, "widgets")] if os.path.isdir(os.path.join(real, "widgets")) else []

    def _fn_getattr(name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Noop("functions." + name)
    functions = _module("ks_includes.functions", __getattr__=_fn_getattr)
    mods = {
        "ks_includes": pkg,
        "ks_includes.widgets": widgets_pkg,
        "ks_includes.screen_panel": _module("ks_includes.screen_panel", ScreenPanel=ScreenPanel),
        "ks_includes.KlippyGtk": _module("ks_includes.KlippyGtk", KlippyGtk=GtkShim, find_widget=find_widget),
        "ks_includes.KlippyGcodes": _module("ks_includes.KlippyGcodes", KlippyGcodes=KlippyGcodes),
        "ks_includes.functions": functions,
    }
    for k, v in mods.items():
        sys.modules.setdefault(k, v)
    pkg.screen_panel = sys.modules["ks_includes.screen_panel"]
    pkg.KlippyGtk = sys.modules["ks_includes.KlippyGtk"]
    pkg.KlippyGcodes = sys.modules["ks_includes.KlippyGcodes"]
    pkg.functions = sys.modules["ks_includes.functions"]
    pkg.widgets = widgets_pkg
    if not hasattr(builtins, "_"):
        builtins._ = lambda s: s
    if not hasattr(builtins, "ngettext"):
        builtins.ngettext = lambda s, p, n: s if n == 1 else p


def load_panel(path, app, configfile, title="MMU"):
    """Import a KlipperScreen panel file and instantiate it against the shim. Raises on failure."""
    install_modules()
    for d in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        if d and d not in sys.path:
            sys.path.append(d)
    name = "abg3d_native_" + re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0])
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    screen = ScreenShim(app, PrinterShim(app.mr, configfile), GtkShim(app))
    cls = getattr(mod, "Panel", None)
    if cls is None:
        cls = next((v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, ScreenPanel)
                    and v is not ScreenPanel), None)
    if cls is not None:
        try:
            panel = cls(screen, title)
        except TypeError:
            panel = cls(screen, title, False)
    elif hasattr(mod, "create_panel"):
        panel = mod.create_panel(screen, title)
    else:
        raise ImportError("no KlipperScreen Panel class in %s" % path)
    if hasattr(panel, "initialize") and callable(panel.initialize):
        try:
            panel.initialize(title)
        except TypeError:
            panel.initialize()
    if not isinstance(getattr(panel, "content", None), Gtk.Widget):
        raise ImportError("panel has no GTK content")
    return panel

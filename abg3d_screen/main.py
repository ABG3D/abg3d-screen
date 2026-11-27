"""abg3d-screen: lightweight GTK3 touchscreen UI for Klipper via Moonraker + Mainsail."""
import configparser
import json
import logging
import math
import os
import signal
import sys

import cairo
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from . import widgets  # noqa: E402
from .core import Blanker, TempHistory  # noqa: E402
from .moonraker import Moonraker  # noqa: E402
from .theme import DEFAULT_THEME, THEMES, Ui, build_css, detect_geometry, hex_rgb, theme_colors  # noqa: E402
from .ui_console import ConsolePanel  # noqa: E402
from .ui_control import ControlPanel  # noqa: E402
from .ui_files import FilesPanel  # noqa: E402
from .ui_home import HomePanel  # noqa: E402
from .ui_mmu import MmuPanel  # noqa: E402
from .ui_settings import SettingsPanel  # noqa: E402
from .ui_system import SystemPanel  # noqa: E402
from .widgets import (HBox, IconBtn, Keyboard, Lbl, Scroller, ThumbCache, VBox, add_cls, confirm,  # noqa: E402
                      icon_content, set_cls, set_temp_cmd)

log = logging.getLogger("abg3d")
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PKG_DIR)
HOME = os.path.expanduser("~")
SETTINGS_PATH = os.path.join(HOME, ".config", "abg3d-screen", "settings.json")

DEFAULT_CONFIG = {
    "host": "127.0.0.1", "port": "7125", "api_key": "",
    "fullscreen": "true", "width": "800", "height": "480", "diagonal": "0",
    "font_size": "0", "log_level": "INFO",
}
DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME, "show_cursor": False, "blank_timeout": 300, "blank_while_printing": False,
    "allow_quit": False, "mmu_enabled": False, "pin_bedfans": False, "pin_caselight": False,
    "macros_hidden": [], "macros_imported": False, "graph_hidden": [],
    "move_step": 10.0, "xy_speed": 100, "z_speed": 10, "e_length": 10, "e_speed": 5,
    "zoff_step": 0.01, "console_hide_temps": True, "files_sort": "date",
}
NAV = [("home", "Home", "home"), ("control", "Control", "control"), ("files", "Files", "files"),
       ("console", "Console", "console"), ("system", "System", "system"), ("mmu", "MMU", "mmu"),
       ("settings", "Settings", "settings")]


def load_config():
    cands = [os.environ.get("ABG3D_CONFIG"),
             os.path.join(HOME, "printer_data", "config", "abg3d-screen.conf"),
             os.path.join(HOME, ".config", "abg3d-screen", "abg3d-screen.conf"),
             os.path.join(ROOT_DIR, "abg3d-screen.conf")]
    cp = configparser.ConfigParser()
    cp.read_dict({"main": DEFAULT_CONFIG})
    for p in cands:
        if p and os.path.isfile(p):
            try:
                cp.read(p)
                log.info("config: %s", p)
            except configparser.Error as e:
                log.error("bad config %s: %s", p, e)
            break
    return cp["main"]


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    if s.get("theme") not in THEMES:
        s["theme"] = DEFAULT_THEME
    if s.get("blank_timeout") not in (0, 60, 300, 900, 1800):
        s["blank_timeout"] = 300
    return s


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.settings = load_settings()
        self.exit_code = 0
        fullscreen = cfg.getboolean("fullscreen")
        x, y, w, h, wmm, hmm = detect_geometry(Gdk, cfg.getint("width"), cfg.getint("height"), fullscreen)
        self.ui = Ui(w, h, wmm, hmm, cfg.getfloat("diagonal", 0.0), cfg.getint("font_size"), x, y)
        widgets.M.update(icon=self.ui.icon, icon_s=self.ui.icon_s, touch=self.ui.touch, sp=self.ui.sp,
                         pad=self.ui.pad, small=self.ui.small, fs_s=self.ui.fs_s)
        self.width, self.height = self.ui.w, self.ui.h
        self.mr = Moonraker(cfg.get("host"), cfg.getint("port"), cfg.get("api_key"), __version__)
        self.history = TempHistory(self.mr)
        self.thumbs = ThumbCache(self.mr)
        self.modals = []
        self.current = None
        self.current_key = None
        self._toast_src = None
        self._css = None
        self._bg = None
        self._bg_key = None
        self._build_window(fullscreen)
        self.blanker = Blanker(self)
        self.mr.on("connection", lambda up: self._update_header())
        self.mr.on("klippy", lambda s, m: self._update_header())
        self.mr.on("ready", self._on_ready)
        self.mr.on("status", self._on_status)
        self.mr.on("temp_store", self.history.seed)
        self.mr.on("error", lambda m: self.toast(m, error=True))
        self.mr.on("gcode_response", self._on_gcode_response)
        self.mr.on("mainsail", self._on_mainsail)
        GLib.timeout_add_seconds(1, self._sample)
        self._update_header()
        self.mr.start()

    # ================================================================ window
    def _build_window(self, fullscreen):
        ui = self.ui
        self.win = Gtk.Window(title="abg3d-screen")
        add_cls(self.win, "abg3d")
        self.win.set_app_paintable(True)
        self.win.set_resizable(False)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("draw", self._draw_background)
        # Window is pinned to the exact monitor geometry: min == max == default == monitor size.
        geo = Gdk.Geometry()
        geo.min_width = geo.max_width = geo.base_width = ui.w
        geo.min_height = geo.max_height = geo.base_height = ui.h
        self.win.set_geometry_hints(None, geo, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE |
                                    Gdk.WindowHints.BASE_SIZE)
        self.win.set_default_size(ui.w, ui.h)
        self.win.move(ui.x, ui.y)
        self.apply_theme(self.settings["theme"], redraw=False)

        self.overlay = Gtk.Overlay()
        self.overlay.set_hexpand(True)
        self.overlay.set_vexpand(True)
        self.win.add(self.overlay)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.overlay.add(root)
        root.pack_start(self._build_header(), False, True, 0)

        self.panels = {
            "home": HomePanel(self), "control": ControlPanel(self), "files": FilesPanel(self),
            "console": ConsolePanel(self), "system": SystemPanel(self), "mmu": MmuPanel(self),
            "settings": SettingsPanel(self),
        }
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        for key, p in self.panels.items():
            p.widget.set_hexpand(True)
            p.widget.set_vexpand(True)
            self.stack.add_named(p.widget, key)

        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if ui.nav_left else Gtk.Orientation.HORIZONTAL,
                      spacing=max(2, ui.sp // 2))
        nav.set_homogeneous(True)
        add_cls(nav, "nav-rail" if ui.nav_left else "nav-bar")
        self.nav = {}
        group = None
        for key, label, icon in NAV:
            rb = Gtk.RadioButton.new_from_widget(group)
            rb.add(icon_content(icon, label if ui.nav_labels else None, vertical=True,
                                size=ui.icon_s if ui.nav_labels else ui.icon))
            rb.set_mode(False)
            rb.set_can_focus(False)
            add_cls(rb, "nav")
            group = group or rb
            rb.connect("toggled", self._nav_toggled, key)
            self.nav[key] = rb
            nav.pack_start(rb, True, True, 0)
        # the nav lives in its own drag-scrollable window so it can never push the window taller
        nav_sw = Scroller(nav, horizontal=not ui.nav_left, vertical=ui.nav_left)
        add_cls(nav_sw, "nav-scroll")
        nav_sw.set_hexpand(not ui.nav_left)
        nav_sw.set_vexpand(ui.nav_left)

        if ui.nav_left:
            nav_sw.set_size_request(ui.nav_size, -1)
            body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            body.pack_start(nav_sw, False, True, 0)
            body.pack_start(self.stack, True, True, 0)
            root.pack_start(body, True, True, 0)
        else:
            nav_sw.set_size_request(-1, ui.nav_btn_h + 4)
            root.pack_start(self.stack, True, True, 0)
            root.pack_start(nav_sw, False, True, 0)

        # toast (never takes input)
        self.toast_lbl = Lbl("", xalign=0.5, wrap=True)
        self.toast_lbl.set_max_width_chars(48)
        tbox = HBox(self.toast_lbl)
        add_cls(tbox, "toast")
        self.toast_box = tbox
        self.toast_rev = Gtk.Revealer()
        self.toast_rev.set_transition_type(Gtk.RevealerTransitionType.NONE)
        self.toast_rev.add(tbox)
        self.toast_rev.set_halign(Gtk.Align.CENTER)
        self.toast_rev.set_valign(Gtk.Align.END)
        self.toast_rev.set_margin_bottom(ui.touch + ui.pad * 2)
        self.overlay.add_overlay(self.toast_rev)
        self.overlay.set_overlay_pass_through(self.toast_rev, True)

        # black screen-off overlay; input while blanked is swallowed in _gdk_event
        self.blank_box = Gtk.EventBox()
        add_cls(self.blank_box, "blank")
        self.blank_box.set_no_show_all(True)
        self.overlay.add_overlay(self.blank_box)

        # global event hook: activity tracking + wake-tap absorption without touching widget handlers
        self._waking = False
        Gdk.event_handler_set(self._gdk_event)

        self.win.show_all()
        if fullscreen:
            self.win.fullscreen()
        self.win.resize(ui.w, ui.h)
        self.apply_cursor(self.settings.get("show_cursor"))
        self._switch("home")

    def _nav_toggled(self, button, key):
        if button.get_active():
            self._switch(key)

    def _build_header(self):
        ui = self.ui
        brand = Lbl("ABG3D", "brand")
        self.state_lbl = Lbl("", "muted", "small", ellipsize=True)
        self.pill_mr = Lbl("", "pill")
        self.pill_mcu = Lbl("", "pill")
        estop = IconBtn("estop", None, self.estop, "danger", "header-estop", size=ui.icon_s)
        estop.set_valign(Gtk.Align.CENTER)
        kids = [brand, self.state_lbl, self.pill_mr, self.pill_mcu, estop]
        hdr = HBox(*kids, expand=(1,))
        for w in (self.pill_mr, self.pill_mcu):
            w.set_valign(Gtk.Align.CENTER)
        add_cls(hdr, "header")
        return hdr

    # ---------------------------------------------------------- theming
    def apply_theme(self, key, redraw=True):
        self.settings["theme"] = key if key in THEMES else DEFAULT_THEME
        css = build_css(os.path.join(PKG_DIR, "style.css"), self.ui, self.settings["theme"])
        prov = Gtk.CssProvider()
        prov.load_from_data(css.encode())
        screen = Gdk.Screen.get_default()
        if self._css:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._css)
        Gtk.StyleContext.add_provider_for_screen(screen, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css = prov
        st = Gtk.Settings.get_default()
        if st:
            st.set_property("gtk-application-prefer-dark-theme", True)
            st.set_property("gtk-enable-animations", False)
        self._bg_key = None
        if redraw:
            self.win.queue_draw()

    def _background(self, W, H):
        key = (W, H, self.settings["theme"])
        if self._bg is not None and self._bg_key == key:
            return self._bg
        t = theme_colors(self.settings["theme"])
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
        cr = cairo.Context(surf)
        cr.set_source_rgb(*hex_rgb(t["bg"]))
        cr.paint()
        r = self.ui.hex_r
        hw = math.sqrt(3) * r
        ins = r * 0.86
        corners = [(math.cos(math.pi / 2 + k * math.pi / 3), math.sin(math.pi / 2 + k * math.pi / 3))
                   for k in range(6)]
        row = 0
        y = 0.0
        while y < H + r:
            off = (row % 2) * hw / 2.0
            x = -hw / 2.0 + off
            while x < W + hw:
                cr.move_to(x + ins * corners[0][0], y + ins * corners[0][1])
                for cx, cy in corners[1:]:
                    cr.line_to(x + ins * cx, y + ins * cy)
                cr.close_path()
                x += hw
            y += 1.5 * r
            row += 1
        ar, ag, ab = hex_rgb(t["accent"])
        grad = cairo.LinearGradient(0, 0, W, H)
        grad.add_color_stop_rgba(0.0, ar, ag, ab, 0.20)
        grad.add_color_stop_rgba(0.45, ar, ag, ab, 0.07)
        grad.add_color_stop_rgba(1.0, ar, ag, ab, 0.012)
        cr.set_source(grad)
        cr.set_line_width(1.0)
        cr.stroke()
        surf.flush()
        self._bg, self._bg_key = surf, key
        return surf

    def _draw_background(self, w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_surface(self._background(W, H), 0, 0)
        cr.paint()
        return False

    def apply_cursor(self, show):
        gw = self.win.get_window()
        if gw:
            gw.set_cursor(None if show else Gdk.Cursor.new_for_display(gw.get_display(),
                                                                       Gdk.CursorType.BLANK_CURSOR))

    # ------------------------------------------------------------ input
    _PRESS = (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.KEY_PRESS)
    _RELEASE = (Gdk.EventType.BUTTON_RELEASE, Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL,
                Gdk.EventType.KEY_RELEASE)
    _SWALLOW = _PRESS + _RELEASE + (Gdk.EventType.MOTION_NOTIFY, Gdk.EventType.TOUCH_UPDATE,
                                    Gdk.EventType._2BUTTON_PRESS, Gdk.EventType._3BUTTON_PRESS,
                                    Gdk.EventType.SCROLL)

    def _gdk_event(self, event, *_data):
        t = event.type
        if t in self._PRESS:
            self.blanker.activity()
            if self.blanker.blanked:
                # first tap only wakes the screen; it never reaches a widget
                self._waking = True
                self.blanker.unblank()
                return
        if self._waking and t in self._SWALLOW:
            if t in self._RELEASE:
                self._waking = False
                self.show_blank(False)
            return
        if t == Gdk.EventType.KEY_PRESS and event.keyval == Gdk.KEY_Escape and self.modals:
            self.close_modal()
            return
        Gtk.main_do_event(event)

    # ------------------------------------------------------------- panels
    def _switch(self, key):
        panel = self.panels[key]
        if self.current is panel:
            return
        if self.current:
            try:
                self.current.on_hide()
            except Exception:
                log.exception("on_hide failed")
        self.current, self.current_key = panel, key
        self.stack.set_visible_child_name(key)
        if not self.nav[key].get_active():
            self.nav[key].set_active(True)
        try:
            panel.on_show()
        except Exception:
            log.exception("panel %s on_show failed", key)

    def show_panel(self, key):
        self._switch(key)

    def refresh_mmu(self):
        """MMU tab is always reachable; the panel itself reports detection/enable state."""
        p = self.panels.get("mmu")
        if p is not None and self.current is p:
            p.on_show()

    # ------------------------------------------------------------- modals
    def show_modal(self, child, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER):
        bg = Gtk.EventBox()
        add_cls(bg, "modal-bg")
        bg.connect("button-press-event", lambda *a: True)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_cls(card, "modal")
        card.set_halign(halign)
        card.set_valign(valign)
        if valign == Gtk.Align.END:
            card.set_margin_bottom(self.ui.sp)
        card.pack_start(child, True, True, 0)
        bg.add(card)
        self.overlay.add_overlay(bg)
        self.overlay.reorder_overlay(self.toast_rev, -1)
        self.overlay.reorder_overlay(self.blank_box, -1)
        bg.show_all()
        self.modals.append(bg)
        return bg

    def close_modal(self, bg=None):
        if bg is None:
            if not self.modals:
                return
            bg = self.modals[-1]
        if bg in self.modals:
            self.modals.remove(bg)
            self.overlay.remove(bg)
            bg.destroy()

    def keyboard_popup(self, entry, on_enter=None, on_close=None):
        """Bottom-anchored keyboard editing `entry` through a shared EntryBuffer."""
        mirror = Gtk.Entry.new_with_buffer(entry.get_buffer())
        mirror.set_hexpand(True)
        holder = {}

        def close():
            if holder.get("m"):
                self.close_modal(holder.pop("m"))
                if on_close:
                    on_close()

        def enter():
            if on_enter:
                on_enter()
        kb = Keyboard(mirror, on_enter=enter, on_hide=close)
        box = VBox(mirror, kb, expand=(1,))
        box.set_size_request(int(self.ui.w * 0.96), -1)
        holder["m"] = self.show_modal(box, valign=Gtk.Align.END)
        close.modal = holder["m"]
        mirror.set_position(-1)
        return close

    def show_blank(self, on):
        if on:
            for m in list(self.modals):
                self.close_modal(m)
        self.blank_box.set_visible(on)

    def toast(self, text, error=False, secs=4):
        self.toast_lbl.set_text(str(text)[:240])
        set_cls(self.toast_box, "error", error)
        self.toast_rev.set_reveal_child(True)
        if self._toast_src:
            GLib.source_remove(self._toast_src)

        def hide():
            self._toast_src = None
            self.toast_rev.set_reveal_child(False)
            return False
        self._toast_src = GLib.timeout_add_seconds(secs, hide)

    def confirm(self, text, cb, ok="Confirm", danger=False):
        confirm(self, text, cb, ok, danger)

    # --------------------------------------------------------- moonraker
    def _update_header(self):
        mr = self.mr
        up = mr.connected
        mcu = mr.mcu_online()
        self.pill_mr.set_text("● Moonraker %s" % ("Online" if up else "Offline"))
        set_cls(self.pill_mr, "on", up)
        set_cls(self.pill_mr, "off", not up)
        self.pill_mcu.set_text("● MCU %s" % ("Online" if mcu else "Offline"))
        set_cls(self.pill_mcu, "on", mcu)
        set_cls(self.pill_mcu, "off", not mcu)
        ps = mr.print_state() if mcu else ""
        self.state_lbl.set_text({"printing": "Printing", "paused": "Paused", "complete": "Complete",
                                 "error": "Error", "cancelled": "Cancelled"}.get(ps, ""))
        if up and mr.klippy_state != "ready" and not ps:
            msg = (mr.klippy_message or "Klipper: %s" % mr.klippy_state).strip()
            self.state_lbl.set_text(msg.splitlines()[0] if msg else "Klipper: %s" % mr.klippy_state)

    def _on_ready(self):
        self.history.setup()
        self._update_header()
        for p in self.panels.values():
            try:
                p.on_ready()
            except Exception:
                log.exception("on_ready failed for %s", p.title)
        if self.current:
            self.current.refresh()

    def _on_status(self, changes):
        if "print_stats" in changes:
            self._update_header()
        for key in ("mmu",):
            p = self.panels[key]
            if p is not self.current:
                p.on_background_status(changes)
        if self.current:
            try:
                self.current.on_status(changes)
            except Exception:
                log.exception("on_status failed for %s", self.current.title)

    def _on_gcode_response(self, line):
        self.panels["console"].append(line)
        self.panels["mmu"].on_gcode_response(line)
        if line.startswith("!!"):
            self.toast(line[2:].strip(), error=True)

    def _on_mainsail(self, data):
        if not self.settings.get("macros_imported"):
            hidden = (data.get("macros") or {}).get("hiddenMacros") or []
            self.settings["macros_hidden"] = sorted({h.upper() for h in hidden if isinstance(h, str)})
            self.settings["macros_imported"] = True
            self.save_settings()

    def _sample(self):
        if self.mr.klippy_state == "ready":
            self.history.sample()
        return True

    # ------------------------------------------------------------- actions
    def estop(self):
        self.mr.call("printer.emergency_stop")
        self.toast("Emergency stop sent", error=True)

    def quit(self, code=0):
        self.exit_code = code
        Gtk.main_quit()

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.settings, f, indent=1)
            os.replace(tmp, SETTINGS_PATH)
        except OSError as e:
            log.error("save settings: %s", e)

    def presets(self):
        """[(name, {obj: temp}, gcode)] from the Mainsail DB, else sane defaults."""
        out = []
        pres = (self.mr.mainsail.get("presets") or {}).get("presets") or {}
        if isinstance(pres, dict):
            pres = list(pres.values())
        for p in pres if isinstance(pres, list) else []:
            if not isinstance(p, dict):
                continue
            vals = {}
            for obj, v in (p.get("values") or {}).items():
                if isinstance(v, dict) and v.get("bool") and obj in self.mr.objects:
                    try:
                        vals[obj] = float(v.get("value", 0))
                    except (TypeError, ValueError):
                        pass
            out.append((p.get("name", "Preset"), vals, p.get("gcode", "") or ""))
        if not out:
            hs = self.mr.heaters()
            ext = [x for x in hs if x.startswith("extruder")][:1]
            bed = ["heater_bed"] if "heater_bed" in hs else []
            for name, e, b in (("PLA", 205, 60), ("PETG", 235, 80), ("ABS", 250, 100), ("TPU", 225, 50)):
                vals = {o: e for o in ext}
                vals.update({o: b for o in bed})
                out.append((name, vals, ""))
        return out

    def apply_preset(self, preset):
        name, vals, gcode = preset
        cmds = [set_temp_cmd(o, t) for o, t in vals.items()]
        if gcode.strip():
            cmds.append(gcode.strip())
        if cmds:
            self.mr.gcode("\n".join(cmds))
            self.toast("Preset %s applied" % name)

    def cooldown(self):
        cd = (self.mr.mainsail.get("presets") or {}).get("cooldownGcode") or "TURN_OFF_HEATERS\nM107"
        self.mr.gcode(cd)
        self.toast("Cooling down")


def main():
    cfg = load_config()
    logging.basicConfig(level=getattr(logging, cfg.get("log_level", "INFO").upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    app = App(cfg)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, Gtk.main_quit)
    Gtk.main()
    app.mr.stop()
    sys.exit(app.exit_code)


if __name__ == "__main__":
    main()


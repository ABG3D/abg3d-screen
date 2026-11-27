"""MMU tab: embeds the native KlipperScreen panel (BoxTurtle AFC / Happy Hare) via ks_shim,
falling back to a built-in lane/gate view when the add-on is missing or fails to load."""
import glob
import logging
import os

from gi.repository import Gtk

from .core import Panel
from .widgets import HBox, IconBtn, Lbl, M, Row, Scroller, Section, VBox, add_cls, set_btn

log = logging.getLogger("abg3d.mmu")
HOME = os.path.expanduser("~")
DRIVER_NAMES = {"afc": "BoxTurtle AFC", "happy_hare": "Happy Hare"}
CANDIDATES = {
    "afc": ["AFC-Klipper-Screen-Add-On/AFC.py", "AFC-Klipper-Screen-Add-On/panels/AFC.py",
            "AFC-Klipper-Screen-Add-On/panels/afc.py", "KlipperScreen/panels/AFC.py"],
    "happy_hare": ["KlipperScreen/happy_hare/mmu_main.py", "KlipperScreen/happy_hare/mmu.py",
                   "KlipperScreen/happy_hare/panels/mmu_main.py", "KlipperScreen/happy_hare/panels/mmu.py",
                   "KlipperScreen/panels/mmu_main.py", "KlipperScreen/panels/mmu.py"],
}


def find_native_panel(driver):
    for rel in CANDIDATES.get(driver, []):
        p = os.path.join(HOME, rel)
        if os.path.isfile(p):
            return p
    if driver == "happy_hare":
        hits = sorted(glob.glob(os.path.join(HOME, "KlipperScreen", "happy_hare", "**", "mmu_main.py"),
                                recursive=True))
        if hits:
            return hits[0]
    return None


class Swatch(Gtk.DrawingArea):
    def __init__(self, color):
        super().__init__()
        self.color = color
        self.set_size_request(M["icon_s"], M["icon_s"])
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        c = (self.color or "").lstrip("#")
        try:
            r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        except ValueError:
            r, g, b = 0.4, 0.4, 0.4
        cr.arc(W / 2.0, H / 2.0, min(W, H) / 2.0 - 1, 0, 6.2832)
        cr.set_source_rgb(r, g, b)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.set_line_width(1)
        cr.stroke()


class MmuPanel(Panel):
    title = "MMU"

    def __init__(self, app):
        super().__init__(app)
        self.driver = None
        self.native = None
        self.native_error = None
        self.use_native = True
        self.loading = False
        self.head = Lbl("", "title", ellipsize=True)
        self.mode_btn = IconBtn("refresh", "Built-in" if not app.ui.small else None, self._toggle_mode)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget = VBox(HBox(self.head, self.mode_btn, expand=(0,)), self.body, expand=(1,))
        add_cls(self.widget, "panel")
        self.rows = {}

    # ------------------------------------------------------------- lifecycle
    def on_ready(self):
        drv = self.mr.mmu_driver()
        if drv != self.driver:
            self.driver = drv
            self._unload_native()
        if self.visible():
            self.on_show()

    def _notice(self, text, btn_icon, btn_label, cb):
        box = VBox(Lbl(text, "muted", xalign=0.5, wrap=True), IconBtn(btn_icon, btn_label, cb))
        box.set_valign(Gtk.Align.CENTER)
        self._set_body(box)

    def _enable(self):
        self.app.settings["mmu_enabled"] = True
        self.app.save_settings()
        sp = self.app.panels.get("settings")
        if sp is not None:
            sp._mmu_mute = True
            sp.mmu_switch.set_active(True)
            sp._mmu_mute = False
        self.on_show()

    def on_show(self):
        self.driver = self.mr.mmu_driver()
        if not self.app.settings.get("mmu_enabled"):
            self.head.set_text("MMU")
            self._notice("MMU support is disabled (Settings \u203a MMU).", "check", "Enable MMU", self._enable)
            return
        if not self.driver:
            self.head.set_text("MMU")
            state = "" if self.mr.klippy_state == "ready" else " Klipper/MCU is not ready \u2014 status will " \
                "appear when it is."
            self._notice("No BoxTurtle AFC or Happy Hare detected." + state, "refresh", "Re-detect", self.on_show)
            return
        self.head.set_text(DRIVER_NAMES[self.driver])
        if self.use_native and self.native is None and not self.native_error and not self.loading:
            path = find_native_panel(self.driver)
            if path:
                self._load_native(path)
                return
            self.native_error = "Native panel not found"
        if self.use_native and self.native is not None:
            self._show_native()
        else:
            self._build_fallback()
        set_btn(self.mode_btn, label="Built-in" if self.use_native else "Native")

    def on_hide(self):
        if self.native is not None:
            try:
                self.native.deactivate()
            except Exception:
                log.exception("native deactivate failed")

    def _toggle_mode(self):
        self.use_native = not self.use_native
        if self.use_native:
            self.native_error = None
        self.on_hide()
        self.on_show()

    # ---------------------------------------------------------------- native
    def _load_native(self, path):
        from . import ks_shim
        self.loading = True
        self._set_body(Lbl("Loading native %s panel…" % DRIVER_NAMES[self.driver], "muted", xalign=0.5))

        def got(configfile):
            self.loading = False
            try:
                self.native = ks_shim.load_panel(path, self.app, configfile, title=DRIVER_NAMES[self.driver])
                log.info("loaded native MMU panel %s", path)
            except Exception as e:
                log.exception("native MMU panel failed: %s", path)
                self.native, self.native_error = None, "%s: %s" % (type(e).__name__, e)
            if self.visible():
                self.on_show()
        self.mr.fetch_config(got)

    def _show_native(self):
        content = self.native.content
        if content.get_parent() is not self.body:
            self._set_body(content)
        try:
            self.native.activate()
            self.native.process_update("notify_status_update", self.mr.data)
        except Exception:
            log.exception("native activate failed")

    def _unload_native(self):
        if self.native is not None:
            try:
                self.native.deactivate()
            except Exception:
                pass
            c = self.native.content
            if c.get_parent():
                c.get_parent().remove(c)
        self.native, self.native_error = None, None

    def _set_body(self, widget):
        for c in self.body.get_children():
            self.body.remove(c)
            if self.native is None or c is not self.native.content:
                c.destroy()
        self.body.pack_start(widget, True, True, 0)
        self.body.show_all()

    # -------------------------------------------------------------- fallback
    def _units(self):
        d = self.mr.data
        if self.driver == "afc":
            lanes = sorted(o for o in d if o.startswith("AFC_stepper ") or o.startswith("AFC_lane "))
            return [(o.split(" ", 1)[1], d.get(o, {})) for o in lanes]
        mmu = d.get("mmu", {})
        n = int(mmu.get("num_gates") or len(mmu.get("gate_status") or []) or 0)
        out = []
        for i in range(n):
            def at(key, default=None, i=i):
                v = mmu.get(key) or []
                return v[i] if i < len(v) else default
            out.append(("Gate %d" % i, {"gate": i, "status": at("gate_status", -1), "material": at("gate_material", ""),
                                        "color": at("gate_color", ""), "spool_id": at("gate_spool_id")}))
        return out

    def _build_fallback(self):
        G = self.mr.gcode
        box = VBox()
        if self.native_error:
            box.pack_start(Lbl("Built-in view (%s)" % self.native_error, "muted", "small", wrap=True), False, False, 0)
        self.summary = Lbl("", "small", wrap=True)
        box.pack_start(self.summary, False, False, 0)
        if self.driver == "afc":
            acts = [("retract", "Unload", "TOOL_UNLOAD"), ("info", "Status", "AFC_STATUS")]
        else:
            acts = [("home", "Home", "MMU_HOME"), ("retract", "Unload", "MMU_UNLOAD"),
                    ("back", "Eject", "MMU_EJECT"), ("refresh", "Recover", "MMU_RECOVER"),
                    ("info", "Status", "MMU_STATUS")]
        box.pack_start(HBox(*[IconBtn(i, label if not self.app.ui.small else None, lambda c=c: G(c))
                              for i, label, c in acts], homogeneous=True), False, False, 0)
        box.pack_start(Section("Lanes" if self.driver == "afc" else "Gates", "spool"), False, False, 0)
        self.rows = {}
        for name, st in self._units():
            info = Lbl("", "muted", "small", ellipsize=True)
            sw = Swatch(st.get("color"))
            if self.driver == "afc":
                btns = [IconBtn("extrude", None, lambda n=name: G("CHANGE_TOOL LANE=%s" % n)),
                        IconBtn("back", None, lambda n=name: G("LANE_UNLOAD LANE=%s" % n))]
            else:
                gate = st["gate"]
                btns = [IconBtn("check", None, lambda g=gate: G("MMU_SELECT GATE=%d" % g)),
                        IconBtn("extrude", None, lambda g=gate: G("MMU_SELECT GATE=%d\nMMU_LOAD" % g))]
            row = Row(sw, VBox(Lbl(name, "title", ellipsize=True), info, spacing=0), *btns, expand=(1,))
            box.pack_start(row, False, False, 0)
            self.rows[name] = (info, sw)
        if not self.rows:
            box.pack_start(Lbl("No lanes/gates reported yet", "muted"), False, False, 0)
        self._set_body(Scroller(box))
        self._update_fallback()

    def _update_fallback(self):
        if not self.rows and not hasattr(self, "summary"):
            return
        d = self.mr.data
        if self.driver == "afc":
            afc = d.get("AFC", {})
            cur = afc.get("current_load") or afc.get("current_lane") or "none"
            self.summary.set_text("Loaded: %s • State: %s" % (cur, afc.get("current_state", afc.get("status", "--"))))
        else:
            mmu = d.get("mmu", {})
            self.summary.set_text("Gate %s • Tool %s • Filament %s • %s" % (
                mmu.get("gate", "?"), mmu.get("tool", "?"), mmu.get("filament", "?"), mmu.get("action", "Idle")))
        status_txt = {-1: "unknown", 0: "empty", 1: "available", 2: "buffered"}
        for name, st in self._units():
            if name not in self.rows:
                continue
            info, sw = self.rows[name]
            if self.driver == "afc":
                flags = [k for k in ("prep", "load", "tool_loaded") if st.get(k)]
                bits = [st.get("map") or "", st.get("material") or "", st.get("status") or "", "/".join(flags)]
                if st.get("weight"):
                    bits.append("%sg" % st["weight"])
            else:
                bits = [status_txt.get(st.get("status"), str(st.get("status"))), st.get("material") or ""]
            info.set_text("  ".join(b for b in bits if b))
            if sw.color != st.get("color"):
                sw.color = st.get("color")
                sw.queue_draw()

    # ---------------------------------------------------------------- events
    def on_status(self, ch):
        if self.native is not None and self.use_native:
            try:
                self.native.process_update("notify_status_update", ch)
            except Exception:
                log.exception("native process_update failed")
        elif self.rows and any(k == "AFC" or k.startswith("AFC_") or k == "mmu" for k in ch):
            self._update_fallback()

    def on_gcode_response(self, line):
        if self.native is not None and self.visible():
            try:
                self.native.process_update("notify_gcode_response", line)
            except Exception:
                pass

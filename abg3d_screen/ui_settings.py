"""Settings: Appearance, MMU, Macros, Network, System (quit + pin configs). Icon-only sub-tabs."""
from gi.repository import Gtk

from . import network
from .core import Panel
from .icons import Icon
from .theme import THEMES
from .ui_mmu import DRIVER_NAMES, find_native_panel
from .widgets import (Dropdown, HBox, IconBtn, Lbl, M, Row, Scroller, Section, VBox, add_cls, ask_text,
                      radio_row, subtabs)

BLANK_OPTS = [0, 60, 300, 900, 1800]
BLANK_LBL = {0: "Never", 60: "1m", 300: "5m", 900: "15m", 1800: "30m"}


def switch(active, cb):
    sw = Gtk.Switch()
    sw.set_active(bool(active))
    sw.set_valign(Gtk.Align.CENTER)
    sw.set_can_focus(False)
    sw.connect("notify::active", lambda w, _p: cb(w))
    return sw


def labelled(icon, title, sub=None):
    kids = [Icon(icon, M["icon_s"])] if icon else []
    text = VBox(Lbl(title, "title", wrap=True), spacing=0)
    text.set_valign(Gtk.Align.CENTER)
    if sub is not None:
        text.pack_start(sub, False, False, 0)
    kids.append(text)
    return HBox(*kids, expand=(len(kids) - 1,))


class SettingsPanel(Panel):
    title = "Settings"

    def __init__(self, app):
        super().__init__(app)
        self.macro_box = VBox(spacing=max(2, M["sp"] // 2))
        self.net_box = VBox()
        self.wifi_list = VBox(spacing=max(2, M["sp"] // 2))
        self.mmu_status = Lbl("", "muted", "small", wrap=True)
        self.quit_btn = IconBtn("quit", None, self._quit, "danger")
        self.quit_btn.get_child().show_all()
        self.quit_btn.set_no_show_all(True)
        box, self.stack, self.tabs = subtabs([
            ("appearance", "palette", Scroller(self._build_appearance())),
            ("mmu", "hotend", Scroller(self._build_mmu())),
            ("macros", "code", Scroller(self.macro_box)),
            ("network", "wifi", Scroller(self._build_network())),
            ("system", "gear", Scroller(self._build_system())),
        ], on_change=lambda k: self.refresh(), extra=self.quit_btn)
        self.widget = box
        add_cls(self.widget, "panel")
        self.quit_btn.set_visible(bool(app.settings.get("allow_quit")))
        self.mr.on("mainsail", lambda _d: self._build_macros())

    def open_tab(self, key):
        if key in self.tabs:
            self.tabs[key].set_active(True)

    def _set(self, key, value):
        self.app.settings[key] = value
        self.app.save_settings()

    # ============================================================= APPEARANCE
    def _build_appearance(self):
        s, app = self.app.settings, self.app
        items = [(k, v["name"]) for k, v in THEMES.items()]
        dd = Dropdown(items, s.get("theme"), self._set_theme, max_h=max(app.ui.touch * 3, int(app.ui.h * 0.4)))
        blank_row, _ = radio_row(BLANK_OPTS, int(s.get("blank_timeout", 300)), self._set_blank,
                                 fmt=lambda v: BLANK_LBL[v])
        return VBox(
            Section("Theme", "palette"), dd,
            Row(labelled("mouse", "Mouse pointer"),
                switch(s.get("show_cursor"), lambda w: (self._set("show_cursor", w.get_active()),
                                                        app.apply_cursor(w.get_active())))),
            Section("Screen timeout", "display"), blank_row,
            Row(labelled("display", "Blank screen while printing"),
                switch(s.get("blank_while_printing"), lambda w: self._set("blank_while_printing", w.get_active()))),
            IconBtn("power", "Screen Off", lambda: app.blanker.blank(), "warn"))

    def _set_theme(self, key):
        self._set("theme", key)
        self.app.apply_theme(key)

    def _set_blank(self, v):
        self._set("blank_timeout", v)
        self.app.blanker.activity()

    # =================================================================== MMU
    def _build_mmu(self):
        self.mmu_switch = switch(self.app.settings.get("mmu_enabled"), self._mmu_toggled)
        self._mmu_mute = False
        return VBox(Section("Multi-material unit", "hotend"),
                    Row(labelled(None, "Enable MMU", self.mmu_status), self.mmu_switch),
                    IconBtn("refresh", "Re-detect", self._mmu_refresh))

    def _mmu_toggled(self, w):
        if self._mmu_mute:
            return
        on = w.get_active()
        self._set("mmu_enabled", on)
        if on and not self.mr.mmu_driver():
            self.app.toast("MMU enabled \u2014 no AFC / Happy Hare detected yet; the MMU tab will "
                           "show it once Klipper reports one.")
        else:
            self.app.toast("MMU %s" % ("enabled" if on else "disabled"))
        self.app.refresh_mmu()
        self._mmu_refresh()

    def _mmu_refresh(self):
        drv = self.mr.mmu_driver()
        if not drv:
            txt = "No MMU detected" + ("" if self.mr.klippy_state == "ready" else " (Klipper not ready)")
        else:
            native = find_native_panel(drv)
            txt = "Detected: %s • native panel: %s" % (DRIVER_NAMES[drv], native or "not found (built-in view)")
        self.mmu_status.set_text(txt)

    # ================================================================ MACROS
    def _build_macros(self):
        for c in self.macro_box.get_children():
            self.macro_box.remove(c)
            c.destroy()
        hidden = {h.upper() for h in self.app.settings.get("macros_hidden", [])}
        macros = self.mr.macros()
        head = HBox(Section("G-code macros", "code"),
                    IconBtn("refresh", "Mainsail" if not self.app.ui.small else None, self._import_mainsail),
                    expand=(0,))
        self.macro_box.pack_start(head, False, False, 0)
        self.macro_box.pack_start(Lbl("Toggle which macros appear in the Console quick-bar.", "muted", "small",
                                      wrap=True), False, False, 0)
        for m in macros:
            name = Lbl(m, "title" if not m.startswith("_") else "muted", ellipsize=True)
            run = IconBtn("play", None, lambda m=m: self.app.confirm("Run macro %s?" % m,
                                                                      lambda: self.mr.gcode(m), ok="Run"))
            sw = switch(m.upper() not in hidden and not m.startswith("_"),
                        lambda w, m=m: self._macro_toggle(m, w.get_active()))
            self.macro_box.pack_start(Row(name, run, sw), False, False, 0)
        if not macros:
            self.macro_box.pack_start(Lbl("No macros (Klipper not ready?)", "muted", xalign=0.5), False, False, 0)
        self.macro_box.show_all()

    def _macro_toggle(self, name, visible):
        hidden = {h.upper() for h in self.app.settings.get("macros_hidden", [])}
        (hidden.discard if visible else hidden.add)(name.upper())
        self._set("macros_hidden", sorted(hidden))
        self.app.panels["console"].build_macros()

    def _import_mainsail(self):
        def done(data):
            hidden = (data.get("macros") or {}).get("hiddenMacros") or []
            self._set("macros_hidden", sorted({h.upper() for h in hidden if isinstance(h, str)}))
            self._set("macros_imported", True)
            self._build_macros()
            self.app.panels["console"].build_macros()
            self.app.toast("Imported macro visibility from Mainsail")
        self.mr.load_mainsail(done)

    # =============================================================== NETWORK
    def _build_network(self):
        self.ip_lbl = Lbl("", "value", wrap=True)
        self.dev_lbl = Lbl("", "muted", "small", wrap=True)
        self.scan_btn = IconBtn("refresh", "Scan", self._scan)
        return VBox(Section("Status", "network"), Row(labelled("network", "IP address", self.ip_lbl)),
                    self.dev_lbl,
                    HBox(Section("Wi-Fi", "wifi"), self.scan_btn, expand=(0,)),
                    self.wifi_list)

    def _net_refresh(self):
        self.ip_lbl.set_text(", ".join(network.local_ips()) or "Not connected")
        if not network.has_nmcli():
            self.dev_lbl.set_text("nmcli (NetworkManager) not available on this host.")
            return

        def got(devs):
            self.dev_lbl.set_text("\n".join("%s (%s): %s%s" % (d["device"], d["type"], d["state"],
                                                               " • " + d["connection"] if d["connection"]
                                                               and d["connection"] != "--" else "")
                                            for d in devs) or "No network devices")
        network.device_status(got)

    def _scan(self):
        if not network.has_nmcli():
            self.app.toast("Wi-Fi scan needs nmcli (NetworkManager), which is not installed", error=True)
            self._wifi_msg("nmcli not available")
            return
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.app.toast("Scanning Wi-Fi…")
        self._wifi_msg("Scanning…")

        def done(nets, err):
            self._scanning = False
            if err:
                self._wifi_msg(err)
                return
            self._clear_wifi()
            for n in nets[:30]:
                kids = [Icon("check" if n["active"] else "wifi", M["icon_s"]),
                        Lbl(n["ssid"], "title" if n["active"] else None, ellipsize=True),
                        Lbl("%d%%" % n["signal"], "muted", "small")]
                if n["security"] and n["security"] != "--":
                    kids.append(Icon("lock", M["icon_s"]))
                b = Gtk.Button()
                b.set_can_focus(False)
                b.add(HBox(*kids, expand=(1,)))
                b.connect("clicked", lambda _b, n=n: self._wifi_pick(n))
                self.wifi_list.pack_start(b, False, False, 0)
            if not nets:
                self._wifi_msg("No networks found")
            self.wifi_list.show_all()
        network.wifi_scan(done)

    def _clear_wifi(self):
        for c in self.wifi_list.get_children():
            self.wifi_list.remove(c)
            c.destroy()

    def _wifi_msg(self, text):
        self._clear_wifi()
        self.wifi_list.pack_start(Lbl(text, "muted", wrap=True), False, False, 0)
        self.wifi_list.show_all()

    def _wifi_pick(self, n):
        app = self.app
        if n["active"]:
            app.confirm("Disconnect from %s?" % n["ssid"],
                        lambda: network.wifi_disconnect(n["ssid"], self._wifi_result), ok="Disconnect")
            return

        def connect(pw):
            app.toast("Connecting to %s…" % n["ssid"])
            network.wifi_connect(n["ssid"], pw, self._wifi_result)
        if n["security"] and n["security"] != "--":
            ask_text(app, n["ssid"], "", connect, password=True)
        else:
            app.confirm("Connect to open network %s?" % n["ssid"], lambda: connect(""), ok="Connect")

    def _wifi_result(self, ok, msg):
        self.app.toast(msg or ("Done" if ok else "Failed"), error=not ok)
        self._net_refresh()
        if ok:
            self._scan()

    # ================================================================ SYSTEM
    def _build_system(self):
        s = self.app.settings
        self.bedfans_note = Lbl("", "muted", "small", wrap=True)
        self.caselight_note = Lbl("", "muted", "small", wrap=True)
        return VBox(
            Section("abg3d-screen", "gear"),
            Row(labelled(None, "Allow to quit abg3d-screen",
                         Lbl("Shows a Quit button on the Settings tab bar", "muted", "small", wrap=True)),
                switch(s.get("allow_quit"), self._allow_quit)),
            Section("Pin Configs", "hash"),
            Row(labelled("fan", "BedFans", self.bedfans_note),
                switch(s.get("pin_bedfans"), lambda w: self._pin("pin_bedfans", w.get_active()))),
            Row(labelled("bulb", "caselight", self.caselight_note),
                switch(s.get("pin_caselight"), lambda w: self._pin("pin_caselight", w.get_active()))))

    def _allow_quit(self, w):
        self._set("allow_quit", w.get_active())
        self.quit_btn.set_visible(w.get_active())

    def _pin(self, key, on):
        self._set(key, on)
        self.app.panels["control"].rebuild_pins()
        self._pin_notes()

    def _pin_notes(self):
        objs = [o.lower() for o in self.mr.objects]
        ready = self.mr.klippy_state == "ready"
        for lbl, obj, cmd in ((self.bedfans_note, "fan_generic bedfans", "SET_FAN_SPEED FAN=BedFans"),
                              (self.caselight_note, "output_pin caselight", "SET_PIN PIN=caselight")):
            found = obj in objs
            lbl.set_text("%s • %s" % (cmd, "found" if found else ("not in Klipper config" if ready
                                                                       else "Klipper not ready")))

    def _quit(self):
        self.app.confirm("Quit abg3d-screen?", lambda: self.app.quit(0), ok="Quit", danger=True)

    # ================================================================ events
    def on_ready(self):
        self._build_macros()
        self._mmu_refresh()
        self._pin_notes()

    def refresh(self):
        page = self.stack.get_visible_child_name()
        if page == "network":
            self._net_refresh()
        elif page == "mmu":
            self._mmu_refresh()
        elif page == "system":
            self._pin_notes()
        elif page == "macros" and not self.macro_box.get_children():
            self._build_macros()


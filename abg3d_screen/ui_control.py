"""Control: temperature, movement (+ Z-offset/speed/flow), BedFans fan presets, caselight LED."""
from gi.repository import Gtk

from .core import Panel
from .icons import Icon
from .widgets import (HBox, IconBtn, Keypad, Lbl, M, Row, Scroller, Section, VBox, add_cls, display_name,
                      fmt_num, radio_row, set_cls, set_temp_cmd, subtabs)

FAN_PRESETS = (0, 20, 50, 80, 100)


def find_obj(objects, kind, name):
    want = ("%s %s" % (kind, name)).lower()
    return next((o for o in objects if o.lower() == want), None)


class ControlPanel(Panel):
    title = "Control"

    def __init__(self, app):
        super().__init__(app)
        self.temp_box = VBox()
        self.fan_box = VBox()
        self.led_box = VBox()
        self.temp_rows = {}
        self.fan_btns = {}
        self.led_switch = None
        self._led_mute = False
        box, self.stack, self.tabs = subtabs([
            ("temp", "thermometer", Scroller(self.temp_box)),
            ("move", "move", Scroller(self._build_move())),
            ("fans", "fan", Scroller(self.fan_box)),
            ("leds", "bulb", Scroller(self.led_box)),
        ], on_change=lambda k: self.refresh())
        self.widget = box
        add_cls(self.widget, "panel")
        self.mr.on("mainsail", lambda _d: self.mr.klippy_state == "ready" and self._build_temp())
        self._build_fans()
        self._build_leds()

    # ============================================================ TEMPERATURE
    def heaters(self):
        objs = self.mr.objects
        out = sorted(o for o in objs if self.mr._is_extruder(o))
        if "heater_bed" in objs:
            out.append("heater_bed")
        chamber = find_obj(objs, "heater_generic", "chamber")
        if chamber:
            out.append(chamber)
        return out

    def _build_temp(self):
        for c in self.temp_box.get_children():
            self.temp_box.remove(c)
            c.destroy()
        self.temp_rows = {}
        small = self.app.ui.small
        for obj in self.heaters():
            name = Lbl(display_name(obj), "title", ellipsize=True)
            val = Lbl("--", "value", "small" if small else None)
            set_btn = Gtk.Button(label="Set")
            set_btn.set_can_focus(False)
            add_cls(set_btn, "primary")
            set_btn.connect("clicked", lambda _b, o=obj: self._keypad_temp(o))
            row = Row(VBox(name, val, spacing=0),
                      IconBtn("minus", None, lambda o=obj: self._bump(o, -5)),
                      IconBtn("plus", None, lambda o=obj: self._bump(o, 5)),
                      set_btn,
                      IconBtn("power", None, lambda o=obj: self.mr.gcode(set_temp_cmd(o, 0))))
            self.temp_box.pack_start(row, False, False, 0)
            self.temp_rows[obj] = val
        if not self.temp_rows:
            self.temp_box.pack_start(Lbl("No heaters available", "muted", xalign=0.5), False, False, 0)
        self.temp_box.pack_start(Section("Presets", "thermometer"), False, False, 0)
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(2)
        flow.set_max_children_per_line(self.app.ui.cols)
        flow.set_column_spacing(M["sp"])
        flow.set_row_spacing(M["sp"])
        for p in self.app.presets():
            temps = "/".join("%g" % t for t in p[1].values())
            b = Gtk.Button(label="%s %s" % (p[0], temps) if temps else p[0])
            b.set_can_focus(False)
            b.connect("clicked", lambda _b, p=p: self.app.apply_preset(p))
            flow.add(b)
        flow.add(IconBtn("cooldown", "Cool Down", self.app.cooldown))
        self.temp_box.pack_start(flow, False, False, 0)
        self.temp_box.show_all()

    def _bump(self, obj, d):
        tgt = self.mr.state(obj, "target", 0) or 0
        self.mr.gcode(set_temp_cmd(obj, max(0, tgt + d)))

    def _keypad_temp(self, obj):
        Keypad(self.app, "%s °C" % display_name(obj), self.mr.state(obj, "target", 0),
               lambda v: self.mr.gcode(set_temp_cmd(obj, v)), decimals=False, maxval=400)

    def _update_temp(self, ch=None):
        for obj, lbl in self.temp_rows.items():
            if ch is not None and obj not in ch:
                continue
            st = self.mr.data.get(obj, {})
            if st.get("temperature") is not None:
                lbl.set_text("%.1f° / %.0f°" % (st["temperature"], st.get("target") or 0))

    # =============================================================== MOVEMENT
    def _build_move(self):
        s = self.app.settings
        ui = self.app.ui
        G = self.mr.gcode
        # icon-only top row: Disable Motors first, then Home All / X / Y / Z
        self.home_btns = {
            "all": IconBtn("home_all", None, lambda: G("G28")),
            "x": IconBtn("home_x", None, lambda: G("G28 X")),
            "y": IconBtn("home_y", None, lambda: G("G28 Y")),
            "z": IconBtn("home_z", None, lambda: G("G28 Z")),
        }
        top = HBox(IconBtn("motors_off", None, lambda: G("M84"), "warn"), *self.home_btns.values(),
                   homogeneous=True)
        self.pos_lbl = Lbl("X --  Y --  Z --", "value", xalign=0.5)
        steps, _ = radio_row([0.1, 1.0, 10.0, 25.0, 50.0, 100.0], float(s.get("move_step", 10)),
                             self._set_step, fmt=fmt_num)
        J = self._jog
        g = Gtk.Grid(row_spacing=M["sp"], column_spacing=M["sp"])
        g.set_row_homogeneous(True)
        g.set_column_homogeneous(True)
        self.e_lbl = Lbl("%g mm" % s.get("e_length", 10), "small", xalign=0.5)
        eb = Gtk.Button()
        eb.add(self.e_lbl)
        eb.set_can_focus(False)
        eb.connect("clicked", lambda _b: Keypad(self.app, "Extrude mm", s.get("e_length", 10),
                                                 self._set_elen, maxval=200))
        cells = [
            (IconBtn("up", None, lambda: J("Y", 1), "jog"), 1, 0),
            (IconBtn("left", None, lambda: J("X", -1), "jog"), 0, 1),
            (IconBtn("home_xy", None, lambda: G("G28 X Y")), 1, 1),
            (IconBtn("right", None, lambda: J("X", 1), "jog"), 2, 1),
            (IconBtn("down", None, lambda: J("Y", -1), "jog"), 1, 2),
            (IconBtn("z_up", None, lambda: J("Z", 1), "jog"), 3, 0),
            (IconBtn("home_z", None, lambda: G("G28 Z")), 3, 1),
            (IconBtn("z_down", None, lambda: J("Z", -1), "jog"), 3, 2),
            (IconBtn("extrude", None, lambda: self._extrude(1)), 4, 0),
            (eb, 4, 1),
            (IconBtn("retract", None, lambda: self._extrude(-1)), 4, 2),
        ]
        for w, col, row in cells:
            g.attach(w, col, row, 1, 1)
        g.set_size_request(-1, ui.touch * 3 + M["sp"] * 2)

        # Z offset / speed / flow
        self.zoff_lbl = Lbl("+0.000", "big", xalign=0.5)
        zsteps, _ = radio_row([0.005, 0.01, 0.025, 0.05, 0.1], float(s.get("zoff_step", 0.01)),
                              self._set_zstep, fmt=fmt_num)
        zrow = HBox(IconBtn("down", None, lambda: self._zadj(-1)), self.zoff_lbl,
                    IconBtn("up", None, lambda: self._zadj(1)),
                    IconBtn("close", None, lambda: G("SET_GCODE_OFFSET Z=0 MOVE=1")),
                    IconBtn("check", None, self._save_offset, "primary"), homogeneous=True)
        self.speed_lbl = Lbl("100%", "big", xalign=0.5)
        self.flow_lbl = Lbl("100%", "big", xalign=0.5)
        box = VBox(top, self.pos_lbl, steps, g,
                   Section("Z offset", "zoffset"), zsteps, zrow,
                   Section("Speed", "speed"), self._factor_row(self.speed_lbl, "M220", "speed_factor", 10),
                   Section("Flow", "flow"), self._factor_row(self.flow_lbl, "M221", "extrude_factor", 1))
        return box

    def _factor_row(self, lbl, cmd, field, step):
        def cur():
            return round((self.mr.state("gcode_move", field, 1.0) or 1.0) * 100)

        def setv(v):
            self.mr.gcode("%s S%d" % (cmd, max(1, int(v))))
        return HBox(IconBtn("minus", None, lambda: setv(cur() - step)), lbl,
                    IconBtn("plus", None, lambda: setv(cur() + step)),
                    IconBtn("keyboard", None, lambda: Keypad(self.app, "%s %%" % ("Speed" if cmd == "M220" else "Flow"),
                                                           cur(), setv, decimals=False, maxval=500)),
                    IconBtn("refresh", None, lambda: setv(100)), homogeneous=True)

    def _set_step(self, v):
        self.app.settings["move_step"] = v
        self.app.save_settings()

    def _set_elen(self, v):
        self.app.settings["e_length"] = v
        self.e_lbl.set_text("%g mm" % v)
        self.app.save_settings()

    def _set_zstep(self, v):
        self.app.settings["zoff_step"] = v
        self.app.save_settings()

    def _jog(self, axis, sign):
        s = self.app.settings
        dist = float(s.get("move_step", 10)) * sign
        feed = float(s.get("z_speed" if axis == "Z" else "xy_speed", 10)) * 60
        self.mr.gcode("G91\nG1 %s%s F%d\nG90" % (axis, fmt_num(dist), feed))

    def _extrude(self, sign):
        s = self.app.settings
        if not self.mr.state(self.mr.state("toolhead", "extruder", "extruder"), "can_extrude", True):
            self.app.toast("Extruder too cold", error=True)
            return
        self.mr.gcode("M83\nG1 E%s F%d" % (fmt_num(float(s.get("e_length", 10)) * sign),
                                          float(s.get("e_speed", 5)) * 60))

    def _zadj(self, sign):
        st = float(self.app.settings.get("zoff_step", 0.01)) * sign
        self.mr.gcode("SET_GCODE_OFFSET Z_ADJUST=%s MOVE=1" % fmt_num(st))

    def _save_offset(self):
        cmd = "Z_OFFSET_APPLY_PROBE" if self.mr.config.get("probe") else "Z_OFFSET_APPLY_ENDSTOP"
        self.app.confirm("Apply Z offset with %s?\nRun SAVE_CONFIG to persist." % cmd,
                         lambda: self.mr.gcode(cmd))

    def _update_move(self):
        pos = self.mr.state("gcode_move", "gcode_position") or self.mr.state("toolhead", "position")
        if pos:
            self.pos_lbl.set_text("X %.2f  Y %.2f  Z %.2f" % tuple(pos[:3]))
        homed = self.mr.state("toolhead", "homed_axes", "") or ""
        for ax, b in self.home_btns.items():
            set_cls(b, "homed", all(a in homed for a in "xyz") if ax == "all" else ax in homed)
        ho = self.mr.state("gcode_move", "homing_origin")
        if ho:
            self.zoff_lbl.set_text("%+.3f" % ho[2])
        self.speed_lbl.set_text("%d%%" % round((self.mr.state("gcode_move", "speed_factor", 1) or 1) * 100))
        self.flow_lbl.set_text("%d%%" % round((self.mr.state("gcode_move", "extrude_factor", 1) or 1) * 100))

    # =================================================================== FANS
    def rebuild_pins(self):
        self._build_fans()
        self._build_leds()
        self.refresh()

    def _disabled_note(self, box, what, key):
        box.pack_start(HBox(Icon("info", M["icon_s"]),
                            Lbl("%s control is disabled. Enable it in Settings › System › Pin Configs."
                                % what, "muted", wrap=True), expand=(1,)), False, False, 0)
        box.pack_start(IconBtn("settings", "Open Settings",
                               lambda: (self.app.show_panel("settings"),
                                        self.app.panels["settings"].open_tab("system"))), False, False, 0)

    def _preset_row(self, key, send):
        btns = {}
        row = HBox(homogeneous=True)
        for pct in FAN_PRESETS:
            b = Gtk.Button(label="%d%%" % pct)
            b.set_can_focus(False)
            b.connect("clicked", lambda _b, p=pct: send(p))
            row.pack_start(b, True, True, 0)
            btns[pct] = b
        self.fan_btns[key] = btns
        return row

    def _build_fans(self):
        for c in self.fan_box.get_children():
            self.fan_box.remove(c)
            c.destroy()
        self.fan_btns = {}
        objs = self.mr.objects
        if "fan" in objs:
            self.fan_box.pack_start(Section("Part cooling fan", "fan"), False, False, 0)
            self.fan_box.pack_start(self._preset_row("fan", lambda p: self.mr.gcode("M106 S%d" % round(p * 2.55))),
                                    False, False, 0)
        self.fan_box.pack_start(Section("BedFans", "fan"), False, False, 0)
        self.bedfans_obj = find_obj(objs, "fan_generic", "BedFans")
        if not self.app.settings.get("pin_bedfans"):
            self._disabled_note(self.fan_box, "BedFans", "pin_bedfans")
        else:
            if not self.bedfans_obj and self.mr.klippy_state == "ready":
                self.fan_box.pack_start(Lbl("[fan_generic BedFans] not found in Klipper config", "warn-text",
                                            wrap=True), False, False, 0)
            self.fan_box.pack_start(self._preset_row(
                "bedfans", lambda p: self.mr.gcode("SET_FAN_SPEED FAN=BedFans SPEED=%.2f" % (p / 100.0))),
                False, False, 0)
        self.fan_box.show_all()

    def _update_fans(self, ch=None):
        targets = {"fan": "fan", "bedfans": getattr(self, "bedfans_obj", None)}
        for key, btns in self.fan_btns.items():
            obj = targets.get(key)
            if not obj or (ch is not None and obj not in ch):
                continue
            pct = round((self.mr.state(obj, "speed", 0) or 0) * 100)
            for p, b in btns.items():
                set_cls(b, "primary", p == pct)

    # =================================================================== LEDS
    def _build_leds(self):
        for c in self.led_box.get_children():
            self.led_box.remove(c)
            c.destroy()
        self.led_switch = None
        self.led_box.pack_start(Section("Case light", "bulb"), False, False, 0)
        self.caselight_obj = find_obj(self.mr.objects, "output_pin", "caselight")
        if not self.app.settings.get("pin_caselight"):
            self._disabled_note(self.led_box, "Case light", "pin_caselight")
        else:
            if not self.caselight_obj and self.mr.klippy_state == "ready":
                self.led_box.pack_start(Lbl("[output_pin caselight] not found in Klipper config", "warn-text",
                                            wrap=True), False, False, 0)
            sw = Gtk.Switch()
            sw.set_can_focus(False)
            sw.set_valign(Gtk.Align.CENTER)
            sw.connect("notify::active", self._led_toggled)
            self.led_switch = sw
            self.led_state = Lbl("Off", "muted")
            self.led_box.pack_start(Row(VBox(Lbl("Case light", "title"), self.led_state, spacing=0), sw),
                                    False, False, 0)
        self.led_box.show_all()

    def _led_toggled(self, sw, _p):
        if self._led_mute:
            return
        self.mr.gcode("SET_PIN PIN=caselight VALUE=%s" % ("1.00" if sw.get_active() else "0.00"))

    def _update_leds(self, ch=None):
        obj = getattr(self, "caselight_obj", None)
        if not self.led_switch or not obj or (ch is not None and obj not in ch):
            return
        on = (self.mr.state(obj, "value", 0) or 0) > 0
        self._led_mute = True
        self.led_switch.set_active(on)
        self._led_mute = False
        self.led_state.set_text("On" if on else "Off")

    # ================================================================ events
    def on_ready(self):
        self._build_temp()
        self._build_fans()
        self._build_leds()

    def refresh(self):
        page = self.stack.get_visible_child_name()
        if page == "move":
            self._update_move()
        elif page == "temp":
            self._update_temp()
        elif page == "fans":
            self._update_fans()
        elif page == "leds":
            self._update_leds()

    def on_status(self, ch):
        page = self.stack.get_visible_child_name()
        if page == "move" and ("gcode_move" in ch or "toolhead" in ch):
            self._update_move()
        elif page == "temp":
            self._update_temp(ch)
        elif page == "fans":
            self._update_fans(ch)
        elif page == "leds":
            self._update_leds(ch)

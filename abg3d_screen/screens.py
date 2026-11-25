"""Tab pages. Each page is a Frame that is rebuilt whenever the theme changes."""
import tkinter as tk


from .detect import MMU_NAMES
from .monitor import MonitorView
from .page import Page
from .mmu import is_active, load_mmu_commands
from .widgets import ScrollList, Switch
from . import network
from .keyboard import OnScreenKeyboard
from .wizard import load_printers

JOG_FEED_XY, JOG_FEED_Z = 3000, 600
PRINT_ACTIVE = ("printing", "paused")


class HomePage(Page):
    """Home: real-time temperature monitor in the centre, job controls on the right."""

    def build(self):
        pad = self.px(12)
        right = tk.Frame(self, bg=self.t["bg"], width=self.px(236))
        right.pack(side="right", fill="y", padx=(pad // 2, pad), pady=pad)
        right.pack_propagate(False)
        self.monitor = MonitorView(self, self.app)
        self.monitor.pack(side="left", fill="both", expand=True, padx=(pad, pad // 2), pady=pad)

        grid = tk.Frame(right, bg=self.t["bg"])
        grid.pack(fill="both", expand=True)
        h, fs = self.px(78), 13
        self.btn_pause = self.button(grid, "Pause", self._toggle_pause, "primary", height=h,
                                     font=fs, icon=self.app.icon("pause", 28))
        self.btn_cancel = self.button(grid, "Cancel", lambda: self._print_action("cancel"),
                                      "danger", confirm=True, height=h, font=fs,
                                      icon=self.app.icon("cancel", 28))
        self.btn_home = self.button(grid, "Home All", lambda: self.gcode("G28", "Homing all axes"),
                                    height=h, font=fs, icon=self.app.icon("home_all", 28))
        self.btn_cool = self.button(grid, "Cool Down",
                                    lambda: self.gcode("M104 S0\nM140 S0\nM107", "Cooling down"),
                                    height=h, font=fs, icon=self.app.icon("temps", 28))
        self.btn_temps = self.button(grid, "Set Temps", self._open_temps, height=h, font=fs,
                                     icon=self.app.icon("temps", 28))
        self.btn_estop = self.button(grid, "E-Stop", self._estop, "danger", confirm=True,
                                     height=h, font=fs, icon=self.app.icon("stop", 28))
        cells = [self.btn_pause, self.btn_cancel, self.btn_home,
                 self.btn_cool, self.btn_temps, self.btn_estop]
        for i, btn in enumerate(cells):
            btn.grid(row=i // 2, column=i % 2, sticky="nsew", padx=3, pady=3)
        for col in range(2):
            grid.columnconfigure(col, weight=1, uniform="home")
        for row in range(3):
            grid.rowconfigure(row, weight=1, uniform="homerow")
        self._ext_target = 0.0
        self._bed_target = 0.0
        self._state = "standby"

    def refresh(self, st, online, demo):
        ext = st.get("extruder") or {}
        bed = st.get("heater_bed") or {}
        self._ext_target = float(ext.get("target") or 0)
        self._bed_target = float(bed.get("target") or 0)
        self.monitor.refresh(st)
        state = (st.get("print_stats") or {}).get("state") or "standby"
        self._state = state
        active = state in PRINT_ACTIVE
        paused = state == "paused"
        self.btn_pause.set_text("Resume" if paused else "Pause")
        self.btn_pause.set_icon(self.app.icon("play" if paused else "pause", 28))
        self.btn_pause.set_enabled(active)
        self.btn_cancel.set_enabled(active)

    def _open_temps(self):
        self.app.open_temp_modal(self._ext_target, self._bed_target)

    def _toggle_pause(self):
        self._print_action("resume" if self._state == "paused" else "pause")

    def _print_action(self, action):
        self.app.run_async(lambda: self.app.backend.print_action(action), f"Print {action} sent")

    def _estop(self):
        self.app.run_async(self.app.backend.emergency_stop, "Emergency stop sent")


class ControlPage(Page):
    """Control sub-tabs: Movement, Fan Control and LED Control."""

    STEPS = [0.1, 1.0, 10.0]
    TABS = [("movement", "Movement", "move"), ("fan", "Fan Control", "fan"),
            ("led", "LED Control", "led")]
    FAN_STEPS = [("Off", 0), ("25%", 64), ("50%", 128), ("75%", 191), ("100%", 255)]
    LED_COLOURS = [("Off", 0, 0, 0), ("White", 1, 1, 1), ("Red", 1, 0, 0),
                   ("Green", 0, 1, 0), ("Blue", 0, 0, 1)]

    def build(self):
        pad = self.px(12)
        self.step = 1.0
        self.jog_buttons = []
        self.step_buttons = {}
        self.extra_buttons = []
        self._extras_key = None
        self._leds_key = None
        self.tab = None

        bar = tk.Frame(self, bg=self.t["bg"])
        bar.pack(side="top", fill="x", padx=pad, pady=(pad, 0))
        self.tab_btns = {}
        for i, (key, text, icon) in enumerate(self.TABS):
            btn = self.button(bar, text, lambda k=key: self._set_tab(k), "secondary", height=64,
                              font=12, icon=self.app.icon(icon, 26))
            btn.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else self.px(6), 0))
            self.tab_btns[key] = btn

        self.panes = {"movement": self._build_movement(), "fan": self._build_fan(),
                      "led": self._build_led()}
        self._set_tab("movement")

    def _set_tab(self, key):
        if key == self.tab:
            return
        self.tab = key
        for pane in self.panes.values():
            pane.pack_forget()
        self.panes[key].pack(fill="both", expand=True, padx=self.px(12), pady=self.px(12))
        for name, btn in self.tab_btns.items():
            btn.set_style("primary" if name == key else "secondary")

    # ---- Movement -------------------------------------------------------
    def _build_movement(self):
        pad = self.px(12)
        pane = self.panel(self)
        homing = tk.Frame(pane, bg=self.t["panel"])
        homing.pack(fill="x", padx=pad, pady=(pad, 0))
        h = self.px(66)
        self.button(homing, "Disable Motors", lambda: self.gcode("M18", "Motors released"),
                    height=h, font=12, icon=self.app.icon("motor_off", 26)).pack(
            side="left", fill="x", expand=True, padx=3)
        for name, cmd, icon in (("Home All", "G28", "home_all"), ("X", "G28 X", "home_x"),
                                ("Y", "G28 Y", "home_y"), ("Z", "G28 Z", "home_z"),
                                ("Home XY", "G28 X Y", "home_xy")):
            self.button(homing, name, lambda c=cmd, n=name: self.gcode(c, f"Homing {n}"),
                        height=h, font=12, icon=self.app.icon(icon, 26)).pack(
                side="left", fill="x", expand=True, padx=3)

        grid = tk.Frame(pane, bg=self.t["panel"])
        grid.pack(expand=True, pady=self.px(6))

        def jog(text, axis, sign, row, col):
            btn = self.button(grid, text, lambda: self._jog(axis, sign), height=56)
            btn.grid(row=row, column=col, sticky="nsew", padx=self.px(4), pady=self.px(3))
            self.jog_buttons.append(btn)

        jog("Y+", "Y", 1, 0, 1)
        jog("X-", "X", -1, 1, 0)
        jog("X+", "X", 1, 1, 2)
        jog("Y-", "Y", -1, 2, 1)
        jog("Z+", "Z", 1, 0, 3)
        jog("Z-", "Z", -1, 2, 3)
        for col in range(4):
            grid.columnconfigure(col, minsize=self.px(64))
        for row in range(3):
            grid.rowconfigure(row, minsize=self.px(56))

        steps = tk.Frame(pane, bg=self.t["panel"])
        steps.pack(fill="x", padx=pad, pady=(0, self.px(6)))
        for val in self.STEPS:
            btn = self.button(steps, f"{val:g} mm", lambda v=val: self._set_step(v),
                              "primary" if val == self.step else "secondary", height=38)
            btn.pack(side="left", fill="x", expand=True, padx=3)
            self.step_buttons[val] = btn

        # Z-Tilt and QGL appear here only when the printer config defines them
        self.extras = tk.Frame(pane, bg=self.t["panel"])
        self.extras.pack(fill="x", padx=pad, pady=(0, self.px(4)))
        self.label(pane, "Jogging is locked while a print is running.", 10,
                   color=self.t["subtext"], bg=self.t["panel"]).pack(anchor="w", padx=pad,
                                                                    pady=(0, pad))
        return pane

    def _set_step(self, value):
        self.step = value
        for val, btn in self.step_buttons.items():
            btn.set_style("primary" if val == value else "secondary")

    def _jog(self, axis, sign):
        dist = sign * self.step
        feed = JOG_FEED_Z if axis == "Z" else JOG_FEED_XY
        self.gcode(f"G91\nG1 {axis}{dist:g} F{feed}\nG90")

    def _build_extras(self, key):
        self._extras_key = key
        for child in self.extras.winfo_children():
            child.destroy()
        self.extra_buttons = []
        ztilt, qgl = key
        if ztilt:
            self.extra_buttons.append(self.button(
                self.extras, "Z-Tilt", lambda: self.gcode("Z_TILT_ADJUST", "Z tilt adjust"),
                height=44))
        if qgl:
            self.extra_buttons.append(self.button(
                self.extras, "QGL", lambda: self.gcode("QUAD_GANTRY_LEVEL", "Quad gantry level"),
                height=44))
        for btn in self.extra_buttons:
            btn.pack(side="left", fill="x", expand=True, padx=3)

    # ---- Fan Control ------------------------------------------------------
    def _build_fan(self):
        pad = self.px(12)
        pane = self.panel(self)
        self.label(pane, "Part fan", 14, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, 0))
        row = tk.Frame(pane, bg=self.t["panel"])
        row.pack(fill="x", padx=pad, pady=pad)
        for name, value in self.FAN_STEPS:
            self.button(row, name, lambda v=value, n=name: self.gcode(f"M106 S{v}", f"Part fan {n}"),
                        height=90, font=13).pack(side="left", fill="x", expand=True, padx=3)
        self.label(pane, "Each button sends M106 straight away.", 10, color=self.t["subtext"],
                   bg=self.t["panel"]).pack(anchor="w", padx=pad)
        return pane

    # ---- LED Control ------------------------------------------------------
    def _build_led(self):
        pad = self.px(12)
        pane = self.panel(self)
        self.label(pane, "LED colour", 14, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, 0))
        self.led_box = tk.Frame(pane, bg=self.t["panel"])
        self.led_box.pack(fill="both", expand=True, padx=pad, pady=pad)
        return pane

    def _build_leds(self, names):
        for child in self.led_box.winfo_children():
            child.destroy()
        if not names:
            self.label(self.led_box, "No LEDs found. Add a neopixel, dotstar or led section to "
                                     "printer.cfg to control them here.", 11,
                       color=self.t["subtext"], bg=self.t["panel"], wraplength=self.px(520),
                       justify="left").pack(anchor="w", pady=self.px(8))
            return
        for name in names:
            row = tk.Frame(self.led_box, bg=self.t["panel"])
            row.pack(fill="x", pady=(0, self.px(8)))
            self.label(row, name, 11, "bold", bg=self.t["panel"]).pack(anchor="w")
            buttons = tk.Frame(row, bg=self.t["panel"])
            buttons.pack(fill="x")
            for label, r, g, b in self.LED_COLOURS:
                self.button(buttons, label,
                            lambda n=name, rr=r, gg=g, bb=b: self.gcode(
                                f"SET_LED LED={n} RED={rr} GREEN={gg} BLUE={bb} TRANSMIT=1",
                                f"{n} {label}"),
                            height=44, font=11).pack(side="left", fill="x", expand=True, padx=3)

    # ---- lifecycle --------------------------------------------------------
    def refresh(self, st, online, demo):
        state = (st.get("print_stats") or {}).get("state") or "standby"
        locked = state in PRINT_ACTIVE
        det = self.app.backend.detection
        key = (bool(det.get("ztilt")), bool(det.get("qgl")))
        if key != self._extras_key:
            self._build_extras(key)
        leds = tuple(det.get("leds") or [])
        if leds != self._leds_key:
            self._leds_key = leds
            self._build_leds(list(leds))
        for btn in self.jog_buttons + self.extra_buttons:
            btn.set_enabled(not locked)


class MMUPage(Page):
    """Shows controls for the detected MMU only. Nothing is sent when no MMU is active."""

    def build(self):
        self.key = None
        self.body = tk.Frame(self, bg=self.t["bg"])
        self.body.pack(fill="both", expand=True, padx=self.px(12), pady=self.px(12))

    def on_show(self):
        self._rebuild(self.app.backend.detection.get("mmu", "none"))

    def refresh(self, st, online, demo):
        key = self.app.backend.detection.get("mmu", "none")
        if key != self.key:
            self._rebuild(key)

    def _rebuild(self, key):
        for child in self.body.winfo_children():
            child.destroy()
        self.key = key
        panel = self.panel(self.body)
        panel.pack(fill="both", expand=True)
        cfg = load_mmu_commands().get(key) if is_active({"mmu": key}) else None
        if not cfg:
            self.label(panel, "No MMU detected", 16, "bold", bg=self.t["panel"]).pack(
                pady=(self.px(40), self.px(8)))
            self.label(panel, "This tab turns on automatically when Happy Hare, Box Turtle / AFC "
                              "or KTC is found on this printer.",
                       11, color=self.t["subtext"], bg=self.t["panel"],
                       wraplength=self.px(560), justify="center").pack()
            return

        pad = self.px(12)
        gates = int(cfg.get("gates", 0))
        self.label(panel, f"{MMU_NAMES.get(key, key)}  ·  {gates} gates", 14, "bold",
                   bg=self.t["panel"]).pack(anchor="w", padx=pad, pady=(pad, 0))
        if cfg.get("note"):
            self.label(panel, cfg["note"], 9, color=self.t["subtext"], bg=self.t["panel"],
                       wraplength=self.px(640), justify="left").pack(anchor="w", padx=pad)
        grid = tk.Frame(panel, bg=self.t["panel"])
        grid.pack(fill="both", expand=True, padx=pad, pady=pad)

        items = [(a["label"], a["gcode"]) for a in cfg.get("actions", [])]
        for i in range(gates):
            if cfg.get("select_template"):
                items.append((cfg.get("select_label", "Gate {n}").format(n=i),
                              cfg["select_template"].format(n=i)))
            for action in cfg.get("gate_actions", []):
                items.append((action["label"].format(n=i), action["gcode"].format(n=i)))

        cols = 4
        for i, (text, script) in enumerate(items):
            self.button(grid, text, lambda s=script, t=text: self.gcode(s, t), height=56).grid(
                row=i // cols, column=i % cols, sticky="nsew", padx=3, pady=3)
        for col in range(cols):
            grid.columnconfigure(col, weight=1)


class SystemPage(Page):
    """Printer and host status on the left; Klipper and Host Control on the right."""
    ROWS = [("host", "Host"), ("os", "System"), ("ip", "IP address"),
            ("klipper_dir", "Klipper"), ("config_dir", "Config"),
            ("klipper_service", "Klipper service"), ("moonraker_service", "Moonraker service"),
            ("mcu", "MCU detected"), ("mmu_name", "MMU"), ("mode", "Mode")]

    def build(self):
        pad = self.px(12)
        actions = tk.Frame(self, bg=self.t["bg"], width=self.px(230))
        actions.pack(side="right", fill="y", padx=(0, pad), pady=pad)
        actions.pack_propagate(False)
        info = self.panel(self)
        info.pack(side="left", fill="both", expand=True, padx=pad, pady=pad)

        self.values = {}
        for key, text in self.ROWS:
            row = tk.Frame(info, bg=self.t["panel"])
            row.pack(fill="x", padx=pad, pady=self.px(3))
            self.label(row, text, 10, color=self.t["subtext"], bg=self.t["panel"]).pack(side="left")
            value = self.label(row, "...", 10, bg=self.t["panel"], wraplength=self.px(300),
                               justify="right")
            value.pack(side="right")
            self.values[key] = value

        self.label(actions, "Klipper", 10, color=self.t["subtext"], bg=self.t["bg"]).pack(
            anchor="w", pady=(0, self.px(2)))
        self.button(actions, "Restart Klipper",
                    lambda: self._do(self.app.backend.restart_klipper, "Restarting Klipper..."),
                    "secondary", confirm=True, height=40).pack(fill="x", pady=(0, self.px(6)))
        self.button(actions, "Firmware restart",
                    lambda: self._do(self.app.backend.firmware_restart, "Firmware restart sent"),
                    "secondary", confirm=True, height=40).pack(fill="x", pady=(0, self.px(6)))
        self.button(actions, "Restart Moonraker",
                    lambda: self._do(self.app.backend.restart_moonraker, "Restarting Moonraker..."),
                    "secondary", confirm=True, height=40).pack(fill="x", pady=(0, self.px(10)))
        self.label(actions, "Host Control", 10, color=self.t["subtext"], bg=self.t["bg"]).pack(
            anchor="w", pady=(0, self.px(2)))
        self.button(actions, "Reboot host",
                    lambda: self._do(self.app.backend.reboot, "Rebooting..."),
                    "danger", confirm=True, height=40).pack(fill="x", pady=(0, self.px(6)))
        self.button(actions, "Shut down host",
                    lambda: self._do(self.app.backend.shutdown, "Shutting down..."),
                    "danger", confirm=True, height=40).pack(fill="x")

    def _do(self, fn, message):
        self.app.run_async(fn, message)

    def refresh(self, st, online, demo):
        det = self.app.backend.detection
        for key, _text in self.ROWS:
            if key == "mode":
                text = "Live (Moonraker)" if online else "Demo (no Moonraker)"
            else:
                text = str(det.get(key, "..."))
            self.values[key].configure(text=text)


class SettingsPage(Page):
    """Settings in icon-only sub-tabs: Appearance, MMU, Macros, Network and System."""

    TABS = [("appearance", "palette"), ("mmu", "hotend"), ("macros", "script"),
            ("network", "wifi"), ("system", "gear")]

    def build(self):
        pad = self.px(12)
        self.printers = load_printers()
        self.sub = None
        self.dropdown = None
        self._macro_key = None
        self._pin_key = None
        self._quit_shown = False
        self._pending = None

        bar = tk.Frame(self, bg=self.t["bg"])
        bar.pack(side="top", fill="x", padx=pad, pady=(pad, 0))
        self.tab_btns = {}
        for i, (key, icon) in enumerate(self.TABS):
            btn = self.button(bar, "", lambda k=key: self._set_sub(k), "secondary", height=56,
                              icon=self.app.icon(icon, 28))
            btn.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else self.px(6), 0))
            self.tab_btns[key] = btn

        self.panes = {"appearance": self._appearance(), "mmu": self._mmu(),
                      "macros": self._macros(), "network": self._network(),
                      "system": self._system()}
        self._set_sub("appearance")

    def _set_sub(self, key):
        if key == self.sub:
            return
        self.sub = key
        for pane in self.panes.values():
            pane.pack_forget()
        self.panes[key].pack(fill="both", expand=True, padx=self.px(12), pady=self.px(12))
        for name, btn in self.tab_btns.items():
            btn.set_style("primary" if name == key else "secondary")
        if key == "network":
            self._refresh_network()

    # ---- Appearance: themes and mouse pointer -----------------------------
    def _appearance(self):
        pane = self.panel(self)
        pad = self.px(12)
        self.label(pane, "Themes", 12, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, self.px(4)))
        self.theme_btn = self.button(pane, "", self._toggle_dropdown, "secondary", height=44,
                                     font=11)
        self.theme_btn.pack(fill="x", padx=pad)
        self.pointer_sw = Switch(pane, "Mouse pointer", self.app.toggle_pointer, self.app,
                                 on=bool(self.app.settings.get("mouse_pointer")), height=44)
        self.pointer_sw.pack(fill="x", padx=pad, pady=(self.px(14), pad))
        return pane

    def _toggle_dropdown(self):
        if self.dropdown is not None:
            self._close_dropdown()
            return
        btn = self.theme_btn
        self.dropdown = ScrollList(btn.master, self.app, visible_rows=3, row_h=34,
                                   bg=self.t["panel_alt"])
        self.dropdown.place(x=btn.winfo_x(), y=btn.winfo_y() + btn.winfo_height() + self.px(4),
                            width=btn.winfo_width())
        self.dropdown.lift()
        for key, theme in self.app.themes.items():
            style = "primary" if key == self.app.theme.key else "secondary"
            self.dropdown.add(theme.name, lambda k=key: self._choose(k), style)

    def _choose(self, key):
        self._close_dropdown()
        self.app.root.after_idle(lambda: self.app.apply_theme(key))

    def _close_dropdown(self):
        if self.dropdown is not None:
            self.dropdown.destroy()
            self.dropdown = None

    # ---- MMU ----------------------------------------------------------------
    def _mmu(self):
        pane = self.panel(self)
        pad = self.px(12)
        self.mmu_sw = Switch(pane, "Enable MMU", self.app.toggle_mmu, self.app,
                             on=bool(self.app.settings.get("mmu_enabled")), height=44)
        self.mmu_sw.pack(fill="x", padx=pad, pady=(pad, 0))
        self.mmu_info = self.label(pane, "", 10, color=self.t["subtext"], bg=self.t["panel"],
                                   wraplength=self.px(520), justify="left")
        self.mmu_info.pack(anchor="w", padx=pad, pady=(self.px(10), 0))
        self.warning = tk.Label(pane, text="", fg=self.t["danger"], bg=self.t["panel"],
                                font=self.font(11, "bold"), wraplength=self.px(520), justify="left")
        self.warning.pack(anchor="w", padx=pad, pady=(self.px(8), 0))
        return pane

    # ---- Macros -------------------------------------------------------------
    def _macros(self):
        pane = self.panel(self)
        pad = self.px(12)
        self.label(pane, "Klipper macros", 12, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, 0))
        self.label(pane, "Tap a macro to cycle: normal, favourite (star), hidden.", 10,
                   color=self.t["subtext"], bg=self.t["panel"]).pack(anchor="w", padx=pad)
        self.macro_list = ScrollList(pane, self.app, visible_rows=4, row_h=34,
                                     bg=self.t["panel"])
        self.macro_list.pack(fill="both", expand=True, padx=pad, pady=(self.px(6), pad))
        return pane

    def _refresh_macros(self, macros):
        s = self.app.settings
        fav = sorted(s.get("macro_favs") or [])
        hid = sorted(s.get("macro_hidden") or [])
        key = (tuple(macros), tuple(fav), tuple(hid))
        if key == self._macro_key:
            return
        self._macro_key = key
        self.macro_list.clear()
        if not macros:
            self.macro_list.add("No macros found. Define [gcode_macro NAME] in printer.cfg.",
                                None, "ghost")
            return
        for name in macros:
            if name in hid:
                text, style = f"hidden: {name}", "ghost"
            elif name in fav:
                text, style = f"\u2605 {name}", "primary"
            else:
                text, style = name, "secondary"
            self.macro_list.add(text, lambda n=name: self._cycle_macro(n), style)

    def _cycle_macro(self, name):
        fav = set(self.app.settings.get("macro_favs") or [])
        hid = set(self.app.settings.get("macro_hidden") or [])
        if name in hid:
            hid.discard(name)
        elif name in fav:
            fav.discard(name)
            hid.add(name)
        else:
            fav.add(name)
        self.app.settings.update(macro_favs=sorted(fav), macro_hidden=sorted(hid))

    # ---- Network ------------------------------------------------------------
    def _network(self):
        pane = self.panel(self)
        pad = self.px(12)
        left = tk.Frame(pane, bg=self.t["panel"], width=self.px(220))
        left.pack(side="left", fill="y", padx=pad, pady=pad)
        left.pack_propagate(False)
        self.net_info = self.label(left, "Loading...", 10, color=self.t["text"],
                                   bg=self.t["panel"], wraplength=self.px(200), justify="left")
        self.net_info.pack(anchor="w")
        self.button(left, "Scan", self._refresh_network, "primary", height=44, font=11).pack(
            side="bottom", fill="x")

        right = tk.Frame(pane, bg=self.t["panel"])
        right.pack(side="left", fill="both", expand=True, padx=(0, pad), pady=pad)
        self.net_msg = self.label(right, "", 10, color=self.t["subtext"], bg=self.t["panel"],
                                  wraplength=self.px(360), justify="left")
        self.net_msg.pack(anchor="w")
        self.net_list = ScrollList(right, self.app, visible_rows=3, row_h=36, bg=self.t["panel"])
        self.net_list.pack(fill="x", pady=(self.px(4), 0))

        self.pw_box = tk.Frame(right, bg=self.t["panel"])
        self.pw_label = self.label(self.pw_box, "", 11, "bold", bg=self.t["panel"])
        self.pw_label.pack(anchor="w")
        self.pw_entry = tk.Entry(self.pw_box, font=("DejaVu Sans", self.font(14)[1]),
                                 bg=self.t["panel_alt"], fg=self.t["text"],
                                 insertbackground=self.t["text"], relief="flat", bd=6, show="\u2022")
        self.pw_entry.pack(fill="x", pady=(self.px(4), self.px(4)))
        self.pw_entry.bind("<ButtonRelease-1>", lambda _e: self._show_kb())
        row = tk.Frame(self.pw_box, bg=self.t["panel"])
        row.pack(fill="x")
        self.button(row, "Connect", self._connect, "primary", height=44, font=11).pack(
            side="left", fill="x", expand=True, padx=(0, self.px(4)))
        self.button(row, "Cancel", self._cancel_pw, "ghost", height=44, font=11).pack(
            side="left", fill="x", expand=True)
        self.pw_kb = OnScreenKeyboard(self.pw_box, self.app, on_key=self._pw_insert,
                                      on_delete=self._pw_delete, on_move=self._pw_move,
                                      on_send=self._connect, on_hide=self._hide_kb)
        return pane

    def _refresh_network(self):
        self.app.run_async(self._gather_network, None, on_done=self._render_network)

    def _gather_network(self):
        info = network.status()
        return info, (network.scan() if info["nmcli"] else [])

    def _render_network(self, result):
        info, nets = result
        online = "online" if self.app.backend.online else "offline"
        mcu = self.app.backend.detection.get("mcu_status", "offline")
        self.net_info.configure(text=(f"IP: {info['ip']}\nWi-Fi: {info['ssid'] or 'not connected'}\n"
                                      f"Interface: {info['iface'] or '-'}\nMoonraker: {online}\n"
                                      f"MCU: {mcu}"))
        if not info["nmcli"]:
            self.net_msg.configure(text="Wi-Fi management needs NetworkManager (nmcli). Status is still shown.")
        elif nets:
            self.net_msg.configure(text=f"{len(nets)} networks found. Tap one to connect.")
        else:
            self.net_msg.configure(text="No networks found. Tap Scan to try again.")
        self.net_list.clear()
        for n in nets:
            label = f"{n['ssid']}   {n['signal']}%" + ("   secured" if n["secured"] else "")
            style = "primary" if n["ssid"] == info["ssid"] else "secondary"
            self.net_list.add(label, lambda net=n: self._pick(net), style)

    def _pick(self, net):
        if not net["secured"]:
            self._connect_to(net["ssid"], "")
            return
        self._pending = net["ssid"]
        self.pw_label.configure(text=f"Password for {net['ssid']}")
        self.pw_entry.delete(0, "end")
        if not self.pw_box.winfo_ismapped():
            self.pw_box.pack(fill="x", pady=(self.px(8), 0))

    def _show_kb(self):
        if not self.pw_kb.winfo_ismapped():
            self.pw_kb.pack(fill="x", pady=(self.px(4), 0))

    def _hide_kb(self):
        self.pw_kb.pack_forget()

    def _pw_insert(self, ch):
        self.pw_entry.insert(tk.INSERT, ch)

    def _pw_delete(self):
        pos = self.pw_entry.index(tk.INSERT)
        if pos > 0:
            self.pw_entry.delete(pos - 1)

    def _pw_move(self, delta):
        pos = self.pw_entry.index(tk.INSERT)
        self.pw_entry.icursor(max(0, min(len(self.pw_entry.get()), pos + delta)))

    def _connect(self):
        if self._pending:
            self._connect_to(self._pending, self.pw_entry.get())

    def _cancel_pw(self):
        self._pending = None
        self._hide_kb()
        self.pw_box.pack_forget()

    def _connect_to(self, ssid, password):
        self._hide_kb()
        self.net_msg.configure(text=f"Connecting to {ssid}...")
        self.app.run_async(lambda: network.connect(ssid, password), None,
                           on_done=lambda result: self._connected(result))

    def _connected(self, result):
        ok, message = result
        self._pending = None
        self.pw_entry.delete(0, "end")
        self.pw_box.pack_forget()
        self.app.toast(f"Wi-Fi: {message}", error=not ok)
        self._refresh_network()

    # ---- System: quit and pin assignments -----------------------------------
    def _system(self):
        pane = self.panel(self)
        pad = self.px(12)
        top = tk.Frame(pane, bg=self.t["panel"])
        top.pack(fill="x", padx=pad, pady=(pad, 0))
        self.quit_sw = Switch(top, "Allow to quit", self.app.toggle_quit, self.app,
                              on=bool(self.app.settings.get("allow_quit")), height=44)
        self.quit_sw.pack(fill="x")
        self.quit_btn = self.button(top, "Quit", self.app.quit, "ghost", confirm=True,
                                    height=64, font=12, icon=self.app.icon("quit", 26))
        self.label(pane, "Klipper pin assignments (from printer.cfg, read-only)", 11, "bold",
                   bg=self.t["panel"]).pack(anchor="w", padx=pad, pady=(self.px(10), 0))
        self.pin_count = self.label(pane, "", 10, color=self.t["subtext"], bg=self.t["panel"])
        self.pin_count.pack(anchor="w", padx=pad)
        self.pin_list = ScrollList(pane, self.app, visible_rows=3, row_h=32, bg=self.t["panel"])
        self.pin_list.pack(fill="both", expand=True, padx=pad, pady=(self.px(4), pad))
        return pane

    def _refresh_pins(self, pins):
        key = tuple(pins)
        if key == self._pin_key:
            return
        self._pin_key = key
        self.pin_list.clear()
        if not pins:
            self.pin_count.configure(text="No pin settings found in the config folder.")
            return
        self.pin_count.configure(text=f"{len(pins)} pin settings")
        for section, pin_key, value in pins:
            self.pin_list.add(f"{section}  \u00b7  {pin_key} = {value}", None, "ghost")

    # ---- refresh -----------------------------------------------------------
    def refresh(self, st, online, demo):
        s = self.app.settings
        det = self.app.backend.detection
        self.theme_btn.set_text(f"{self.app.theme.name}  \u25bc")
        self.pointer_sw.set_on(bool(s.get("mouse_pointer")))
        self.mmu_sw.set_on(bool(s.get("mmu_enabled")))
        self.warning.configure(text=self.app.mmu_block_message())
        self.mmu_info.configure(text=f"Detected: {det.get('mmu_name', 'None detected')}")
        self.quit_sw.set_on(bool(s.get("allow_quit")))
        if s.get("allow_quit") and not self._quit_shown:
            self.quit_btn.pack(fill="x", pady=(self.px(6), 0))
            self._quit_shown = True
        elif not s.get("allow_quit") and self._quit_shown:
            self.quit_btn.pack_forget()
            self._quit_shown = False
        self._refresh_macros(det.get("macros") or [])
        self._refresh_pins(det.get("pins") or [])

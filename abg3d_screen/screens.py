"""Tab pages. Each page is a Frame that is rebuilt whenever the theme changes."""
import tkinter as tk


from .detect import MMU_NAMES
from .monitor import MonitorView
from .page import Page
from .mmu import is_active, load_mmu_commands
from .widgets import RoundButton, Switch, round_rect
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
    """Theme dropdown and toggles on the left; the Quit button on the right when allowed."""

    def build(self):
        pad = self.px(12)
        self.printers = load_printers()
        self._exit_shown = False
        self.dropdown = None
        self._scroll = None
        right = tk.Frame(self, bg=self.t["bg"], width=self.px(170))
        right.pack(side="right", fill="y", padx=(0, pad), pady=pad)
        right.pack_propagate(False)
        left = self.panel(self)
        left.pack(side="left", fill="both", expand=True, padx=pad, pady=pad)

        self.label(left, "Themes", 12, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, self.px(4)))
        self.theme_btn = self.button(left, "", self._toggle_dropdown, "secondary", height=40,
                                     font=11)
        self.theme_btn.pack(fill="x", padx=pad)

        self.pointer_sw = Switch(left, "Mouse pointer", self.app.toggle_pointer, self.app,
                                 on=bool(self.app.settings.get("mouse_pointer")), height=40)
        self.pointer_sw.pack(fill="x", padx=pad, pady=(self.px(12), 0))
        self.mmu_sw = Switch(left, "Enable MMU", self.app.toggle_mmu, self.app,
                             on=bool(self.app.settings.get("mmu_enabled")), height=40)
        self.mmu_sw.pack(fill="x", padx=pad, pady=(self.px(8), 0))
        self.quit_sw = Switch(left, "Allow to quit", self.app.toggle_quit, self.app,
                              on=bool(self.app.settings.get("allow_quit")), height=40)
        self.quit_sw.pack(fill="x", padx=pad, pady=(self.px(8), 0))
        self.warning = tk.Label(left, text="", fg=self.t["danger"], bg=self.t["panel"],
                                font=self.font(10, "bold"), wraplength=self.px(430), justify="left")
        self.warning.pack(anchor="w", padx=pad, pady=(self.px(8), 0))
        self.info = self.label(left, "", 9, color=self.t["subtext"], bg=self.t["panel"],
                               wraplength=self.px(430), justify="left")
        self.info.pack(anchor="w", padx=pad, pady=(self.px(6), 0))

        self.exit_btn = self.button(right, "Quit", self.app.quit, "ghost", confirm=True,
                                    height=84, font=12, icon=self.app.icon("quit", 30))

    # ---- theme dropdown with scrollbar ------------------------------------
    ITEM_H = 34    # base px per theme button
    PAD = 3        # base px gap between items
    VISIBLE = 3    # items visible at once

    def _toggle_dropdown(self):
        if self.dropdown is not None:
            self._close_dropdown()
            return
        btn = self.theme_btn
        row = self.px(self.ITEM_H) + 2 * self.px(self.PAD)
        clip_h = row * self.VISIBLE
        themes = list(self.app.themes.items())
        self.dropdown = tk.Frame(btn.master, bg=self.t["panel_alt"])
        self.dropdown.place(x=btn.winfo_x(), y=btn.winfo_y() + btn.winfo_height() + self.px(4),
                            width=btn.winfo_width())
        self.dropdown.lift()

        column = tk.Frame(self.dropdown, bg=self.t["panel_alt"], width=self.px(44))
        column.pack(side="right", fill="y")
        column.pack_propagate(False)
        clip = tk.Frame(self.dropdown, bg=self.t["panel_alt"], height=clip_h)
        clip.pack(side="left", fill="both", expand=True)
        clip.pack_propagate(False)

        inner = tk.Frame(clip, bg=self.t["panel_alt"])
        inner.place(x=0, y=0, relwidth=1)
        for key, theme in themes:
            style = "primary" if key == self.app.theme.key else "secondary"
            RoundButton(inner, theme.name, lambda k=key: self._choose(k), self.app, style,
                        height=self.ITEM_H, font=10).pack(fill="x", padx=self.px(4),
                                                          pady=self.px(self.PAD))
        total = len(themes) * row
        self._scroll = {"inner": inner, "offset": 0, "step": row, "clip_h": clip_h,
                        "max": max(0, total - clip_h), "track": None}

        RoundButton(column, "▲", lambda: self._scroll_by(-1), self.app, "secondary",
                    height=self.ITEM_H, font=10).pack(fill="x", padx=2, pady=(2, 0))
        track = tk.Canvas(column, bg=self.t["panel_alt"], highlightthickness=0, bd=0)
        track.pack(fill="both", expand=True, padx=12, pady=4)
        RoundButton(column, "▼", lambda: self._scroll_by(1), self.app, "secondary",
                    height=self.ITEM_H, font=10).pack(fill="x", padx=2, pady=(0, 2))
        self._scroll["track"] = track
        track.bind("<Configure>", lambda _e: self._draw_thumb())
        self._place_inner()

    def _scroll_by(self, direction):
        if self._scroll is None:
            return
        sc = self._scroll
        sc["offset"] = max(0, min(sc["max"], sc["offset"] + direction * sc["step"]))
        self._place_inner()
        self._draw_thumb()

    def _place_inner(self):
        sc = self._scroll
        if sc is not None:
            sc["inner"].place(x=0, y=-sc["offset"], relwidth=1)

    def _draw_thumb(self):
        sc = self._scroll
        if sc is None or sc["track"] is None:
            return
        c = sc["track"]
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if h <= 4 or w <= 4:
            return
        total = sc["max"] + sc["clip_h"]
        thumb_h = max(12, int(h * sc["clip_h"] / total))
        y = int((h - thumb_h) * (sc["offset"] / sc["max"])) if sc["max"] else 0
        round_rect(c, 2, y, w - 2, y + thumb_h, 6, fill=self.t["accent"], outline="")

    def _choose(self, key):
        self._close_dropdown()
        self.app.root.after_idle(lambda: self.app.apply_theme(key))

    def _close_dropdown(self):
        if self.dropdown is not None:
            self.dropdown.destroy()
            self.dropdown = None
        self._scroll = None

    # ---- refresh --------------------------------------------------------
    def refresh(self, st, online, demo):
        s = self.app.settings
        self.theme_btn.set_text(f"{self.app.theme.name}  ▼")
        self.pointer_sw.set_on(bool(s.get("mouse_pointer")))
        self.mmu_sw.set_on(bool(s.get("mmu_enabled")))
        self.quit_sw.set_on(bool(s.get("allow_quit")))
        self.warning.configure(text=self.app.mmu_block_message())
        if s.get("allow_quit") and not self._exit_shown:
            self.exit_btn.pack(fill="x", pady=(0, self.px(6)))
            self._exit_shown = True
        elif not s.get("allow_quit") and self._exit_shown:
            self.exit_btn.pack_forget()
            self._exit_shown = False
        family = s.get("printer_family")
        name = self.printers.get(family, {}).get("name", "not set") if family else "not set"
        model = s.get("printer_model") or ""
        self.info.configure(text=f"Printer: {name} {model}   ·   Moonraker: {s.get('moonraker_url')}")

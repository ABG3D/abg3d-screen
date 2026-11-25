"""Tab pages. Each page is a Frame that is rebuilt whenever the theme changes."""
import base64
import math
import tkinter as tk


from .detect import MMU_NAMES
from .monitor import MonitorView
from .page import Page, fmt_time
from .mmu import is_active, load_mmu_commands
from .widgets import ScrollList, Switch, drag_moved, round_rect
from . import network
from .keyboard import OnScreenKeyboard

JOG_FEED_XY, JOG_FEED_Z = 3000, 600
SCREEN_TIMEOUTS = [(0, "Never"), (60, "1 min"), (300, "5 min"), (900, "15 min"), (1800, "30 min")]
STEP_DELTAS = [-10, -1, 1, 10]
HEATER_SPECS = {
    "extruder": {"name": "Hotend", "max": 350, "presets": [("PLA", 210), ("PETG", 240), ("ABS", 250)],
                 "gcode": "M104 S{v}"},
    "heater_bed": {"name": "Bed", "max": 130, "presets": [("PLA", 60), ("PETG", 80), ("ABS", 100)],
                   "gcode": "M140 S{v}"},
}
CHAMBER_SPEC = {"name": "Chamber", "max": 100, "presets": [("40", 40), ("50", 50), ("60", 60)],
                "gcode": "SET_HEATER_TEMPERATURE HEATER={heater} TARGET={v}"}
PRINT_ACTIVE = ("printing", "paused")


class HomePage(Page):
    """Home: live temperature monitor on the left, print preview on the right."""

    PREVIEW_W, PREVIEW_H = 206, 150

    def build(self):
        pad = self.px(12)
        right = self.panel(self)
        right.configure(width=self.px(230))
        right.pack(side="right", fill="y", padx=(pad // 2, pad), pady=pad)
        right.pack_propagate(False)
        self.monitor = MonitorView(self, self.app)
        self.monitor.pack(side="left", fill="both", expand=True, padx=(pad, pad // 2), pady=pad)

        self.preview = tk.Canvas(right, width=self.px(self.PREVIEW_W),
                                 height=self.px(self.PREVIEW_H), bg=self.t["panel_alt"],
                                 highlightthickness=0, bd=0)
        self.preview.pack(padx=pad, pady=(pad, self.px(8)))
        self.file_lbl = self.label(right, "No file loaded", 11, "bold", bg=self.t["panel"],
                                   wraplength=self.px(206), justify="left")
        self.file_lbl.pack(anchor="w", padx=pad)
        self.status_lbl = self.label(right, "Idle", 10, color=self.t["subtext"],
                                     bg=self.t["panel"], wraplength=self.px(206), justify="left")
        self.status_lbl.pack(anchor="w", padx=pad, pady=(self.px(4), 0))
        self.progress = self.meter(right, height=10)
        self.progress.pack(fill="x", padx=pad, pady=self.px(8))
        self.time_lbl = self.label(right, "", 10, color=self.t["subtext"], bg=self.t["panel"])
        self.time_lbl.pack(anchor="w", padx=pad)
        self._name = None
        self._cache = {}
        self._draw_preview(None)

    def _draw_preview(self, image):
        c = self.preview
        c.delete("all")
        w, h = self.px(self.PREVIEW_W), self.px(self.PREVIEW_H)
        if image is not None:
            c.create_image(w // 2, h // 2, image=image)
            return
        round_rect(c, 2, 2, w - 2, h - 2, self.px(12), fill=self.t["panel_alt"],
                   outline=self.t["border"])
        c.create_text(w // 2, h // 2 - self.px(8), text="Print preview", fill=self.t["text"],
                      font=self.font(12, "bold"))
        c.create_text(w // 2, h // 2 + self.px(14), text="no thumbnail",
                      fill=self.t["subtext"], font=self.font(10))

    def _show_file(self, name, online):
        if not name:
            self._draw_preview(None)
            return
        if name in self._cache:
            self._draw_preview(self._cache[name])
            return
        self._draw_preview(None)
        if online:
            self.app.run_async(lambda: self.app.backend.thumbnail_bytes(name), None,
                               on_done=lambda data: self._thumb_ready(name, data))

    def _thumb_ready(self, name, data):
        if name != self._name or not data:
            return
        try:
            img = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
        except tk.TclError:
            return  # format Tk cannot read: keep the placeholder
        factor = max(1, math.ceil(img.width() / self.px(self.PREVIEW_W)),
                     math.ceil(img.height() / self.px(self.PREVIEW_H)))
        img = img.subsample(factor) if factor > 1 else img
        self._cache[name] = img
        self._draw_preview(img)

    def refresh(self, st, online, demo):
        ps = st.get("print_stats") or {}
        state = ps.get("state") or "standby"
        name = ps.get("filename") or ""
        prog = float((st.get("display_status") or {}).get("progress") or 0)
        dur = float(ps.get("print_duration") or 0)
        self.monitor.refresh(st)
        if name != self._name:
            self._name = name
            self._show_file(name, online)
        self.file_lbl.configure(text=name or "No file loaded")
        if state in PRINT_ACTIVE:
            self.status_lbl.configure(text=f"{state.capitalize()}  \u00b7  {prog * 100:.0f}%")
            self.time_lbl.configure(text=f"Elapsed {fmt_time(dur)}")
            self.progress.set(prog)
        else:
            self.status_lbl.configure(text="Demo mode" if demo else state.capitalize())
            self.time_lbl.configure(text="")
            self.progress.set(1.0 if state == "complete" else 0.0)


class ControlPage(Page):
    """Control sub-tabs: Movement, Fan Control and LED Control."""

    STEPS = [0.1, 1.0, 10.0]
    TABS = [("temperature", "Temperature", "temps"), ("movement", "Movement", "move"),
            ("fan", "Fan Control", "fan"), ("led", "LED Control", "led")]
    FAN_STEPS = [("Off", 0), ("25%", 64), ("50%", 128), ("75%", 191), ("100%", 255)]
    BEDFAN_STEPS = [("Off", "0.0"), ("20%", "0.2"), ("50%", "0.5"), ("80%", "0.8"), ("100%", "1.0")]
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
        self._cards = {}
        self._targets = {}
        self._active_key = None
        self._chamber_obj = ""
        self._off_row = None
        self._temp_box = None

        bar = self.hexbg(self)
        bar.pack(side="top", fill="x", padx=pad, pady=(pad, 0))
        self.tab_btns = {}
        for i, (key, text, icon) in enumerate(self.TABS):
            btn = self.button(bar, text, lambda k=key: self._set_tab(k), "secondary", height=64,
                              font=12, icon=self.app.icon(icon, 26))
            btn.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else self.px(6), 0))
            self.tab_btns[key] = btn

        self.panes = {"temperature": self._build_temperature(), "movement": self._build_movement(),
                      "fan": self._build_fan(), "led": self._build_led()}
        self._set_tab("temperature")

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
        pane = ScrollList(self, self.app, visible_rows=None, row_h=36, bg=self.t["panel"])
        box = pane.inner
        homing = tk.Frame(box, bg=self.t["panel"])
        homing.pack(fill="x", padx=pad, pady=(pad, 0))
        h = self.px(66)
        self.button(homing, "", lambda: self.gcode("M18", "Motors released"), height=h,
                    icon=self.app.icon("motor_off", 30)).pack(side="left", fill="x", expand=True, padx=3)
        for name, cmd, icon in (("Home All", "G28", "home_all"), ("X", "G28 X", "home_x"),
                                ("Y", "G28 Y", "home_y"), ("Z", "G28 Z", "home_z"),
                                ("Home XY", "G28 X Y", "home_xy")):
            self.button(homing, "", lambda c=cmd, n=name: self.gcode(c, f"Homing {n}"), height=h,
                        icon=self.app.icon(icon, 30)).pack(side="left", fill="x", expand=True, padx=3)

        grid = tk.Frame(box, bg=self.t["panel"])
        grid.pack(pady=self.px(6))

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

        steps = tk.Frame(box, bg=self.t["panel"])
        steps.pack(fill="x", padx=pad, pady=(0, self.px(6)))
        for val in self.STEPS:
            btn = self.button(steps, f"{val:g} mm", lambda v=val: self._set_step(v),
                              "primary" if val == self.step else "secondary", height=38)
            btn.pack(side="left", fill="x", expand=True, padx=3)
            self.step_buttons[val] = btn

        self.extras = tk.Frame(box, bg=self.t["panel"])
        self.extras.pack(fill="x", padx=pad, pady=(0, self.px(4)))
        self.label(box, "Jogging is locked while a print is running.", 10,
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
        row.pack(fill="x", padx=pad, pady=(self.px(4), 0))
        for name, value in self.FAN_STEPS:
            self.button(row, name, lambda v=value, n=name: self.gcode(f"M106 S{v}", f"Part fan {n}"),
                        height=80, font=13).pack(side="left", fill="x", expand=True, padx=3)
        self.bedfan_box = tk.Frame(pane, bg=self.t["panel"])
        self.label(self.bedfan_box, "Bed fans", 14, "bold", bg=self.t["panel"]).pack(anchor="w")
        bed = tk.Frame(self.bedfan_box, bg=self.t["panel"])
        bed.pack(fill="x", pady=(self.px(4), 0))
        for name, value in self.BEDFAN_STEPS:
            self.button(bed, name,
                        lambda v=value, n=name: self.gcode(f"SET_FAN_SPEED FAN=bedfans SPEED={v}",
                                                           f"Bed fans {n}"),
                        height=70, font=13).pack(side="left", fill="x", expand=True, padx=3)
        self._bedfan_shown = False
        return pane

    def _build_led(self):
        pad = self.px(12)
        pane = self.panel(self)
        self.label(pane, "LED colour", 14, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, 0))
        self.case_sw = Switch(pane, "Case light", self._toggle_case, self.app, on=False,
                              height=44)
        self.led_box = tk.Frame(pane, bg=self.t["panel"])
        self.led_box.pack(fill="both", expand=True, padx=pad, pady=pad)
        self._case_shown = False
        return pane

    def _toggle_case(self):
        on = self.case_sw.on
        self.gcode(f"SET_PIN PIN=caselight VALUE={'1.00' if on else '0.00'}",
                   f"Case light {'on' if on else 'off'}")

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
    # ---- Temperature --------------------------------------------------------
    def _build_temperature(self):
        pad = self.px(12)
        pane = ScrollList(self, self.app, visible_rows=None, row_h=36, bg=self.t["panel"])
        self._temp_box = pane.inner
        self.label(self._temp_box, "Target temperatures", 14, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(pad, self.px(4)))
        for key, spec in HEATER_SPECS.items():
            self._add_card(key, spec, key, None)
        self._off_row = tk.Frame(self._temp_box, bg=self.t["panel"])
        self._off_row.pack(fill="x", padx=pad, pady=(self.px(4), pad))
        self.button(self._off_row, "All heaters off", self._all_off, "secondary", height=44,
                    font=12, icon=self.app.icon("temps", 24)).pack(fill="x")
        self.temp_kb = OnScreenKeyboard(self._temp_box, self.app, on_key=self._kb_key,
                                        on_delete=self._kb_delete, on_move=self._kb_move,
                                        on_send=self._kb_apply, on_hide=self._kb_hide, numeric=True)
        return pane

    def _add_card(self, key, spec, status_key, heater, before=None):
        pad = self.px(10)
        panel_alt = self.t["panel_alt"]
        card = tk.Frame(self._temp_box, bg=panel_alt)
        top = tk.Frame(card, bg=panel_alt)
        top.pack(fill="x", padx=pad, pady=(pad, 0))
        self.label(top, spec["name"], 12, "bold", bg=panel_alt).pack(side="left")
        live = self.label(top, "--", 12, color=self.t["subtext"], bg=panel_alt)
        live.pack(side="right")
        presets = tk.Frame(card, bg=panel_alt)
        presets.pack(fill="x", padx=pad, pady=(self.px(8), 0))
        self.button(presets, "Off", lambda: self._send(key, 0), "secondary", height=40,
                    font=11).pack(side="left", fill="x", expand=True, padx=2)
        for name, value in spec["presets"]:
            self.button(presets, name, lambda v=value: self._send(key, v), "secondary", height=40,
                        font=11).pack(side="left", fill="x", expand=True, padx=2)
        steps = tk.Frame(card, bg=panel_alt)
        steps.pack(fill="x", padx=pad, pady=(self.px(6), 0))
        for delta in STEP_DELTAS:
            self.button(steps, f"{delta:+d}", lambda d=delta: self._step(key, d), "secondary",
                        height=40, font=11).pack(side="left", fill="x", expand=True, padx=2)
        entry_row = tk.Frame(card, bg=panel_alt)
        entry_row.pack(fill="x", padx=pad, pady=(self.px(6), pad))
        entry = tk.Entry(entry_row, font=("DejaVu Sans", self.font(16)[1], "bold"), width=6,
                         justify="center", bg=self.t["panel"], fg=self.t["text"],
                         insertbackground=self.t["text"], relief="flat", bd=6)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<ButtonRelease-1>", lambda _e, k=key: self._focus(k))
        self.button(entry_row, "Set", lambda: self._apply(key), "primary", height=44,
                    font=11).pack(side="left", padx=(self.px(6), 0))
        if before is not None:
            card.pack(fill="x", pady=(0, self.px(10)), before=before)
        else:
            card.pack(fill="x", pady=(0, self.px(10)))
        self._cards[key] = {"frame": card, "live": live, "entry": entry, "spec": spec,
                            "status_key": status_key, "heater": heater}

    def _send(self, key, value):
        card = self._cards.get(key)
        if not card:
            return
        spec = card["spec"]
        v = max(0, min(spec["max"], int(round(float(value)))))
        script = spec["gcode"].format(v=v, heater=card["heater"] or "")
        self.gcode(script, f"{spec['name']} target {v} \u00b0C")

    def _step(self, key, delta):
        self._send(key, self._targets.get(key, 0) + delta)

    def _apply(self, key):
        card = self._cards.get(key)
        if not card:
            return
        try:
            self._send(key, int(card["entry"].get() or 0))
        except ValueError:
            pass

    def _all_off(self):
        lines = [c["spec"]["gcode"].format(v=0, heater=c["heater"] or "")
                 for c in self._cards.values()]
        self.gcode("\n".join(lines), "Heaters off")

    def _focus(self, key):
        if drag_moved():
            return
        self._active_key = key
        if not self.temp_kb.winfo_ismapped():
            self.temp_kb.pack(fill="x", padx=self.px(12), pady=(self.px(8), self.px(12)))

    def _kb_entry(self):
        card = self._cards.get(self._active_key) if self._active_key else None
        return card["entry"] if card else None

    def _kb_key(self, ch):
        entry = self._kb_entry()
        if entry is not None and ch.isdigit():
            entry.insert(tk.INSERT, ch)

    def _kb_delete(self):
        entry = self._kb_entry()
        if entry is not None:
            pos = entry.index(tk.INSERT)
            if pos > 0:
                entry.delete(pos - 1)

    def _kb_move(self, delta):
        entry = self._kb_entry()
        if entry is not None:
            pos = entry.index(tk.INSERT)
            entry.icursor(max(0, min(len(entry.get()), pos + delta)))

    def _kb_apply(self):
        key = self._active_key
        self._kb_hide()
        if key:
            self._apply(key)

    def _kb_hide(self):
        self.temp_kb.pack_forget()
        self._active_key = None

    def _refresh_temps(self, st, det):
        chamber = det.get("chamber_heater") or ""
        if chamber != self._chamber_obj:
            old = self._cards.pop("chamber", None)
            if old:
                old["frame"].destroy()
            self._targets.pop("chamber", None)
            self._chamber_obj = chamber
            if chamber:
                self._add_card("chamber", CHAMBER_SPEC, chamber, chamber.split(" ", 1)[1],
                               before=self._off_row)
        for key, card in self._cards.items():
            data = st.get(card["status_key"]) or {}
            cur, tgt = data.get("temperature"), data.get("target")
            if tgt is not None:
                self._targets[key] = float(tgt)
            card["live"].configure(
                text="--" if cur is None else f"{float(cur):.0f}\u00b0 / {float(tgt or 0):.0f}\u00b0")
            if key != self._active_key and tgt is not None:
                card["entry"].delete(0, "end")
                card["entry"].insert(0, f"{float(tgt):.0f}")

    # ---- lifecycle --------------------------------------------------------
    def refresh(self, st, online, demo):
        pad = self.px(12)
        state = (st.get("print_stats") or {}).get("state") or "standby"
        locked = state in PRINT_ACTIVE
        det = self.app.backend.detection
        self._refresh_temps(st, det)
        key = (bool(det.get("ztilt")), bool(det.get("qgl")))
        if key != self._extras_key:
            self._build_extras(key)
        leds = tuple(det.get("leds") or [])
        if leds != self._leds_key:
            self._leds_key = leds
            self._build_leds(list(leds))
        s = self.app.settings
        bed_on = bool(s.get("pin_bedfans"))
        if bed_on != self._bedfan_shown:
            if bed_on:
                self.bedfan_box.pack(fill="x", padx=pad, pady=(self.px(12), pad))
            else:
                self.bedfan_box.pack_forget()
            self._bedfan_shown = bed_on
        case_on = bool(s.get("pin_caselight"))
        if case_on != self._case_shown:
            if case_on:
                self.case_sw.pack(fill="x", padx=pad, pady=(0, self.px(8)), before=self.led_box)
            else:
                self.case_sw.pack_forget()
            self._case_shown = case_on
        for btn in self.jog_buttons + self.extra_buttons:
            btn.set_enabled(not locked)


class MMUPage(Page):
    """Shows controls for the detected MMU only. Nothing is sent when no MMU is active."""

    def build(self):
        self.key = None
        self.body = self.hexbg(self)
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
        actions = self.hexbg(self, width=self.px(230))
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
        self.sub = None
        self.dropdown = None
        self._macro_key = None
        self._pin_key = None
        self._quit_shown = False
        self._pending = None

        bar = self.hexbg(self)
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
        self.pointer_sw.pack(fill="x", padx=pad, pady=(self.px(14), self.px(8)))
        self.label(pane, "Display", 12, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(self.px(6), self.px(4)))
        trow = tk.Frame(pane, bg=self.t["panel"])
        trow.pack(fill="x", padx=pad)
        self.timeout_btns = {}
        for seconds, text in SCREEN_TIMEOUTS:
            btn = self.button(trow, text, lambda s=seconds: self.app.set_screen_timeout(s),
                              "secondary", height=40, font=10)
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.timeout_btns[seconds] = btn
        self.button(pane, "Screen Off", self.app.screen_off, "secondary", height=44).pack(
            fill="x", padx=pad, pady=(self.px(8), pad))
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
        self.label(pane, "Pin configs", 11, "bold", bg=self.t["panel"]).pack(
            anchor="w", padx=pad, pady=(self.px(10), 0))
        self.label(pane, "Enable optional outputs. Their controls appear on the Control tab.", 10,
                   color=self.t["subtext"], bg=self.t["panel"]).pack(anchor="w", padx=pad)
        self.bedfan_sw = Switch(pane, "Bed fans", lambda: self.app.toggle_setting("pin_bedfans"),
                                self.app, on=bool(self.app.settings.get("pin_bedfans")), height=44)
        self.bedfan_sw.pack(fill="x", padx=pad, pady=(self.px(6), 0))
        self.case_pin_sw = Switch(pane, "Case light",
                                  lambda: self.app.toggle_setting("pin_caselight"), self.app,
                                  on=bool(self.app.settings.get("pin_caselight")), height=44)
        self.case_pin_sw.pack(fill="x", padx=pad, pady=(self.px(8), pad))
        return pane

    # ---- refresh -----------------------------------------------------------
    def refresh(self, st, online, demo):
        s = self.app.settings
        det = self.app.backend.detection
        self.theme_btn.set_text(f"{self.app.theme.name}  \u25bc")
        self.pointer_sw.set_on(bool(s.get("mouse_pointer")))
        current = int(s.get("screen_timeout") or 0)
        for seconds, btn in self.timeout_btns.items():
            btn.set_style("primary" if seconds == current else "secondary")
        self.mmu_sw.set_on(bool(s.get("mmu_enabled")))
        self.warning.configure(text=self.app.mmu_block_message())
        self.mmu_info.configure(text=f"Detected: {det.get('mmu_name', 'None detected')}")
        self.quit_sw.set_on(bool(s.get("allow_quit")))
        self.bedfan_sw.set_on(bool(s.get("pin_bedfans")))
        self.case_pin_sw.set_on(bool(s.get("pin_caselight")))
        if s.get("allow_quit") and not self._quit_shown:
            self.quit_btn.pack(fill="x", pady=(self.px(6), 0))
            self._quit_shown = True
        elif not s.get("allow_quit") and self._quit_shown:
            self.quit_btn.pack_forget()
            self._quit_shown = False
        self._refresh_macros(det.get("macros") or [])

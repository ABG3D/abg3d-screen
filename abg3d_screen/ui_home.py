"""Home: Cairo temperature graph, toggleable sensor list, active/last print with thumbnail, quick actions."""
import os

from gi.repository import GLib, Gtk

from .core import Panel
from .widgets import (GRAPH_COLORS, ActiveBar, HBox, IconBtn, Keypad, Lbl, Scroller, TempGraph, VBox,
                      add_cls, display_name, fmt_len, fmt_time, set_btn, set_cls, set_temp_cmd)

STATE_TEXT = {"standby": "Ready", "printing": "Printing", "paused": "Paused",
              "complete": "Complete", "cancelled": "Cancelled", "error": "Error"}


class HomePanel(Panel):
    title = "Home"

    def __init__(self, app):
        super().__init__(app)
        ui = app.ui
        self.rows = {}
        self.cur_file = None
        self.meta = {}
        self.last_job = None
        self.heater_set = set()
        lbl = ui.nav_labels

        self.graph = TempGraph(app)
        self.graph.set_vexpand(True)
        gcard = VBox(self.graph, spacing=0, expand=(0,))
        add_cls(gcard, "card")
        self.sensor_box = VBox(spacing=max(2, ui.sp // 2))
        sensors = Scroller(self.sensor_box)
        # graph and sensor list share the column height (expand + fill), no fixed pixel heights
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=ui.sp)
        left.set_homogeneous(True)
        left.pack_start(gcard, True, True, 0)
        left.pack_start(sensors, True, True, 0)

        # print status card
        self.tsize = ui.thumb_home
        self.thumb = Gtk.Image()
        add_cls(self.thumb, "thumb")
        self.thumb.set_size_request(self.tsize, self.tsize)
        self.thumb.set_no_show_all(not self.tsize)
        self.fname = Lbl("No active print", "title", ellipsize=True)
        self.state_lbl = Lbl("Ready", "muted", "small", ellipsize=True)
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.times = Lbl("", "small", wrap=True)
        self.pause_btn = IconBtn("pause", "Pause" if lbl else None, self._pause_resume, "primary")
        self.cancel_btn = IconBtn("cancel", "Cancel" if lbl else None, self._cancel, "danger")
        pc = VBox(self.thumb, self.fname, self.state_lbl, self.progress, self.times,
                  HBox(self.pause_btn, self.cancel_btn, homogeneous=True))
        add_cls(pc, "card")
        actions = HBox(IconBtn("home_all", "Home All" if lbl else None, lambda: self.mr.gcode("G28")),
                       IconBtn("cooldown", "Cool Down" if lbl else None, app.cooldown),
                       IconBtn("estop", "E-Stop" if lbl else None, app.estop, "danger"),
                       homogeneous=True)
        right = VBox(pc, actions, expand=(0,))
        content_w = ui.w - (ui.nav_size if ui.nav_left else 0) - 2 * ui.pad
        right = Scroller(right)
        right.set_size_request(int(content_w * (0.48 if ui.small else 0.37)), -1)

        self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ui.sp)
        self.widget.pack_start(left, True, True, 0)
        self.widget.pack_start(right, False, True, 0)
        add_cls(self.widget, "panel")
        GLib.timeout_add_seconds(1, self._tick)

    # ------------------------------------------------------------- build
    def on_ready(self):
        for c in self.sensor_box.get_children():
            self.sensor_box.remove(c)
            c.destroy()
        self.rows = {}
        hist = self.app.history
        self.heater_set = set(self.mr.heaters() + self.mr.temp_fans())
        hidden = set(self.app.settings.get("graph_hidden", []))
        for obj in hist.order:
            idx = hist.color_index(obj)
            bar = ActiveBar(GRAPH_COLORS[idx % len(GRAPH_COLORS)])
            bar.set_active(obj not in hidden)
            name = Lbl(display_name(obj), ellipsize=True)
            temp = Lbl("--", "sensor-temp", xalign=1.0)
            toggle = Gtk.Button()
            toggle.set_can_focus(False)
            add_cls(toggle, "flat-row")
            toggle.add(HBox(bar, name, temp, expand=(1,)))
            toggle.connect("clicked", lambda _b, o=obj: self._toggle(o))
            kids = [toggle]
            tgt = None
            if obj in self.heater_set:
                tgt = Gtk.Button(label="/ --")
                tgt.set_can_focus(False)
                tgt.connect("clicked", lambda _b, o=obj: self._set_target(o))
                kids.append(tgt)
            row = HBox(*kids, expand=(0,))
            add_cls(row, "row", "sensor-row")
            set_cls(row, "off", obj in hidden)
            self.sensor_box.pack_start(row, False, False, 0)
            self.rows[obj] = (row, bar, temp, tgt)
        self.sensor_box.show_all()
        self.last_job = None
        self._load_last_job()

    def _toggle(self, obj):
        hidden = set(self.app.settings.get("graph_hidden", []))
        hidden ^= {obj}
        self.app.settings["graph_hidden"] = sorted(hidden)
        self.app.save_settings()
        row, bar, _t, _g = self.rows[obj]
        bar.set_active(obj not in hidden)
        set_cls(row, "off", obj in hidden)
        self.graph.queue_draw()

    def _set_target(self, obj):
        Keypad(self.app, "%s °C" % display_name(obj), self.mr.state(obj, "target", 0),
               lambda v: self.mr.gcode(set_temp_cmd(obj, v)), decimals=False, maxval=400)

    # ------------------------------------------------------------ updates
    def _tick(self):
        if self.visible():
            self.graph.queue_draw()
            if self.mr.is_printing():
                self._update_print()
        return True

    def refresh(self):
        self._update_temps(None)
        self._update_print()
        self.graph.queue_draw()

    def on_status(self, ch):
        if any(o in ch for o in self.rows):
            self._update_temps(ch)
        if "print_stats" in ch or "display_status" in ch or "virtual_sdcard" in ch:
            self._update_print()

    def _update_temps(self, ch):
        for obj, (_row, _bar, temp, tgt) in self.rows.items():
            if ch is not None and obj not in ch:
                continue
            st = self.mr.data.get(obj, {})
            t = st.get("temperature")
            if t is None:
                continue
            temp.set_text("%.1f°" % t)
            if tgt is not None:
                target = st.get("target") or 0
                tgt.set_label("/ %.0f°" % target)
                set_cls(tgt, "warn", target > 0)

    def _load_last_job(self):
        self.mr.call("server.history.list", {"limit": 1, "order": "desc"}, self._on_history)

    def _on_history(self, res, err):
        jobs = (res or {}).get("jobs") or []
        if jobs and not err:
            self.last_job = jobs[0]
            if not self.mr.state("print_stats", "filename"):
                self._update_print()

    def _update_print(self):
        mr = self.mr
        ps = mr.data.get("print_stats", {})
        state = ps.get("state", "standby")
        fn = ps.get("filename") or ""
        last = False
        if not fn and self.last_job:
            fn, last = self.last_job.get("filename", ""), True
        if fn != self.cur_file:
            self.cur_file = fn
            self.meta = {}
            self.thumb.clear()
            if fn:
                if last and isinstance(self.last_job.get("metadata"), dict) and \
                        self.last_job["metadata"].get("thumbnails"):
                    self._on_meta(fn, self.last_job["metadata"], None)
                else:
                    mr.call("server.files.metadata", {"filename": fn},
                            lambda r, e, f=fn: self._on_meta(f, r, e))
        name = os.path.basename(fn) if fn else "No active print"
        self.fname.set_text(("Last: " + name) if last else name)
        txt = STATE_TEXT.get(state, state.title())
        if last:
            txt = "Last job: %s" % self.last_job.get("status", "").replace("_", " ")
        if state == "error" and ps.get("message"):
            txt += ": " + ps["message"]
        msg = mr.state("display_status", "message")
        if msg and state in ("printing", "paused"):
            txt += " — " + msg
        self.state_lbl.set_text(txt)
        progress = mr.state("display_status", "progress", 0.0) or mr.state("virtual_sdcard", "progress", 0.0)
        if state == "complete" or (last and self.last_job.get("status") == "completed"):
            progress = 1.0
        elif last:
            progress = 0.0
        self.progress.set_fraction(max(0.0, min(1.0, progress)))
        self.progress.set_text("%d%%" % round(progress * 100))
        dur = ps.get("print_duration", 0) or 0
        total = ps.get("total_duration", 0) or 0
        est = self.meta.get("estimated_time")
        remaining = None
        active = state in ("printing", "paused")
        if active:
            if est and dur:
                remaining = max(0, est - dur)
            elif progress > 0.02:
                remaining = dur / progress - dur
        parts = []
        if active or (fn and not last):
            parts.append("Elapsed %s" % fmt_time(total))
        if remaining is not None:
            parts.append("Left %s" % fmt_time(remaining))
        if last and self.last_job.get("total_duration"):
            parts.append("Took %s" % fmt_time(self.last_job["total_duration"]))
        if ps.get("filament_used") and not last:
            parts.append(fmt_len(ps["filament_used"]))
        info = ps.get("info") or {}
        if info.get("current_layer") is not None and info.get("total_layer"):
            parts.append("L %s/%s" % (info["current_layer"], info["total_layer"]))
        self.times.set_text("  •  ".join(parts))
        set_btn(self.pause_btn, "resume" if state == "paused" else "pause",
                "Resume" if state == "paused" else "Pause")
        if state in ("complete", "cancelled", "error") and (not self.last_job or
                                                            self.last_job.get("filename") != fn):
            self._load_last_job()

    def _on_meta(self, fn, res, err):
        if fn != self.cur_file or err or not res:
            return
        self.meta = res
        if self.tsize:
            self.app.thumbs.load(fn, res.get("thumbnails"), self.tsize,
                                 lambda pb: pb and fn == self.cur_file and self.thumb.set_from_pixbuf(pb))

    # ------------------------------------------------------------ actions
    def _pause_resume(self):
        if self.mr.print_state() == "paused":
            self.mr.call("printer.print.resume")
        else:
            self.mr.call("printer.print.pause")

    def _cancel(self):
        self.app.confirm("Cancel the current print?", lambda: self.mr.call("printer.print.cancel"),
                         ok="Cancel Print", danger=True)


"""Console: live G-code terminal, macro quick-bar, editable command input; keyboard on input tap only."""
import re
import time

from gi.repository import GLib, Gtk, Pango

from .core import Panel
from .widgets import Btn, HBox, IconBtn, Scroller, VBox, add_cls

MAX_LINES = 400
TEMP_RE = re.compile(r"^(ok\s+)?(B|T\d*|C):\s*-?\d")


class ConsolePanel(Panel):
    title = "Console"

    def __init__(self, app):
        super().__init__(app)
        self.history = []
        self.hist_idx = 0
        self.loaded = False
        self._pending = []
        self._flush_src = None
        self._kb_close = None

        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_can_focus(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(6)
        self.view.set_right_margin(6)
        add_cls(self.view, "console")
        self.buf = self.view.get_buffer()
        self.buf.create_tag("cmd", foreground="#62b6ff", weight=Pango.Weight.BOLD)
        self.buf.create_tag("err", foreground="#ff6b5e")
        self.buf.create_tag("info", foreground="#9aa3b5")
        self.buf.create_tag("time", foreground="#6a7284")
        self.end_mark = self.buf.create_mark("end", self.buf.get_end_iter(), False)
        term = Scroller(self.view)
        term.set_vexpand(True)
        add_cls(term, "console-frame")

        self.macro_box = HBox()
        self.macro_sw = Scroller(self.macro_box, horizontal=True, vertical=False)
        self.macro_sw.set_no_show_all(True)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("G-code command…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda _e: self.send())
        self.entry.connect("button-release-event", self._entry_tapped)
        self.entry.connect("key-press-event", self._entry_key)
        row = HBox(self.entry, IconBtn("trash", None, self.clear), IconBtn("send", None, self.send, "primary"),
                   expand=(0,))
        self.widget = VBox(term, self.macro_sw, row, expand=(0,))
        add_cls(self.widget, "panel")

    # ------------------------------------------------------------- lifecycle
    def on_show(self):
        if not self.loaded and self.mr.connected:
            self.loaded = True
            self.mr.call("server.gcode_store", {"count": 100}, self._on_store)
        self.build_macros()
        GLib.idle_add(lambda: self._scroll_end() and False)

    def on_hide(self):
        self._hide_keyboard()

    def on_ready(self):
        self.build_macros()
        if self.visible() and not self.loaded:
            self.on_show()

    def build_macros(self):
        for c in self.macro_box.get_children():
            self.macro_box.remove(c)
            c.destroy()
        hidden = {h.upper() for h in self.app.settings.get("macros_hidden", [])}
        names = [m for m in self.mr.macros() if not m.startswith("_") and m.upper() not in hidden]
        for n in names:
            self.macro_box.pack_start(Btn(n.replace("_", " "), lambda n=n: self.send(n)), False, False, 0)
        self.macro_sw.set_visible(bool(names))
        if names:
            self.macro_sw.set_size_request(-1, self.app.ui.touch + 8)
            self.macro_box.show_all()

    def _on_store(self, res, err):
        if err or not res:
            self.loaded = False
            return
        self.buf.set_text("")
        for item in res.get("gcode_store", []):
            msg = item.get("message", "")
            if item.get("type") == "command":
                self._insert(msg, "cmd", item.get("time"))
            else:
                self.append(msg, item.get("time"), immediate=True)
        self._scroll_end()

    # ---------------------------------------------------------------- output
    def append(self, line, ts=None, immediate=False):
        if self.app.settings.get("console_hide_temps", True) and TEMP_RE.match(line):
            return
        tag = "err" if line.startswith("!!") else "info" if line.startswith("//") else None
        if immediate:
            self._insert(line, tag, ts)
            return
        self._pending.append((line, tag, ts or time.time()))
        if not self._flush_src:
            self._flush_src = GLib.timeout_add(150, self._flush)

    def _flush(self):
        self._flush_src = None
        for line, tag, ts in self._pending:
            self._insert(line, tag, ts)
        self._pending = []
        if self.visible():
            self._scroll_end()
        return False

    def _insert(self, text, tag=None, ts=None):
        it = self.buf.get_end_iter()
        self.buf.insert_with_tags_by_name(it, time.strftime("%H:%M:%S ", time.localtime(ts or time.time())), "time")
        it = self.buf.get_end_iter()
        if tag:
            self.buf.insert_with_tags_by_name(it, text + "\n", tag)
        else:
            self.buf.insert(it, text + "\n")
        n = self.buf.get_line_count()
        if n > MAX_LINES:
            self.buf.delete(self.buf.get_start_iter(), self.buf.get_iter_at_line(n - MAX_LINES))

    def _scroll_end(self):
        self.buf.move_mark(self.end_mark, self.buf.get_end_iter())
        self.view.scroll_mark_onscreen(self.end_mark)
        return False

    def clear(self):
        self.buf.set_text("")

    # ----------------------------------------------------------------- input
    def _entry_tapped(self, _e, _ev):
        if not self._kb_close or getattr(self._kb_close, "modal", None) not in self.app.modals:
            self._kb_close = self.app.keyboard_popup(
                self.entry, on_enter=self.send, on_close=lambda: setattr(self, "_kb_close", None))
        return False

    def _hide_keyboard(self):
        if self._kb_close:
            self._kb_close()

    def _entry_key(self, _e, ev):
        from gi.repository import Gdk
        if ev.keyval == Gdk.KEY_Up and self.history:
            self.hist_idx = max(0, self.hist_idx - 1)
            self.entry.set_text(self.history[self.hist_idx])
            self.entry.set_position(-1)
            return True
        if ev.keyval == Gdk.KEY_Down and self.history:
            self.hist_idx = min(len(self.history), self.hist_idx + 1)
            self.entry.set_text(self.history[self.hist_idx] if self.hist_idx < len(self.history) else "")
            self.entry.set_position(-1)
            return True
        return False

    def send(self, cmd=None):
        cmd = (cmd if cmd is not None else self.entry.get_text()).strip()
        if not cmd:
            return
        if not self.history or self.history[-1] != cmd:
            self.history.append(cmd)
            self.history = self.history[-50:]
        self.hist_idx = len(self.history)
        if cmd == self.entry.get_text().strip():
            self.entry.set_text("")
        self._insert(cmd, "cmd")
        self._scroll_end()
        # Klipper echoes errors back as "!!" gcode responses, so no error callback here
        self.mr.call("printer.gcode.script", {"script": cmd})

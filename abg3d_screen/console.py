"""Console tab: G-code history, options, and a command line that opens the keyboard when tapped."""
import time
import tkinter as tk

from .keyboard import OnScreenKeyboard
from .page import Page
from .widgets import Switch

POLL_S = 1.5


class ConsolePage(Page):
    def build(self):
        pad = self.px(8)
        self.auto_scroll = True
        self._all = []
        self._offset = 0
        self._last = None
        self._last_poll = 0.0

        head = self.panel(self)
        head.pack(side="top", fill="x", padx=pad, pady=(pad, 0))
        self.label(head, "Console", 12, "bold", bg=self.t["panel"]).pack(
            side="left", padx=self.px(10), pady=self.px(6))
        self.button(head, "", self._clear, height=36, icon=self.app.icon("trash", 22)).pack(
            side="right", padx=self.px(6), pady=self.px(6))
        self.scroll_sw = Switch(head, "Auto-scroll", self._toggle_scroll, self.app, on=True,
                                height=36)
        self.scroll_sw.pack(side="right", padx=self.px(6), pady=self.px(6))

        # packed before the log, so the log fills the space between the header and the entry
        self._entry_row = tk.Frame(self, bg=self.t["bg"])
        self._entry_row.pack(side="bottom", fill="x", padx=pad, pady=pad)
        self.entry = tk.Entry(self._entry_row, font=("DejaVu Sans Mono", self.font(12)[1]),
                              bg=self.t["panel_alt"], fg=self.t["text"],
                              insertbackground=self.t["text"], relief="flat", bd=6)
        self.entry.pack(side="left", fill="x", expand=True, ipady=self.px(6))
        self.entry.bind("<ButtonRelease-1>", lambda _e: self._show_keyboard())
        self.entry.bind("<Return>", lambda _e: self._send())
        self.button(self._entry_row, "", self._send, "primary", height=44,
                    icon=self.app.icon("enter", 26)).pack(
            side="right", padx=(self.px(8), 0))
        self.keyboard = OnScreenKeyboard(self, self.app, on_key=self._insert,
                                         on_delete=self._delete, on_move=self._move,
                                         on_send=self._send, on_hide=self._hide_keyboard)

        self.log_frame = self.panel(self)
        self.log_frame.pack(side="top", fill="both", expand=True, padx=pad, pady=pad)
        self.log = tk.Text(self.log_frame, state="disabled", wrap="word", bd=0, height=6,
                           bg=self.t["panel"], fg=self.t["subtext"], highlightthickness=0,
                           font=("DejaVu Sans Mono", self.font(10)[1]), padx=8, pady=6)
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("cmd", foreground=self.t["accent"])

    # ---- lifecycle ----------------------------------------------------
    def on_show(self):
        self._poll()

    def refresh(self, st, online, demo):
        if time.time() - self._last_poll >= POLL_S:
            self._poll()

    # ---- log ----------------------------------------------------------
    def _poll(self):
        self._last_poll = time.time()
        self.app.run_async(lambda: self.app.backend.console_lines(60), None,
                           on_done=self._render)

    def _render(self, lines):
        self._all = lines
        shown = lines[self._offset:] if self._offset <= len(lines) else lines
        if shown == self._last:
            return
        self._last = shown
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for line in shown:
            tags = ("cmd",) if line.startswith(">") else ()
            self.log.insert("end", line + "\n", *tags)
        self.log.configure(state="disabled")
        if self.auto_scroll:
            self.log.see("end")

    def _clear(self):
        self._offset = len(self._all)
        self._last = None
        self._render(self._all)

    def _toggle_scroll(self):
        self.auto_scroll = self.scroll_sw.on

    # ---- entry and keyboard -------------------------------------------
    def _show_keyboard(self):
        if not self.keyboard.winfo_ismapped():
            # bottom-most, so the entry sits directly above the keyboard
            self.keyboard.pack(side="bottom", fill="x", before=self._entry_row)

    def _hide_keyboard(self):
        self.keyboard.pack_forget()

    def _insert(self, ch):
        self.entry.insert(tk.INSERT, ch)

    def _delete(self):
        pos = self.entry.index(tk.INSERT)
        if pos > 0:
            self.entry.delete(pos - 1)

    def _move(self, delta):
        pos = self.entry.index(tk.INSERT)
        self.entry.icursor(max(0, min(len(self.entry.get()), pos + delta)))

    def _send(self):
        script = self.entry.get().strip()
        if not script:
            return
        self.entry.delete(0, "end")
        self._hide_keyboard()
        self.app.run_async(lambda: self.app.backend.gcode(script), None)
        self.after(400, self._poll)

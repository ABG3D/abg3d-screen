"""On-screen keyboard shown under a text entry once that entry is tapped.

Two layouts: full text (letters, symbols, shift) and numeric (temperature entry).
The owner supplies callbacks: insert a key, delete, move the cursor, send, or hide.
"""
import tkinter as tk

from .widgets import RoundButton

FULL_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm", "=.-+_/:,"]
NUMERIC_ROWS = ["123", "456", "789"]


class OnScreenKeyboard(tk.Frame):
    def __init__(self, master, app, on_key, on_delete, on_move, on_send, on_hide, numeric=False):
        self.app = app
        self.t = app.theme
        self.on_key = on_key
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_send = on_send
        self.on_hide = on_hide
        self.numeric = numeric
        self.shift = False
        super().__init__(master, bg=self.t["panel_alt"])
        self._build()

    def _build(self):
        for child in self.winfo_children():
            child.destroy()
        pad = self.app.scale.px(4)
        for chars in (NUMERIC_ROWS if self.numeric else FULL_ROWS):
            self._row(chars, pad)
        if self.numeric:
            self._row("0", pad, extra=[
                ("<", lambda: self.on_move(-1), "secondary"),
                (">", lambda: self.on_move(1), "secondary"),
                ("Del", self.on_delete, "secondary"),
                ("Done", self.on_hide, "ok"),
            ])
        else:
            shift_style = "primary" if self.shift else "secondary"
            self._row("", pad, extra=[
                ("Shift", self._toggle_shift, shift_style),
                ("<", lambda: self.on_move(-1), "secondary"),
                ("Space", lambda: self.on_key(" "), "secondary"),
                (">", lambda: self.on_move(1), "secondary"),
                ("Del", self.on_delete, "secondary"),
                ("Hide", self.on_hide, "ghost"),
                ("Send", self.on_send, "ok"),
            ])

    def _row(self, chars, pad, extra=()):
        row = tk.Frame(self, bg=self.t["panel_alt"])
        row.pack(fill="both", expand=True, padx=pad, pady=(pad, 0))
        for ch in chars:
            label = ch.upper() if self.shift and ch.isalpha() else ch
            self._btn(row, label, lambda c=ch: self._press(c), "secondary")
        for label, cmd, style in extra:
            self._btn(row, label, cmd, style)

    def _btn(self, row, label, cmd, style):
        RoundButton(row, label, cmd, self.app, style, height=36, font=12).pack(
            side="left", fill="both", expand=True, padx=2)

    def _press(self, ch):
        self.on_key(ch.upper() if self.shift and ch.isalpha() else ch)

    def _toggle_shift(self):
        self.shift = not self.shift
        self._build()

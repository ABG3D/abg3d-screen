"""Set Temps dialog: nozzle and bed targets with a numeric keypad, presets and part fan."""
import tkinter as tk

from .keyboard import OnScreenKeyboard
from .widgets import RoundButton

NOZZLE_MAX = 350
BED_MAX = 130
PRESETS = [("Off", 0, 0), ("PLA", 210, 60), ("PETG", 240, 80), ("ABS", 250, 100)]
FANS = [("Off", 0), ("50%", 128), ("100%", 255)]


class TempModal(tk.Frame):
    def __init__(self, root, app, nozzle=0, bed=0):
        self.app = app
        self.t = app.theme
        self.sc = app.scale
        super().__init__(root, bg=self.t["bg"])
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        self.active = None
        self._build(nozzle, bed)

    def px(self, value):
        return self.sc.px(value)

    def _build(self, nozzle, bed):
        pad = self.px(14)
        tk.Label(self, text="Set temperatures", font=self.sc.font(15, "bold"), fg=self.t["text"],
                 bg=self.t["bg"]).pack(side="top", anchor="w", padx=pad, pady=(pad, 0))
        self.actions = tk.Frame(self, bg=self.t["bg"])
        self.actions.pack(side="bottom", fill="x", padx=pad, pady=(0, pad))
        RoundButton(self.actions, "Cancel", self.close, self.app, "ghost", height=50).pack(
            side="left", fill="x", expand=True, padx=(0, self.px(6)))
        RoundButton(self.actions, "Set", self._apply, self.app, "primary", height=50).pack(
            side="left", fill="x", expand=True)
        # packed after the action row, so it appears just above it when shown
        self.keypad = OnScreenKeyboard(self, self.app, on_key=self._insert, on_delete=self._delete,
                                       on_move=self._move, on_send=self._hide_pad,
                                       on_hide=self._hide_pad, numeric=True)

        body = tk.Frame(self, bg=self.t["bg"])
        body.pack(side="top", fill="both", expand=True, padx=pad, pady=pad)
        fields = tk.Frame(body, bg=self.t["bg"])
        fields.pack(fill="x")
        self.nozzle_entry = self._field(fields, f"Nozzle °C (max {NOZZLE_MAX})", nozzle)
        self.bed_entry = self._field(fields, f"Bed °C (max {BED_MAX})", bed)
        self.error = tk.Label(body, text="", fg=self.t["danger"], bg=self.t["bg"],
                              font=self.sc.font(11, "bold"))
        self.error.pack(anchor="w", pady=(self.px(6), 0))

        presets = tk.Frame(body, bg=self.t["bg"])
        presets.pack(fill="x", pady=(self.px(8), 0))
        for name, nozzle_v, bed_v in PRESETS:
            RoundButton(presets, name, lambda n=nozzle_v, b=bed_v: self._preset(n, b), self.app,
                        "secondary", height=44).pack(side="left", fill="x", expand=True, padx=3)
        fans = tk.Frame(body, bg=self.t["bg"])
        fans.pack(fill="x", pady=(self.px(8), 0))
        tk.Label(fans, text="Part fan", font=self.sc.font(10), fg=self.t["subtext"],
                 bg=self.t["bg"]).pack(side="left", padx=(3, self.px(8)))
        for name, value in FANS:
            RoundButton(fans, name, lambda v=value: self._fan(v), self.app, "secondary",
                        height=40).pack(side="left", fill="x", expand=True, padx=3)

    def _field(self, parent, text, value):
        box = tk.Frame(parent, bg=self.t["bg"])
        box.pack(side="left", fill="x", expand=True, padx=6)
        tk.Label(box, text=text, font=self.sc.font(10), fg=self.t["subtext"],
                 bg=self.t["bg"]).pack(anchor="w")
        entry = tk.Entry(box, font=("DejaVu Sans", self.sc.font(20, "bold")[1], "bold"), width=6,
                         justify="center", bg=self.t["panel_alt"], fg=self.t["text"],
                         insertbackground=self.t["text"], relief="flat", bd=6)
        entry.insert(0, str(value))
        entry.pack(fill="x", ipady=self.px(6))
        entry.bind("<ButtonRelease-1>", lambda _e, w=entry: self._focus(w))
        return entry

    # ---- keypad -------------------------------------------------------
    def _focus(self, entry):
        self.active = entry
        if not self.keypad.winfo_ismapped():
            self.keypad.pack(side="bottom", fill="x")

    def _hide_pad(self):
        self.keypad.pack_forget()

    def _insert(self, ch):
        if self.active is not None and ch.isdigit():
            self.active.insert(tk.INSERT, ch)

    def _delete(self):
        if self.active is None:
            return
        pos = self.active.index(tk.INSERT)
        if pos > 0:
            self.active.delete(pos - 1)

    def _move(self, delta):
        if self.active is None:
            return
        pos = self.active.index(tk.INSERT)
        self.active.icursor(max(0, min(len(self.active.get()), pos + delta)))

    # ---- actions ------------------------------------------------------
    def _preset(self, nozzle, bed):
        self._set(self.nozzle_entry, nozzle)
        self._set(self.bed_entry, bed)
        self._hide_pad()
        self.error.configure(text="")

    def _set(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value))

    def _fan(self, value):
        self.app.run_async(lambda: self.app.backend.gcode(f"M106 S{value}"), "Fan set")

    def _error(self, message):
        self.error.configure(text=message)

    def _apply(self):
        try:
            nozzle = int(self.nozzle_entry.get() or 0)
            bed = int(self.bed_entry.get() or 0)
        except ValueError:
            return self._error("Enter whole numbers only.")
        if not 0 <= nozzle <= NOZZLE_MAX:
            return self._error(f"Nozzle must be 0-{NOZZLE_MAX} °C.")
        if not 0 <= bed <= BED_MAX:
            return self._error(f"Bed must be 0-{BED_MAX} °C.")
        script = f"M104 S{nozzle}\nM140 S{bed}"
        self.app.run_async(lambda: self.app.backend.gcode(script),
                           f"Nozzle {nozzle} °C, bed {bed} °C")
        self.close()

    def close(self):
        self.destroy()

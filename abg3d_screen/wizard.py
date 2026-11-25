"""First-run printer wizard: choose family and model, which applies the matching theme."""
import json
import tkinter as tk

from . import ASSETS_DIR
from .widgets import RoundButton, apply_cursor


def load_printers():
    return json.loads((ASSETS_DIR / "data" / "printers.json").read_text())


class PrinterWizard(tk.Frame):
    def __init__(self, root, app, on_done, family=None):
        self.app = app
        self.t = app.theme
        self.sc = app.scale
        self.on_done = on_done
        self.printers = load_printers()
        self.family = None
        self.model = None
        self._images = []
        super().__init__(root, bg=self.t["bg"])
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()

        self.title_lbl = tk.Label(self, text="", font=self.sc.font(18, "bold"),
                                  fg=self.t["text"], bg=self.t["bg"])
        self.title_lbl.pack(anchor="w", padx=self.sc.px(20), pady=(self.sc.px(12), 0))
        self.sub_lbl = tk.Label(self, text="", font=self.sc.font(11), fg=self.t["subtext"],
                                bg=self.t["bg"])
        self.sub_lbl.pack(anchor="w", padx=self.sc.px(20))
        self.footer = tk.Frame(self, bg=self.t["bg"])
        self.footer.pack(side="bottom", fill="x", padx=self.sc.px(20), pady=self.sc.px(10))
        self.body = tk.Frame(self, bg=self.t["bg"])
        self.body.pack(fill="both", expand=True, padx=self.sc.px(20), pady=self.sc.px(6))
        if family in self.printers:
            self.family = family
            self.show_models()
        else:
            self.show_families()

    def _reset(self, title, subtitle):
        self.title_lbl.configure(text=title)
        self.sub_lbl.configure(text=subtitle)
        for frame in (self.body, self.footer):
            for child in frame.winfo_children():
                child.destroy()

    def _finish_step(self):
        apply_cursor(self, self.app.current_cursor())

    def _footer(self, back=None):
        if back:
            RoundButton(self.footer, "Back", back, self.app, "secondary", height=50).pack(
                side="left", fill="x", expand=True, padx=(0, self.sc.px(6)))
        RoundButton(self.footer, "Skip for now", self.skip, self.app, "ghost", height=50).pack(
            side="left", fill="x", expand=True)

    def _thumb(self, rel):
        img = tk.PhotoImage(file=str(ASSETS_DIR / rel))
        factor = max(1, round(img.width() / max(60, 120 * self.sc.s)))
        img = img.subsample(factor) if factor > 1 else img
        self._images.append(img)
        return img

    # ---- steps ---------------------------------------------------------
    def show_families(self):
        self._reset("Choose your printer",
                    "Sets the colour theme for this screen. You can change it later in Settings.")
        grid = tk.Frame(self.body, bg=self.t["bg"])
        grid.pack(fill="both", expand=True)
        for i, (key, info) in enumerate(self.printers.items()):
            card = tk.Frame(grid, bg=self.t["panel"])
            card.grid(row=i // 2, column=i % 2, sticky="nsew",
                      padx=self.sc.px(8), pady=self.sc.px(6))
            thumb = tk.Label(card, image=self._thumb(info["image"]), bg=self.t["panel"], bd=0)
            thumb.pack(padx=self.sc.px(8), pady=(self.sc.px(8), self.sc.px(2)))
            name = tk.Label(card, text=info["name"], font=self.sc.font(13, "bold"),
                            fg=self.t["text"], bg=self.t["panel"])
            name.pack(pady=(0, self.sc.px(6)))
            for widget in (card, thumb, name):
                widget.bind("<ButtonRelease-1>", lambda _e, k=key: self.pick_family(k))
        for col in (0, 1):
            grid.columnconfigure(col, weight=1, uniform="card")
        for row in range((len(self.printers) + 1) // 2):
            grid.rowconfigure(row, weight=1)
        self._footer()
        self._finish_step()

    def pick_family(self, key):
        self.family = key
        self.show_models()

    def show_models(self):
        info = self.printers[self.family]
        self._reset(info["name"], "Select your model")
        grid = tk.Frame(self.body, bg=self.t["bg"])
        grid.pack(fill="both", expand=True)
        cols = 3
        models = info["models"]
        for i, model in enumerate(models):
            RoundButton(grid, model, lambda m=model: self.pick_model(m), self.app,
                        "secondary", height=60).grid(row=i // cols, column=i % cols, sticky="nsew",
                                                     padx=6, pady=6)
        for col in range(cols):
            grid.columnconfigure(col, weight=1, uniform="model")
        for row in range((len(models) + cols - 1) // cols):
            grid.rowconfigure(row, weight=1)
        self._footer(back=self.show_families)
        self._finish_step()

    def pick_model(self, model):
        self.model = model
        self.show_confirm()

    def show_confirm(self):
        info = self.printers[self.family]
        theme = self.app.themes.get(info["theme"])
        theme_name = theme.name if theme else info["theme"]
        self._reset("Confirm", f"{info['name']} - {self.model}")
        box = tk.Frame(self.body, bg=self.t["panel"])
        box.pack(fill="x", pady=self.sc.px(10))
        tk.Label(box, justify="left", bg=self.t["panel"], fg=self.t["text"],
                 font=self.sc.font(12),
                 text=(f"The '{theme_name}' colour theme will be applied.\n"
                       "Your choice is saved and restored after every reboot.")
                 ).pack(padx=self.sc.px(16), pady=self.sc.px(16), anchor="w")
        row = tk.Frame(self.body, bg=self.t["bg"])
        row.pack(side="bottom", fill="x")
        RoundButton(row, "Apply", self.finish, self.app, "primary", height=60).pack(
            side="left", fill="x", expand=True, padx=(0, self.sc.px(6)))
        RoundButton(row, "Back", self.show_models, self.app, "secondary", height=60).pack(
            side="left", fill="x", expand=True)
        self._footer_skip_only()
        self._finish_step()

    def _footer_skip_only(self):
        RoundButton(self.footer, "Skip for now", self.skip, self.app, "ghost", height=50).pack(
            fill="x")

    def finish(self):
        info = self.printers[self.family]
        self.destroy()
        self.on_done(info["theme"], self.family, self.model)

    def skip(self):
        self.destroy()
        self.on_done(None, None, None)

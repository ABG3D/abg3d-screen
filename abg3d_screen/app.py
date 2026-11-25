"""Main window: header, tab bar, page switching, background data and task queue."""
import math
import queue
import threading
import time
import tkinter as tk

from . import ASSETS_DIR, __app_name__
from .backend import Backend
from .mmu import is_active
from .config import Settings
from .theme import Scale, load_themes
from .widgets import apply_cursor
from .console import ConsolePage
from .dialogs import TempModal
from .wizard import PrinterWizard
from . import screens

ICON_DIR = ASSETS_DIR / "icons"
LOGO = ASSETS_DIR / "logo.png"
SPLASH_BG = "#0c0f14"
TABS = [
    ("home", "Home", screens.HomePage),
    ("control", "Control", screens.ControlPage),
    ("console", "Console", ConsolePage),
    ("mmu", "MMU", screens.MMUPage),
    ("system", "System", screens.SystemPage),
    ("settings", "Settings", screens.SettingsPage),
]


class App:
    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.settings = Settings()
        self.themes = load_themes()
        self.theme = self._theme(self.settings.get("theme"))
        self.current = None
        self.pages = {}
        self.tab_buttons = {}
        self._icon_cache = {}
        self._queue = queue.Queue()
        self._toast_job = None
        self._splash = None
        self._splash_job = None

        root.title(__app_name__)
        if args.windowed:
            width, height = 800, 480
            root.geometry(f"{width}x{height}+0+0")
            root.bind("<Escape>", lambda _e: self.quit())
        else:
            width, height = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{width}x{height}+0+0")
            try:
                root.attributes("-fullscreen", True)
            except tk.TclError:
                pass  # no window manager: the full-size geometry is enough
        self.scale = Scale(width, height)
        self.backend = Backend(self.settings.get("moonraker_url"), force_demo=args.demo,
                               simulate_mmu=args.simulate_mmu)
        self._mmu_seen = None
        self._mmu_block_until = 0.0
        root.protocol("WM_DELETE_WINDOW", self.quit)

        self._build_chrome()
        if self.settings.get("show_splash") and not args.no_splash:
            self._show_splash()
        else:
            self._after_splash()
        self._tick()

    # ---- helpers -------------------------------------------------------
    def _theme(self, key):
        return self.themes.get(key) or self.themes["midnight"]

    def _visible_tabs(self):
        """The MMU tab is only built when Enable MMU is on in Settings."""
        return [t for t in TABS if t[0] != "mmu" or self.settings.get("mmu_enabled")]

    def toggle_mmu(self):
        if not self.settings.get("mmu_enabled"):
            if not is_active(self.backend.detection):
                self._mmu_block_until = time.time() + 8
                return
            self.settings.set("mmu_enabled", True)
        else:
            self.settings.set("mmu_enabled", False)
        self._mmu_block_until = 0.0
        self.root.after_idle(self._build_chrome)

    def mmu_block_message(self):
        if time.time() < self._mmu_block_until:
            return ("No MMU detected. Attach and configure Happy Hare, Box Turtle / AFC or KTC "
                    "on this printer, then enable it.")
        return ""

    def toggle_quit(self):
        self.settings.set("allow_quit", not self.settings.get("allow_quit"))

    def current_cursor(self):
        return "" if self.settings.get("mouse_pointer") else "none"

    def icon(self, name, size=34):
        """Return a cached icon scaled to roughly `size` base pixels on this screen."""
        key = (name, size)
        if key not in self._icon_cache:
            img = tk.PhotoImage(file=str(ICON_DIR / f"{name}.png"))
            factor = max(1, round(img.width() / max(12, size * self.scale.s)))
            self._icon_cache[key] = img.subsample(factor) if factor > 1 else img
        return self._icon_cache[key]

    def _icon(self, name):
        return self.icon(name, 34)

    def run_async(self, fn, message=None, on_done=None):
        """Run a blocking call (network or system) off the UI thread; report via the toast."""
        def worker():
            try:
                result = fn()
                self._queue.put(("ok", message, result, on_done))
            except Exception as exc:
                self._queue.put(("err", str(exc), None, None))
        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self):
        while True:
            try:
                kind, msg, result, callback = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "ok":
                if msg:
                    self.toast(msg)
                if callback:
                    callback(result)
            else:
                self.toast(f"Failed: {msg[:90]}", error=True)

    def toast(self, message, ms=2600, error=False):
        self.toast_lbl.configure(text=message, fg=self.theme["danger"] if error else self.theme["text"])
        self.toast_lbl.place(relx=0.5, rely=1.0, y=-(self.scale.px(74) + self.scale.px(10)), anchor="s")
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(ms, self.toast_lbl.place_forget)

    # ---- chrome (header, tab bar, pages) ---------------------------------
    def _build_chrome(self):
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
            self._toast_job = None
        for name in ("header", "tabbar", "content", "toast_lbl"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.destroy()
        t, s = self.theme, self.scale
        self.root.configure(bg=t["bg"])

        self.header = tk.Frame(self.root, bg=t["panel"], height=s.px(40))
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)
        tk.Label(self.header, text="ABG3D", font=s.font(14, "bold"), fg=t["accent"],
                 bg=t["panel"]).pack(side="left", padx=(s.px(12), 0))
        tk.Label(self.header, text="Screen", font=s.font(12), fg=t["text"],
                 bg=t["panel"]).pack(side="left", padx=(s.px(4), s.px(16)))
        self.state_lbl = tk.Label(self.header, text="", font=s.font(12, "bold"),
                                  fg=t["text"], bg=t["panel"])
        self.state_lbl.pack(side="left")
        self.clock_lbl = tk.Label(self.header, text="", font=s.font(12), fg=t["subtext"],
                                  bg=t["panel"])
        self.clock_lbl.pack(side="right", padx=s.px(12))
        self.link_lbl = tk.Label(self.header, text="", font=s.font(11), fg=t["subtext"],
                                 bg=t["panel"])
        self.link_lbl.pack(side="right", padx=s.px(8))

        self.tabbar = tk.Frame(self.root, bg=t["panel"], height=s.px(74))
        self.tabbar.pack(side="bottom", fill="x")
        self.tabbar.pack_propagate(False)
        self.content = tk.Frame(self.root, bg=t["bg"])
        self.content.pack(fill="both", expand=True)
        self.toast_lbl = tk.Label(self.root, text="", font=s.font(12), fg=t["text"],
                                  bg=t["panel_alt"], padx=s.px(14), pady=s.px(6))

        tabs = self._visible_tabs()
        self.pages = {key: cls(self.content, self) for key, _label, cls in tabs}
        self.tab_buttons = {}
        for key, label, _cls in tabs:
            btn = tk.Button(self.tabbar, text=label, image=self._icon(key), compound="top",
                            font=s.font(9), relief="flat", bd=0, highlightthickness=0,
                            command=lambda k=key: self.show(k))
            btn.pack(side="left", fill="both", expand=True)
            self.tab_buttons[key] = btn

        self.show(self.current if self.current in self.pages else "home")
        apply_cursor(self.root, self.current_cursor())

    def show(self, key):
        if key not in self.pages:
            return
        for name, page in self.pages.items():
            if name != key:
                page.pack_forget()
        self.current = key
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        page.on_show()
        self._restyle_tabs()

    def _restyle_tabs(self):
        for key, btn in self.tab_buttons.items():
            active = key == self.current
            btn.configure(fg=self.theme["accent"] if active else self.theme["subtext"],
                          bg=self.theme["panel_alt"] if active else self.theme["panel"],
                          activebackground=self.theme["panel_alt"],
                          activeforeground=self.theme["text"],
                          disabledforeground=self.theme["border"])
        self._sync_mmu_tab()

    def _sync_mmu_tab(self):
        """Enable the MMU tab only while a supported MMU is detected on this printer."""
        detection = self.backend.detection
        active = is_active(detection)
        btn = self.tab_buttons.get("mmu")
        if btn is not None:
            btn.configure(state="normal" if active else "disabled")
        key = detection.get("mmu") if active else None
        if key != self._mmu_seen:
            if key:
                self.toast(f"{detection.get('mmu_name', key)} detected - MMU tab enabled")
            self._mmu_seen = key
        if not active and self.current == "mmu":
            self.show("home")

    def apply_theme(self, key):
        self.theme = self._theme(key)
        self.settings.set("theme", self.theme.key)
        self._build_chrome()

    def toggle_pointer(self):
        on = not self.settings.get("mouse_pointer")
        self.settings.set("mouse_pointer", on)
        apply_cursor(self.root, self.current_cursor())

    def open_temp_modal(self, nozzle_target=0, bed_target=0):
        TempModal(self.root, self, int(round(nozzle_target)), int(round(bed_target)))

    def open_wizard(self, family=None):
        PrinterWizard(self.root, self, on_done=self._wizard_done, family=family)

    def _wizard_done(self, theme_key, family, model):
        if family:
            self.settings.update(setup_done=True, printer_family=family, printer_model=model)
        else:
            self.settings.update(setup_done=True)
        if theme_key:
            self.root.after_idle(lambda: self.apply_theme(theme_key))

    # ---- splash -------------------------------------------------------
    def _show_splash(self):
        self._splash = tk.Frame(self.root, bg=SPLASH_BG)
        self._splash.place(x=0, y=0, relwidth=1, relheight=1)
        img = tk.PhotoImage(file=str(LOGO))
        factor = max(1, math.ceil(img.height() / (self.scale.height * 0.42)))
        self._splash_img = img.subsample(factor) if factor > 1 else img
        logo = tk.Label(self._splash, image=self._splash_img, bg=SPLASH_BG, bd=0)
        logo.place(relx=0.5, rely=0.42, anchor="center")
        tag = tk.Label(self._splash, text="Starting...", font=self.scale.font(10),
                       fg="#6b7485", bg=SPLASH_BG)
        tag.place(relx=0.5, rely=0.88, anchor="center")
        for widget in (self._splash, logo, tag):
            widget.bind("<ButtonRelease-1>", lambda _e: self._dismiss_splash())
        self._splash_job = self.root.after(2200, self._dismiss_splash)

    def _dismiss_splash(self):
        if self._splash is None:
            return
        if self._splash_job:
            self.root.after_cancel(self._splash_job)
            self._splash_job = None
        self._splash.destroy()
        self._splash = None
        self._after_splash()

    def _after_splash(self):
        if not self.settings.get("setup_done") or self.args.reset_setup:
            self.open_wizard()

    # ---- main loop ----------------------------------------------------
    def _tick(self):
        self._drain_queue()
        status, online, demo = self.backend.snapshot()
        self._update_header(status, online, demo)
        self._sync_mmu_tab()
        if self.current:
            self.pages[self.current].refresh(status, online, demo)
        self.clock_lbl.configure(text=time.strftime("%H:%M"))
        self.root.after(500, self._tick)

    def _update_header(self, status, online, demo):
        t = self.theme
        state = (status.get("print_stats") or {}).get("state") or "standby"
        progress = float((status.get("display_status") or {}).get("progress") or 0) * 100
        if demo:
            text, color = "Demo mode", t["warn"]
        elif state == "printing":
            text, color = f"Printing {progress:.0f}%", t["accent"]
        elif state == "error":
            text, color = "Error", t["danger"]
        else:
            text, color = state.capitalize(), t["text"]
        self.state_lbl.configure(text=text, fg=color)
        if online:
            self.link_lbl.configure(text="● online", fg=t["ok"])
        else:
            self.link_lbl.configure(text="● no Moonraker", fg=t["warn"])

    def quit(self):
        self.backend.stop()
        self.root.destroy()

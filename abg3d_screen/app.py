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
from .widgets import apply_cursor, drag_motion, drag_press
from .console import ConsolePage
from .honeycomb import HexFrame
from .dialogs import TempModal
from . import display
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
        self.asleep = False
        self._overlay = None
        self._last_activity = time.time()
        root.bind_all("<ButtonPress>", self._on_activity_press, add="+")
        root.bind_all("<B1-Motion>", self._on_activity_motion, add="+")
        root.bind_all("<Motion>", self._on_activity_motion, add="+")
        root.bind_all("<ButtonPress-1>", drag_press, add="+")
        root.bind_all("<B1-Motion>", drag_motion, add="+")
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

    def toggle_setting(self, key):
        self.settings.set(key, not self.settings.get(key))

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

        self.header = HexFrame(self.root, self, height=s.px(40))
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)
        hb = t["bg"]
        tk.Label(self.header, text="ABG3D", font=s.font(14, "bold"), fg=t["accent"],
                 bg=hb).pack(side="left", padx=(s.px(12), 0))
        tk.Label(self.header, text="Screen", font=s.font(12), fg=t["text"],
                 bg=hb).pack(side="left", padx=(s.px(4), s.px(16)))
        self.state_lbl = tk.Label(self.header, text="", font=s.font(12, "bold"),
                                  fg=t["text"], bg=hb)
        self.state_lbl.pack(side="left")
        self.clock_lbl = tk.Label(self.header, text="", font=s.font(12), fg=t["subtext"], bg=hb)
        self.clock_lbl.pack(side="right", padx=s.px(12))
        self.link_lbl = tk.Label(self.header, text="", font=s.font(11), fg=t["subtext"], bg=hb)
        self.link_lbl.pack(side="right", padx=s.px(8))
        self.mcu_lbl = tk.Label(self.header, text="", font=s.font(11), fg=t["subtext"], bg=hb)
        self.mcu_lbl.pack(side="right", padx=s.px(8))

        self.tabbar = HexFrame(self.root, self, height=s.px(74))
        self.tabbar.pack(side="bottom", fill="x")
        self.tabbar.pack_propagate(False)
        self.content = HexFrame(self.root, self)
        self.content.pack(fill="both", expand=True)
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

    # ---- splash -------------------------------------------------------
    def _show_splash(self):
        self._splash = HexFrame(self.root, self)
        self._splash.place(x=0, y=0, relwidth=1, relheight=1)
        img = tk.PhotoImage(file=str(LOGO))
        factor = max(1, math.ceil(img.height() / (self.scale.height * 0.42)))
        self._splash_img = img.subsample(factor) if factor > 1 else img
        logo = tk.Label(self._splash, image=self._splash_img, bg=self.theme["bg"], bd=0)
        logo.place(relx=0.5, rely=0.42, anchor="center")
        tag = tk.Label(self._splash, text="Starting...", font=self.scale.font(10),
                       fg=self.theme["subtext"], bg=self.theme["bg"])
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
        """Splash finished. The Home screen is already showing."""
        return

    # ---- main loop ----------------------------------------------------
    def _tick(self):
        self._drain_queue()
        status, online, demo = self.backend.snapshot()
        self._update_header(status, online, demo)
        self._sync_mmu_tab()
        if self.current:
            self.pages[self.current].refresh(status, online, demo)
        self.clock_lbl.configure(text=time.strftime("%H:%M"))
        self._check_idle()
        self.root.after(500, self._tick)

    def _update_header(self, status, online, demo):
        t = self.theme
        det = self.backend.detection
        state = (status.get("print_stats") or {}).get("state") or "standby"
        progress = float((status.get("display_status") or {}).get("progress") or 0) * 100
        if demo:
            text, color = "Demo mode", t["warn"]
        elif state == "printing":
            text, color = f"Printing {progress:.0f}%", t["accent"]
        elif state == "error":
            text, color = "Error", t["danger"]
        elif state == "standby" and det.get("mcu") == "no":
            text, color = "Standby - No MCU", t["warn"]
        else:
            text, color = state.capitalize(), t["text"]
        self.state_lbl.configure(text=text, fg=color)
        if online:
            self.link_lbl.configure(text="● online", fg=t["ok"])
        else:
            self.link_lbl.configure(text="● no Moonraker", fg=t["warn"])
        mcu_ok = det.get("mcu_status") == "online"
        self.mcu_lbl.configure(text="● MCU Online" if mcu_ok else "● MCU Offline",
                               fg=t["ok"] if mcu_ok else t["danger"])

    # ---- screen power -----------------------------------------------------
    def set_screen_timeout(self, seconds):
        self.settings.set("screen_timeout", int(seconds))
        self._last_activity = time.time()

    def _on_activity_press(self, _event):
        if not self.asleep:
            self._last_activity = time.time()

    def _on_activity_motion(self, _event):
        if self.asleep:
            self.wake()
        else:
            self._last_activity = time.time()

    def _check_idle(self):
        limit = int(self.settings.get("screen_timeout") or 0)
        if limit and not self.asleep and time.time() - self._last_activity >= limit:
            self.screen_off()

    def screen_off(self):
        if self.asleep:
            return
        self.asleep = True
        display.screen_off()
        self._overlay = tk.Frame(self.root, bg="#000000")
        self._overlay.place(x=0, y=0, relwidth=1, relheight=1)
        hint = tk.Label(self._overlay, text="Touch to wake", fg="#3a3f4a", bg="#000000",
                        font=self.scale.font(12))
        hint.place(relx=0.5, rely=0.5, anchor="center")
        # The wake tap lands on this overlay and is absorbed, so no button underneath fires.
        for widget in (self._overlay, hint):
            widget.bind("<ButtonRelease-1>", lambda _e: self.wake())
        self._overlay.lift()

    def wake(self):
        if not self.asleep:
            return
        self.asleep = False
        display.screen_on()
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None
        self._last_activity = time.time()

    def quit(self):
        self.backend.stop()
        self.root.destroy()

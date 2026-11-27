"""System: Klipper / Moonraker service restarts, host power, version + resource info."""
import os

from gi.repository import Gtk

from . import __version__
from .core import Panel
from .network import local_ips
from .widgets import HBox, IconBtn, Lbl, M, Scroller, Section, VBox, add_cls


def rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return "%.1f MB" % (int(line.split()[1]) / 1024.0)
    except OSError:
        pass
    return "?"


def grid(items, cols):
    g = Gtk.Grid(row_spacing=M["sp"], column_spacing=M["sp"])
    g.set_column_homogeneous(True)
    for i, w in enumerate(items):
        g.attach(w, i % cols, i // cols, 1, 1)
    return g


class SystemPanel(Panel):
    title = "System"

    def __init__(self, app):
        super().__init__(app)
        mr = app.mr
        cols = 3 if app.ui.w >= 600 else 2

        def post(path, label, params=None):
            """POST a Moonraker REST endpoint with immediate + result feedback (works without MCU)."""
            def run():
                app.toast("%s\u2026" % label)

                def done(_res, err):
                    if err:
                        app.toast("%s failed: %s" % (label, err.get("message", "error")), error=True)
                    else:
                        app.toast("%s: request accepted" % label)
                mr.http("POST", path, params, cb=done)
            return run

        def btn(icon, label, fn, danger=False, ask=None):
            cb = (lambda: app.confirm(ask, fn, ok=label, danger=danger)) if ask else fn
            return IconBtn(icon, label, cb, "danger" if danger else None, vertical=not app.ui.small)

        def svc(name, label):
            return btn("service", label, post("/machine/services/restart", "Restarting %s" % name,
                                              {"service": name}))

        self.info_box = VBox(spacing=2)
        body = VBox(
            Section("Klipper", "chip"),
            grid([btn("restart", "Restart", post("/printer/restart", "Klipper restart")),
                  btn("chip", "FW Restart", post("/printer/firmware_restart", "Firmware restart")),
                  svc("klipper", "Klipper Service")], cols),
            Section("Moonraker", "network"),
            grid([svc("moonraker", "Moonraker"),
                  svc("abg3d-screen", "Screen UI"),
                  btn("refresh", "Sync Mainsail",
                      lambda: (app.toast("Syncing Mainsail\u2026"),
                               mr.load_mainsail(lambda d: app.toast("Mainsail data synced"))))], cols),
            Section("Host", "power"),
            grid([btn("refresh", "Reboot", post("/machine/reboot", "Reboot"), danger=True,
                      ask="Reboot the host computer?"),
                  btn("power", "Shutdown", post("/machine/shutdown", "Shutdown"), danger=True,
                      ask="Shut down the host computer?")], cols),
            Section("Info", "info"),
            self.info_box, spacing=app.ui.sp)
        self.widget = Scroller(body)
        add_cls(body, "panel")

    def refresh(self):
        mr = self.mr
        rows = [("abg3d-screen", "%s • RAM %s" % (__version__, rss_mb())),
                ("Display", "%dx%d • %.0f dpi • %.1f\"" % (self.app.ui.w, self.app.ui.h,
                                                                   self.app.ui.dpi, self.app.ui.diag_in)),
                ("Moonraker", mr.server_info.get("moonraker_version", "--")),
                ("Klipper", mr.printer_info.get("software_version", "--")),
                ("Klippy", mr.klippy_state),
                ("Host", "%s • %s" % (mr.printer_info.get("hostname", os.uname().nodename),
                                          ", ".join(local_ips()) or "no IP"))]
        self._render(rows)

        def got(res, err):
            if err or not res or not self.visible():
                return
            si = res.get("system_info", {})
            cpu = si.get("cpu_info", {})
            self._render(rows + [("OS", si.get("distribution", {}).get("name", "--")),
                                 ("Board", cpu.get("model") or cpu.get("cpu_desc", "--")),
                                 ("Memory", "%s %s" % (cpu.get("total_memory", "--"), cpu.get("memory_units", "")))])
        mr.call("machine.system_info", None, got)

    def _render(self, rows):
        for c in self.info_box.get_children():
            self.info_box.remove(c)
            c.destroy()
        for k, v in rows:
            r = HBox(Lbl(k, "muted", "small"), Lbl(str(v), "small", xalign=1.0, wrap=True), expand=(1,))
            add_cls(r, "row")
            self.info_box.pack_start(r, False, False, 0)
        self.info_box.show_all()

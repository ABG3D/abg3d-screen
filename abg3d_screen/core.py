"""Panel base class, temperature history buffer and screen blanking."""
import glob
import logging
import os
import subprocess
import time
from collections import deque

from gi.repository import GLib

log = logging.getLogger("abg3d.core")


class Panel:
    title = ""

    def __init__(self, app):
        self.app = app
        self.mr = app.mr
        self.widget = None

    def visible(self):
        return self.app.current is self

    def on_show(self):
        self.refresh()

    def on_hide(self):
        pass

    def on_ready(self):
        pass

    def on_status(self, changes):
        pass

    def refresh(self):
        pass

    def on_background_status(self, changes):
        pass

    def on_gcode_response(self, line):
        pass


class TempHistory:
    """Fixed-size ring buffers of (temperature, target) sampled once per second."""

    def __init__(self, mr, size=600, max_series=8):
        self.mr, self.size, self.max_series = mr, size, max_series
        self.series = {}
        self.order = []
        self._targets = set()

    def setup(self):
        names = self.mr.heaters() + self.mr.temp_fans() + self.mr.sensors()
        names = names[:self.max_series]
        self.series = {n: self.series.get(n) or deque(maxlen=self.size) for n in names}
        self.order = names
        self._targets = set(self.mr.heaters() + self.mr.temp_fans())

    def has_target(self, name):
        return name in self._targets

    def color_index(self, name):
        try:
            return self.order.index(name)
        except ValueError:
            return -1

    def seed(self, store):
        for name, d in (store or {}).items():
            buf = self.series.get(name)
            if buf is None or len(buf):
                continue
            temps = (d.get("temperatures") or [])[-self.size:]
            targets = (d.get("targets") or [])[-self.size:]
            if len(targets) != len(temps):
                targets = [0.0] * len(temps)
            buf.extend(zip(temps, targets))

    def sample(self):
        data = self.mr.data
        for name in self.order:
            st = data.get(name)
            if not st or st.get("temperature") is None:
                continue
            self.series[name].append((float(st["temperature"]), float(st.get("target") or 0.0)))


class Blanker:
    """Idle timeout + immediate Screen Off.

    Blanks with `xset dpms force off`, falling back to /sys/class/backlight/*/bl_power,
    and always raises a black input-absorbing overlay so the waking tap never reaches
    the widget underneath.
    """

    def __init__(self, app):
        self.app = app
        self.last = time.monotonic()
        self.blanked = False
        self.method = None
        self.backlight = self._find_backlight()
        # DPMS enabled but with no automatic timeouts: only we decide when to blank.
        self._x("s", "off")
        self._x("s", "noblank")
        self._x("+dpms")
        self._x("dpms", "0", "0", "0")
        GLib.timeout_add_seconds(5, self._tick)

    @staticmethod
    def _find_backlight():
        for p in sorted(glob.glob("/sys/class/backlight/*")):
            if os.access(os.path.join(p, "bl_power"), os.W_OK):
                return p
        return None

    def _bl_power(self, value):
        if not self.backlight:
            return False
        try:
            with open(os.path.join(self.backlight, "bl_power"), "w") as f:
                f.write(str(value))
            return True
        except OSError:
            return False

    @staticmethod
    def _x(*args):
        if not os.environ.get("DISPLAY"):
            return False
        try:
            r = subprocess.run(["xset"] + list(args), timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def activity(self):
        self.last = time.monotonic()

    def _tick(self):
        timeout = int(self.app.settings.get("blank_timeout", 0) or 0)
        if timeout > 0 and not self.blanked and time.monotonic() - self.last > timeout:
            if not self.app.mr.is_printing() or self.app.settings.get("blank_while_printing"):
                self.blank()
        return True

    def blank(self):
        if self.blanked:
            return
        self.blanked = True
        self.app.show_blank(True)
        # let the black overlay paint first, then power the panel down
        GLib.timeout_add(250, self._power_off)

    def _power_off(self):
        if not self.blanked:
            return False
        if self._x("dpms", "force", "off"):
            self.method = "dpms"
        elif self._bl_power(4):
            self.method = "bl_power"
        else:
            self.method = "overlay"
        log.info("screen off (%s)", self.method)
        return False

    def unblank(self):
        if not self.blanked:
            return
        self.blanked = False
        if self.method == "dpms":
            self._x("dpms", "force", "on")
        elif self.method == "bl_power":
            self._bl_power(0)
        self.method = None
        self.last = time.monotonic()
        log.info("screen on")

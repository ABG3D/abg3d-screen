"""Data and action layer.

When Moonraker is reachable this talks to it. When it is not (no Klipper, no MCU,
or a VM for testing) it switches to a simulated demo printer so the whole UI still
works. System actions (restart Klipper, reboot, shut down) go through sudo rules
written by install.sh, so they work in both modes.
"""
import collections
import posixpath
import random
import socket
import subprocess
import threading
import time
import urllib.parse

from . import detect
from .detect import MMU_NAMES
from .moonraker import MoonrakerClient

QUERY_OBJECTS = ["print_stats", "display_status", "virtual_sdcard", "toolhead",
                 "extruder", "heater_bed", "fan", "webhooks", "idle_timeout"]
AMBIENT = 24.0
DEMO_MACROS = ["PRINT_START", "PRINT_END", "PARK", "CLEAN_NOZZLE"]


def _param(parts, letter):
    for part in parts[1:]:
        if part[:1].upper() == letter:
            try:
                return float(part[1:])
            except ValueError:
                return None
    return None


def system_command(cmd):
    """Run a privileged command via the sudoers rule installed by install.sh."""
    try:
        res = subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from None
    if res.returncode != 0:
        lines = (res.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "command failed")
    return "ok"


class Backend:
    def __init__(self, url, force_demo=False, simulate_mmu=None):
        self.client = MoonrakerClient(url)
        self.force_demo = force_demo
        self.simulate_mmu = simulate_mmu  # testing only: pretend this MMU is installed
        self.online = False
        self.demo = force_demo
        self.objects = []
        self.status = {}
        self.detection = {}
        self.error = ""
        self._last_detect = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sim_target = {"ext": 0.0, "bed": 0.0}
        self._sim_temp = {"ext": AMBIENT, "bed": AMBIENT, "chamber": AMBIENT}
        self.temp_objects = []
        self._sim_fan = 0
        self._demo_log = collections.deque(
            ["DEMO: no Moonraker/MCU connection. Commands are simulated."], maxlen=200)
        threading.Thread(target=self._loop, daemon=True, name="abg3d-backend").start()

    # ---- polling -------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return dict(self.status), self.online, self.demo

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._poll()
            except Exception as exc:  # the poller must never die
                self.error = str(exc)
            if not self.detection or time.time() - self._last_detect > 30:
                try:
                    self.refresh_detection()
                except Exception as exc:
                    self.error = str(exc)
            self._stop.wait(1.0)

    def _poll(self):
        if not self.force_demo:
            try:
                self.client.server_info()
                if not self.objects:
                    self.objects = self.client.list_objects()
                    self.temp_objects = detect.temp_object_names(self.objects)
                status = self.client.query(QUERY_OBJECTS + self.temp_objects)
                with self._lock:
                    self.online, self.demo, self.status = True, False, status
                self.error = ""
                return
            except Exception as exc:  # Moonraker missing, Klipper starting, or no MCU
                self.error = str(exc)
                self.objects = []
                self.temp_objects = []
        with self._lock:
            self.online, self.demo = False, True
            self.status = self._simulate()

    def refresh_detection(self):
        klipper = detect.find_klipper_dir()
        config = detect.find_config_dir()
        mmu_key = self.simulate_mmu or detect.detect_mmu(klipper, config, self.objects)
        info = {
            "host": socket.gethostname(),
            "os": detect.os_pretty_name(),
            "ip": detect.local_ip(),
            "klipper_dir": str(klipper) if klipper else "not found",
            "config_dir": str(config) if config else "not found",
            "klipper_service": detect.service_state("klipper"),
            "moonraker_service": detect.service_state("moonraker"),
            "mcu": "yes" if detect.mcu_present(self.objects) else "no",
            "mmu": mmu_key,
            "mmu_name": MMU_NAMES.get(mmu_key, mmu_key),
        }
        info.update(detect.detect_printer_features(config, self.objects))
        info["leds"] = detect.led_names(self.objects)
        if self.online:
            info["macros"] = detect.macro_names(self.objects)
        else:
            info["macros"] = list(DEMO_MACROS) if self.demo else []
        info["pins"] = detect.read_pins(config)
        info["mcu_status"] = "online" if (self.online and info["mcu"] == "yes") else "offline"
        with self._lock:
            self.detection = info
        self._last_detect = time.time()

    # ---- demo simulation ----------------------------------------------
    def _simulate(self):
        for key in ("ext", "bed"):
            target = self._sim_target[key]
            goal = target if target > 0 else AMBIENT
            step = max(-2.5, min(2.5, (goal - self._sim_temp[key]) * 0.3))
            self._sim_temp[key] += step + random.uniform(-0.15, 0.15)
        self._sim_temp["chamber"] += (31.0 - self._sim_temp["chamber"]) * 0.02 + random.uniform(-0.05, 0.05)
        return {
            "temperature_sensor chamber": {"temperature": round(self._sim_temp["chamber"], 2)},
            "print_stats": {"state": "standby", "filename": "", "print_duration": 0.0},
            "display_status": {"progress": 0.0},
            "extruder": {"temperature": self._sim_temp["ext"], "target": self._sim_target["ext"]},
            "heater_bed": {"temperature": self._sim_temp["bed"], "target": self._sim_target["bed"]},
            "fan": {"speed": self._sim_fan / 255.0},
            "webhooks": {"state": "ready", "state_message": "Demo mode: Moonraker or MCU not connected"},
        }

    def _demo_gcode(self, script):
        for line in script.splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            self._demo_log.append(f"> {line.strip()}")
            self._demo_log.append("ok")
            cmd = parts[0].upper()
            value = _param(parts, "S")
            if cmd == "M104" and value is not None:
                self._sim_target["ext"] = value
            elif cmd == "M140" and value is not None:
                self._sim_target["bed"] = value
            elif cmd == "M106":
                self._sim_fan = int(value or 0)
            elif cmd == "M107":
                self._sim_fan = 0

    # ---- actions (called from worker threads) -------------------------
    def gcode(self, script):
        if self.online:
            return self.client.gcode(script)
        self._demo_gcode(script)
        return "demo"

    def thumbnail_bytes(self, filename):
        """PNG bytes of the largest print thumbnail for a G-code file, or None."""
        if not self.online or not filename:
            return None
        try:
            meta = self.client.get("/server/files/metadata",
                                   {"filename": filename})["result"]
            thumbs = meta.get("thumbnails") or []
            if not thumbs:
                return None
            best = max(thumbs, key=lambda t: t.get("width", 0))
            rel = posixpath.normpath(posixpath.join(posixpath.dirname(filename),
                                                    best["relative_path"]))
            return self.client.get_bytes("/server/files/gcodes/" + urllib.parse.quote(rel))
        except Exception:
            return None

    def console_lines(self, count=60):
        """Console history for the Console screen. Never raises, so polling cannot spam errors."""
        if self.online:
            try:
                return [m.get("message", "") for m in self.client.gcode_store(count)]
            except Exception:
                return []
        return list(self._demo_log)[-count:]

    def print_action(self, action):
        if self.online:
            return self.client.print_action(action)
        raise RuntimeError("No print running (demo mode)")

    def emergency_stop(self):
        if self.online:
            return self.client.emergency_stop()
        raise RuntimeError("Emergency stop needs Klipper (demo mode)")

    def restart_klipper(self):
        if self.online:
            try:
                self.client.restart_service("klipper")
                return "ok"
            except Exception:
                pass  # fall back to systemd below
        return system_command(["/usr/bin/systemctl", "restart", "klipper"])

    def firmware_restart(self):
        if self.online:
            return self.client.firmware_restart()
        return self.restart_klipper()

    def restart_moonraker(self):
        return system_command(["/usr/bin/systemctl", "restart", "moonraker"])

    def reboot(self):
        return system_command(["/usr/bin/systemctl", "reboot"])

    def shutdown(self):
        return system_command(["/usr/bin/systemctl", "poweroff"])

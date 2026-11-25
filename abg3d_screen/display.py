"""Screen power for the touchscreen.

On X11 the screen is blanked with DPMS (`xset dpms force off`). Panels that do not
support DPMS, such as many DSI displays, fall back to the kernel backlight:
/sys/class/backlight/*/bl_power, where 4 means powered down and 0 means on.
Writing bl_power needs root. When the file is not writable, the write goes through
`sudo -n tee`, which install.sh allows for exactly that path.
"""
import glob
import os
import subprocess

BACKLIGHT_GLOB = "/sys/class/backlight/*/bl_power"
TEE = "/usr/bin/tee"
BL_OFF, BL_ON = 4, 0


def _run(cmd, stdin=None, timeout=5):
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def dpms_available():
    if not os.environ.get("DISPLAY"):
        return False
    res = _run(["xset", "q"])
    return bool(res and res.returncode == 0 and "DPMS is" in res.stdout)


def _write_backlight(value):
    wrote = False
    for path in sorted(glob.glob(BACKLIGHT_GLOB)):
        if os.access(path, os.W_OK):
            try:
                with open(path, "w") as fh:
                    fh.write(f"{value}\n")
                wrote = True
                continue
            except OSError:
                pass
        res = _run(["sudo", "-n", TEE, path], stdin=f"{value}\n")
        wrote = wrote or bool(res and res.returncode == 0)
    return wrote


def screen_off():
    if dpms_available():
        res = _run(["xset", "dpms", "force", "off"])
        if res and res.returncode == 0:
            return True
    return _write_backlight(BL_OFF)


def screen_on():
    if dpms_available():
        _run(["xset", "dpms", "force", "on"])
        _run(["xset", "s", "reset"])
    _write_backlight(BL_ON)

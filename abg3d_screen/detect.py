"""Auto-detection of Klipper, Moonraker, MCU and MMU installations. No user names are hard-coded."""
import re
import socket
import subprocess
from pathlib import Path

HOME = Path.home()
KLIPPER_CANDIDATES = [HOME / "klipper", Path("/home/pi/klipper"), Path("/opt/klipper")]
CONFIG_CANDIDATES = [HOME / "printer_data" / "config", Path("/home/pi/printer_data/config"),
                     HOME / "klipper_config"]
MMU_NAMES = {
    "happy_hare": "Happy Hare",
    "boxturtle_afc": "Box Turtle / AFC",
    "ktc": "KTC",
    "none": "None detected",
}


def find_klipper_dir():
    for path in KLIPPER_CANDIDATES:
        if (path / "klippy" / "klippy.py").is_file():
            return path
    return None


def find_config_dir():
    for path in CONFIG_CANDIDATES:
        if (path / "printer.cfg").is_file():
            return path
    return None


def service_state(name):
    try:
        res = subprocess.run(["systemctl", "is-active", name], capture_output=True,
                             text=True, timeout=3)
        return res.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def os_pretty_name():
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "unknown"


def local_ip():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("10.255.255.255", 1))  # no packets are sent; this only selects a route
        return sock.getsockname()[0]
    except OSError:
        return "no network"
    finally:
        if sock is not None:
            sock.close()


def mcu_present(objects):
    return any(o == "mcu" or o.startswith("mcu ") for o in objects)


def _config_scan(config_dir, limit=400_000):
    """Return (lower-cased text of all .cfg files, set of their lower-cased file names)."""
    if not config_dir or not config_dir.is_dir():
        return "", set()
    chunks, names, total = [], set(), 0
    for path in sorted(config_dir.rglob("*.cfg")):
        names.add(path.name.lower())
        if total > limit:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        chunks.append(text)
        total += len(text)
    return "\n".join(chunks).lower(), names


TEMP_OBJECT_RE = re.compile(
    r"^(extruder\d*|heater_bed|heater_generic \S.*|temperature_sensor \S.*"
    r"|temperature_fan \S.*|temperature_probe \S.*)$")


def temp_object_names(objects):
    """Every Moonraker object that reports a temperature (nozzles, bed, sensors, fans)."""
    return sorted(o for o in objects if TEMP_OBJECT_RE.match(o))


LED_OBJECT_RE = re.compile(r"^(led|neopixel|dotstar|pca9533|pca9632) (\S+)$")


def led_names(objects):
    """LED names usable with SET_LED, e.g. 'neopixel chamber_led' -> 'chamber_led'."""
    names = set()
    for obj in objects:
        match = LED_OBJECT_RE.match(obj)
        if match:
            names.add(match.group(2))
    return sorted(names)


def detect_printer_features(config_dir, objects):
    """Optional gantry tools. Only offered when the printer actually defines them."""
    cfg, _ = _config_scan(config_dir)
    objs = [o.lower() for o in objects]
    return {
        "ztilt": "[z_tilt]" in cfg or "z_tilt" in objs,
        "qgl": "[quad_gantry_level]" in cfg or "quad_gantry_level" in objs,
    }


def detect_mmu(klipper_dir, config_dir, objects):
    """Return 'happy_hare', 'boxturtle_afc', 'ktc' or 'none'.

    Each MMU is only reported when at least one reliable marker is present:
      Happy Hare   mmu.py / mmu_*.py in Klipper extras, an 'mmu' Moonraker object,
                   a [mmu...] config section, or mmu_vars.cfg / mmu_hardware.cfg.
      Box Turtle   the 'AFC' Moonraker object, afc*.py extras, an [AFC] section,
                   AFC*.cfg files, or an AFC/ config folder (AFC-Klipper-Add-On).
      KTC          ktc*.py extras or a [ktc...] section.
    """
    extras = klipper_dir / "klippy" / "extras" if klipper_dir else None
    names = {p.name.lower() for p in extras.glob("*.py")} if extras and extras.is_dir() else set()
    objs = [o.lower() for o in objects]
    cfg, cfg_files = _config_scan(config_dir)

    happy_hare = (
        any(n == "mmu.py" or n.startswith("mmu_") for n in names)
        or any(o == "mmu" or o.startswith("mmu_") for o in objs)
        or "[mmu" in cfg
        or "mmu_vars.cfg" in cfg_files or "mmu_hardware.cfg" in cfg_files
    )
    if happy_hare:
        return "happy_hare"

    afc_folder = bool(config_dir and (config_dir / "AFC").is_dir())
    afc = (
        any(o == "afc" or o.startswith("afc_") or o.startswith("afc ") for o in objs)
        or any(n.startswith("afc") for n in names)
        or "[afc" in cfg
        or any(f.startswith("afc") for f in cfg_files)
        or afc_folder
    )
    if afc:
        return "boxturtle_afc"

    if any(n.startswith("ktc") for n in names) or "[ktc" in cfg:
        return "ktc"
    return "none"

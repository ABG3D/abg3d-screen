"""Network status and Wi-Fi through NetworkManager (nmcli).

Status works everywhere. Scanning and connecting need nmcli and NetworkManager; when
nmcli is missing the functions say so instead of failing.
"""
import shutil
import subprocess

from .detect import local_ip


def _run(cmd, timeout=20):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def _fields(line):
    """Split an nmcli -t line on unescaped colons."""
    parts, cur, escaped = [], "", False
    for ch in line:
        if escaped:
            cur, escaped = cur + ch, False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def has_nmcli():
    return shutil.which("nmcli") is not None


def status():
    info = {"ip": local_ip(), "ssid": "", "iface": "", "nmcli": has_nmcli()}
    if info["nmcli"]:
        _code, out, _err = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
        for line in out.splitlines():
            f = _fields(line)
            if len(f) >= 4 and f[1] == "wifi" and f[2] == "connected":
                info["iface"], info["ssid"] = f[0], f[3]
    return info


def scan():
    if not has_nmcli():
        return []
    _code, out, _err = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY",
                             "dev", "wifi", "list", "--rescan", "auto"], timeout=30)
    nets = {}
    for line in out.splitlines():
        f = _fields(line)
        if len(f) < 3 or not f[0]:
            continue
        ssid = f[0]
        signal = int(f[1]) if f[1].isdigit() else 0
        secured = f[2].strip() not in ("", "--")
        if ssid not in nets or signal > nets[ssid]["signal"]:
            nets[ssid] = {"ssid": ssid, "signal": signal, "secured": secured}
    return sorted(nets.values(), key=lambda n: -n["signal"])


def connect(ssid, password=""):
    """Return (ok, message). The password is passed to nmcli and never stored."""
    if not has_nmcli():
        return False, "nmcli not found. Install NetworkManager to manage Wi-Fi here."
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    code, out, err = _run(cmd, timeout=60)
    text = (out if code == 0 else (err or out or "connection failed")).splitlines()
    message = text[-1] if text else "done"
    return code == 0, message[:120]

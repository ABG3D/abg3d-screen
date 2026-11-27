"""IP status and Wi-Fi scan/connect through NetworkManager's `nmcli` (non-blocking)."""
import shutil
import socket
import subprocess
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib  # noqa: E402


def local_ips():
    ips = []
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2).stdout
        ips = [i for i in out.split() if ":" not in i]
    except (OSError, subprocess.SubprocessError):
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                ips = [ip]
        except OSError:
            pass
    return ips


def has_nmcli():
    return shutil.which("nmcli") is not None


def run_async(args, cb, timeout=40):
    """Run a command on a worker thread; cb(returncode, stdout, stderr) on the GTK loop."""
    def work():
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            res = (r.returncode, r.stdout, r.stderr)
        except subprocess.TimeoutExpired:
            res = (124, "", "timed out")
        except OSError as e:
            res = (127, "", str(e))
        GLib.idle_add(lambda: cb(*res) and False)
    threading.Thread(target=work, daemon=True).start()


def split_terse(line):
    """Split an `nmcli -t` line on unescaped ':'."""
    out, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def wifi_scan(cb):
    def done(rc, out, err):
        if rc != 0:
            cb(None, (err or out).strip() or "nmcli failed (%d)" % rc)
            return
        nets = {}
        for line in out.splitlines():
            f = split_terse(line)
            if len(f) < 4 or not f[1]:
                continue
            ssid = f[1]
            try:
                sig = int(f[2] or 0)
            except ValueError:
                sig = 0
            cur = nets.get(ssid)
            if not cur or sig > cur["signal"] or f[0] == "*":
                nets[ssid] = {"ssid": ssid, "signal": sig, "security": f[3],
                              "active": f[0] == "*" or (cur or {}).get("active", False)}
        cb(sorted(nets.values(), key=lambda n: (not n["active"], -n["signal"])), None)
    run_async(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"],
              done)


def wifi_connect(ssid, password, cb):
    args = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    run_async(args, lambda rc, out, err: cb(rc == 0, (out if rc == 0 else err or out).strip()), timeout=45)


def wifi_disconnect(ssid, cb):
    run_async(["nmcli", "connection", "down", "id", ssid],
              lambda rc, out, err: cb(rc == 0, (out if rc == 0 else err or out).strip()))


def device_status(cb):
    def done(rc, out, err):
        devs = []
        if rc == 0:
            for line in out.splitlines():
                f = split_terse(line)
                if len(f) >= 4 and f[1] in ("wifi", "ethernet"):
                    devs.append({"device": f[0], "type": f[1], "state": f[2], "connection": f[3]})
        cb(devs)
    run_async(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], done, timeout=10)

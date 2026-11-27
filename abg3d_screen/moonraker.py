"""Moonraker client for abg3d-screen.

JSON-RPC 2.0 over WebSocket (the `websockets` sync client when installed in the
venv, else a built-in minimal RFC 6455 client) + REST over urllib.
Network I/O runs on small daemon threads; every callback and event is
marshalled onto the GTK main loop with GLib.idle_add, so UI code never
touches sockets and never blocks.
"""
import base64
import json
import logging
import os
import queue
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from gi.repository import GLib

try:  # websockets >= 12 ships a thread-friendly sync client
    from websockets.sync.client import connect as _ws_connect
except Exception:  # pragma: no cover - fallback keeps zero-dependency operation
    _ws_connect = None

log = logging.getLogger("abg3d.moonraker")

FIXED_OBJECTS = {
    "webhooks": None,
    "print_stats": None,
    "display_status": ["progress", "message"],
    "virtual_sdcard": ["progress", "is_active"],
    "toolhead": ["homed_axes", "position", "extruder"],
    "gcode_move": ["gcode_position", "homing_origin", "speed_factor",
                   "extrude_factor", "absolute_coordinates"],
    "idle_timeout": ["state"],
    "fan": ["speed"],
    "heater_bed": ["temperature", "target", "power"],
}
KIND_FIELDS = {
    "heater_generic": ["temperature", "target", "power"],
    "temperature_sensor": ["temperature"],
    "temperature_fan": ["temperature", "target", "speed"],
    "fan_generic": ["speed"],
    "heater_fan": ["speed"],
    "controller_fan": ["speed"],
    "output_pin": ["value"],
    "led": ["color_data"],
    "neopixel": ["color_data"],
    "dotstar": ["color_data"],
    "pca9533": ["color_data"],
    "pca9632": ["color_data"],
    "filament_switch_sensor": ["filament_detected", "enabled"],
    "filament_motion_sensor": ["filament_detected", "enabled"],
}
PROBE_OBJECTS = ("probe", "bltouch", "smart_effector", "probe_eddy_current",
                 "beacon", "cartographer", "scanner")


class WSError(Exception):
    pass


class WebSocket:
    """Minimal blocking RFC 6455 client (text frames, ping/pong, close)."""

    def __init__(self, host, port, path, headers=None, timeout=8):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.wlock = threading.Lock()
        self._rbuf = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        req = ["GET %s HTTP/1.1" % path, "Host: %s:%d" % (host, port),
               "Upgrade: websocket", "Connection: Upgrade",
               "Sec-WebSocket-Key: " + key, "Sec-WebSocket-Version: 13"]
        for k, v in (headers or {}).items():
            req.append("%s: %s" % (k, v))
        self.sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSError("handshake: connection closed")
            buf += chunk
            if len(buf) > 32768:
                raise WSError("handshake: response too large")
        head, _, rest = bytes(buf).partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].split()
        if len(status) < 2 or status[1] != b"101":
            raise WSError("handshake failed: %s" % head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self._rbuf += rest
        self.sock.settimeout(None)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    def _exact(self, n):
        while len(self._rbuf) < n:
            chunk = self.sock.recv(max(65536, n - len(self._rbuf)))
            if not chunk:
                raise WSError("connection lost")
            self._rbuf += chunk
        out = bytes(self._rbuf[:n])
        del self._rbuf[:n]
        return out

    def recv(self):
        msg = bytearray()
        mop = 1
        while True:
            hdr = self._exact(2)
            b1, b2 = hdr[0], hdr[1]
            fin, op, ln = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._exact(8))[0]
            mask = self._exact(4) if b2 & 0x80 else None
            data = self._exact(ln) if ln else b""
            if mask and ln:
                m = (mask * (ln // 4 + 1))[:ln]
                data = (int.from_bytes(data, "big") ^ int.from_bytes(m, "big")).to_bytes(ln, "big")
            if op == 0x8:
                self.close()
                raise WSError("closed by server")
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            if op in (0x1, 0x2):
                mop = op
                msg = bytearray(data)
            elif op == 0x0:
                msg += data
            if fin:
                return msg.decode("utf-8", "replace") if mop == 1 else bytes(msg)

    def _send(self, op, payload):
        n = len(payload)
        mask = os.urandom(4)
        hdr = bytearray([0x80 | op])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack("!H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack("!Q", n)
        if n:
            m = (mask * (n // 4 + 1))[:n]
            payload = (int.from_bytes(payload, "big") ^ int.from_bytes(m, "big")).to_bytes(n, "big")
        with self.wlock:
            self.sock.sendall(bytes(hdr) + mask + payload)

    def send(self, text):
        self._send(0x1, text.encode("utf-8"))

    def close(self):
        try:
            with self.wlock:
                self.sock.sendall(b"\x88\x80" + os.urandom(4))
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class LibWebSocket:
    """Adapter over websockets.sync.client with the same recv/send/close API."""

    def __init__(self, host, port, path, headers=None, timeout=8):
        self.conn = _ws_connect("ws://%s:%d%s" % (host, port, path), additional_headers=headers or None,
                                open_timeout=timeout, compression=None, max_size=32 * 2 ** 20,
                                ping_interval=20, ping_timeout=20)

    def recv(self):
        return self.conn.recv()

    def send(self, text):
        self.conn.send(text)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


MMU_PREFIXES = ("AFC", "mmu")


def is_mmu_object(name):
    kind = name.split(" ", 1)[0]
    return kind == "AFC" or kind.startswith("AFC_") or kind == "mmu" or kind.startswith("mmu_")


class Moonraker:
    """JSON-RPC over WebSocket + REST helper with event dispatch.

    Events (all emitted on the GTK main loop):
      connection(bool)       websocket up / down
      klippy(state, message) klippy_state changed (ready/startup/shutdown/error/disconnected)
      ready()                printer objects discovered + subscribed, self.data populated
      status(changes)        notify_status_update (already merged into self.data)
      gcode_response(line)
      filelist_changed(info)
      temp_store(result)
      mainsail(dict)
      error(message)
    """

    def __init__(self, host="127.0.0.1", port=7125, api_key="", version="1.0"):
        self.host, self.port, self.api_key, self.version = host, int(port), api_key, version
        self.ws = None
        self.connected = False
        self.klippy_state = "disconnected"
        self.klippy_message = ""
        self.data = {}
        self.objects = []
        self.config = {"pwm": {}, "probe": None, "kinematics": ""}
        self.mainsail = {}
        self.printer_info = {}
        self.server_info = {}
        self._id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._listeners = {}
        self._running = False
        self._retry_src = None
        self._q = queue.Queue()
        self._tq = queue.Queue()
        for qq, n in ((self._q, 2), (self._tq, 1)):
            for _ in range(n):
                threading.Thread(target=self._http_worker, args=(qq,), daemon=True).start()

    # ---------------------------------------------------------------- events
    def on(self, event, cb):
        self._listeners.setdefault(event, []).append(cb)

    def emit(self, event, *args):
        for cb in list(self._listeners.get(event, ())):
            try:
                cb(*args)
            except Exception:
                log.exception("listener for %s failed", event)

    def _idle(self, fn, *args):
        def run():
            try:
                fn(*args)
            except Exception:
                log.exception("idle callback failed")
            return False
        GLib.idle_add(run)

    # ------------------------------------------------------------ websocket
    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="moonraker-ws").start()

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

    def _headers(self):
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    def _loop(self):
        backoff = 1.0
        while self._running:
            try:
                cls = LibWebSocket if _ws_connect else WebSocket
                self.ws = cls(self.host, self.port, "/websocket", self._headers())
            except Exception as e:
                log.debug("connect failed: %s", e)
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 5.0)
                continue
            backoff = 1.0
            self.connected = True
            log.info("connected to moonraker %s:%d", self.host, self.port)
            self._idle(self._on_open)
            try:
                while self._running:
                    raw = self.ws.recv()
                    if isinstance(raw, str):
                        self._handle(raw)
            except Exception as e:
                log.warning("websocket closed: %s", e)
            self.connected = False
            try:
                self.ws.close()
            except Exception:
                pass
            with self._lock:
                pend, self._pending = self._pending, {}
            for cb in pend.values():
                self._idle(cb, None, {"message": "Moonraker disconnected"})
            self._idle(self._on_close)
            time.sleep(1.0)

    def _handle(self, raw):
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if "id" in msg and ("result" in msg or "error" in msg):
            with self._lock:
                cb = self._pending.pop(msg["id"], None)
            if cb:
                err = msg.get("error")
                if err is not None and not isinstance(err, dict):
                    err = {"message": str(err)}
                self._idle(cb, msg.get("result"), err)
        elif "method" in msg:
            self._idle(self._notify, msg["method"], msg.get("params") or [])

    def call(self, method, params=None, cb=None):
        if not self.connected or not self.ws:
            if cb:
                self._idle(cb, None, {"message": "Not connected to Moonraker"})
            else:
                self._idle(self.emit, "error", "Moonraker offline \u2014 %s not sent" % method)
            return
        with self._lock:
            self._id += 1
            rid = self._id
            if cb:
                self._pending[rid] = cb
        payload = json.dumps({"jsonrpc": "2.0", "method": method,
                              "params": params or {}, "id": rid})
        try:
            self.ws.send(payload)
        except Exception as e:
            with self._lock:
                self._pending.pop(rid, None)
            if cb:
                self._idle(cb, None, {"message": str(e)})

    def gcode(self, script, cb=None):
        log.info("gcode: %s", script.replace("\n", " | "))

        def done(res, err):
            if err:
                self.emit("error", err.get("message", "G-code error"))
            if cb:
                cb(res, err)
        self.call("printer.gcode.script", {"script": script}, done)

    # ------------------------------------------------------------------ REST
    def http(self, method, path, params=None, body=None, cb=None, raw=False, timeout=15, q="main"):
        (self._tq if q == "thumb" else self._q).put((method, path, params, body, cb, raw, timeout))

    def url(self, path):
        return "http://%s:%d%s" % (self.host, self.port, path)

    def _http_worker(self, qq):
        while True:
            method, path, params, body, cb, raw, timeout = qq.get()
            url = self.url(path)
            if params:
                url += "?" + urllib.parse.urlencode(params)
            headers = dict(self._headers())
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            elif method in ("POST", "PUT"):
                data = b""
            res = err = None
            try:
                req = urllib.request.Request(url, data=data, method=method, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    payload = r.read()
                res = payload if raw else json.loads(payload or b"{}").get("result")
            except urllib.error.HTTPError as e:
                msg = "HTTP %d" % e.code
                try:
                    msg = json.loads(e.read()).get("error", {}).get("message", msg)
                except Exception:
                    pass
                err = {"message": msg}
            except Exception as e:
                err = {"message": str(e)}
            if cb:
                self._idle(cb, res, err)

    # ------------------------------------------------------------ lifecycle
    def _on_open(self):
        self.emit("connection", True)
        self.call("server.connection.identify", {
            "client_name": "abg3d-screen", "version": self.version,
            "type": "display", "url": "https://github.com/abg3d/abg3d-screen"},
            lambda r, e: self._query_server())

    def _on_close(self):
        self._set_klippy("disconnected", "Moonraker connection lost")
        self.emit("connection", False)

    def _set_klippy(self, state, message=""):
        changed = (state, message) != (self.klippy_state, self.klippy_message)
        self.klippy_state, self.klippy_message = state, message
        if changed:
            self.emit("klippy", state, message)

    def _schedule_retry(self, secs=2):
        if self._retry_src:
            return

        def fire():
            self._retry_src = None
            self._query_server()
            return False
        self._retry_src = GLib.timeout_add_seconds(secs, fire)

    def _query_server(self):
        if not self.connected:
            return
        self.call("server.info", None, self._on_server_info)

    def _on_server_info(self, res, err):
        if err or not res:
            self._schedule_retry()
            return
        self.server_info = res
        state = res.get("klippy_state", "disconnected")
        if state == "ready":
            self._init_printer()
        else:
            self.call("printer.info", None, lambda r, e: self._set_klippy(
                state, (r or {}).get("state_message", "") if not e else
                "Klipper is %s" % state))
            self._schedule_retry()

    def _init_printer(self):
        self.call("printer.info", None, self._on_printer_info)

    def _on_printer_info(self, res, err):
        if err or not res:
            self._schedule_retry()
            return
        self.printer_info = res
        if res.get("state") != "ready":
            self._set_klippy(res.get("state", "error"), res.get("state_message", ""))
            self._schedule_retry()
            return
        self.call("printer.objects.list", None, self._on_objects)

    def _on_objects(self, res, err):
        if err or not res:
            self._schedule_retry()
            return
        self.objects = res.get("objects", [])
        self.call("printer.objects.query", {"objects": {"configfile": ["settings"]}}, self._on_config)

    def _on_config(self, res, err):
        settings = {}
        if res and not err:
            settings = res.get("status", {}).get("configfile", {}).get("settings", {})
        pwm = {}
        for name, sect in settings.items():
            if name.startswith("output_pin "):
                pwm[name] = bool(sect.get("pwm", False))
        probe = next((o for o in PROBE_OBJECTS if o in settings or o in self.objects), None)
        self.config = {"pwm": pwm, "probe": probe,
                       "kinematics": settings.get("printer", {}).get("kinematics", "")}
        settings.clear()
        subs = {}
        for name in self.objects:
            if name in FIXED_OBJECTS:
                subs[name] = FIXED_OBJECTS[name]
            elif self._is_extruder(name):
                subs[name] = ["temperature", "target", "power", "can_extrude"]
            elif is_mmu_object(name):
                subs[name] = None
            else:
                kind = name.split(" ", 1)[0]
                if kind in KIND_FIELDS and " " in name:
                    subs[name] = KIND_FIELDS[kind]
        self.call("printer.objects.subscribe", {"objects": subs}, self._on_subscribed)

    def _on_subscribed(self, res, err):
        if err or not res:
            self._schedule_retry()
            return
        self.data = {}
        self._merge(res.get("status", {}))
        self._set_klippy("ready", "")
        self.emit("ready")
        self.emit("status", self.data)
        self.call("server.temperature_store", {"include_monitors": False},
                  lambda r, e: r and self.emit("temp_store", r))
        self.load_mainsail()

    def load_mainsail(self, cb=None):
        """Mainsail DB namespace over REST (independent of the websocket / Klipper state)."""
        def done(res, err):
            if err:
                # a missing "mainsail" namespace is normal on non-Mainsail setups: only report on request
                log.info("mainsail database unavailable: %s", err.get("message"))
                if cb:
                    self.emit("error", "Mainsail database: %s" % err.get("message", "unavailable"))
                return
            val = (res or {}).get("value", {})
            self.mainsail = val if isinstance(val, dict) else {}
            self.emit("mainsail", self.mainsail)
            if cb:
                cb(self.mainsail)
        self.http("GET", "/server/database/item", {"namespace": "mainsail"}, cb=done)

    def _merge(self, changes):
        for obj, fields in changes.items():
            if isinstance(fields, dict):
                self.data.setdefault(obj, {}).update(fields)

    def _notify(self, method, params):
        if method == "notify_status_update":
            if params and isinstance(params[0], dict):
                self._merge(params[0])
                self.emit("status", params[0])
                ws = params[0].get("webhooks")
                if ws and "state" in ws and ws["state"] != "ready":
                    self._set_klippy(ws["state"], ws.get("state_message", ""))
        elif method == "notify_gcode_response":
            for p in params:
                self.emit("gcode_response", str(p))
        elif method == "notify_klippy_ready":
            self._init_printer()
        elif method == "notify_klippy_shutdown":
            self._set_klippy("shutdown", "Klipper shutdown")
            self._schedule_retry(3)
        elif method == "notify_klippy_disconnected":
            self._set_klippy("disconnected", "Klipper disconnected")
            self._schedule_retry(3)
        elif method == "notify_filelist_changed":
            self.emit("filelist_changed", params[0] if params else {})
        elif method == "notify_active_spool_set":
            pass

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _is_extruder(name):
        return name.startswith("extruder") and " " not in name and name[8:].isdigit() or name == "extruder"

    def heaters(self):
        out = [o for o in self.objects if self._is_extruder(o)]
        out.sort()
        if "heater_bed" in self.objects:
            out.append("heater_bed")
        out += sorted(o for o in self.objects if o.startswith("heater_generic "))
        return out

    def temp_fans(self):
        return sorted(o for o in self.objects if o.startswith("temperature_fan "))

    def sensors(self):
        return sorted(o for o in self.objects if o.startswith("temperature_sensor "))

    def macros(self):
        return sorted((o[12:] for o in self.objects if o.startswith("gcode_macro ")), key=str.lower)

    def state(self, obj, field, default=None):
        v = self.data.get(obj, {}).get(field)
        return default if v is None else v

    def mcu_online(self):
        return self.connected and self.klippy_state == "ready" and any(
            o == "mcu" or o.startswith("mcu ") for o in self.objects)

    def mmu_driver(self):
        """'afc' (BoxTurtle AFC), 'happy_hare' or None from the Klipper object list."""
        if self.klippy_state != "ready":
            return None
        if any(o == "AFC" or o.startswith("AFC_stepper") or o.startswith("AFC_lane") for o in self.objects):
            return "afc"
        if "mmu" in self.objects:
            return "happy_hare"
        return None

    def fetch_config(self, cb):
        """Full configfile settings (only fetched on demand, e.g. by the MMU panel shim)."""
        self.call("printer.objects.query", {"objects": {"configfile": ["settings", "config"]}},
                  lambda r, e: cb({} if e or not r else r.get("status", {}).get("configfile", {})))

    def print_state(self):
        return self.state("print_stats", "state", "standby")

    def is_printing(self):
        return self.print_state() in ("printing", "paused")

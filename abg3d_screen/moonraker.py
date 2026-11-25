"""Minimal Moonraker HTTP client using only the standard library (keeps the Pi 3B+ light)."""
import json
import urllib.error
import urllib.parse
import urllib.request


class MoonrakerError(RuntimeError):
    pass


class MoonrakerClient:
    def __init__(self, base_url, timeout=2.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, params=None, body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data, headers = None, {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode() or "{}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="ignore")
            try:
                message = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = f"HTTP {exc.code}"
            raise MoonrakerError(message) from None
        return json.loads(raw)

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def get_bytes(self, path):
        req = urllib.request.Request(self.base_url + path, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def post(self, path, body=None, params=None):
        return self._request("POST", path, params=params, body=body)

    def server_info(self):
        return self.get("/server/info")["result"]

    def list_objects(self):
        return self.get("/printer/objects/list")["result"]["objects"]

    def query(self, objects):
        path = "/printer/objects/query?" + "&".join(urllib.parse.quote(o, safe="") for o in objects)
        return self.get(path)["result"]["status"]

    def gcode(self, script):
        return self.post("/printer/gcode/script", {"script": script})

    def print_action(self, action):
        return self.post(f"/printer/print/{action}")

    def emergency_stop(self):
        return self.post("/printer/emergency_stop")

    def firmware_restart(self):
        return self.post("/printer/firmware_restart")

    def gcode_store(self, count=60):
        """Recent console lines (commands and responses) kept by Moonraker."""
        return self.get("/server/gcode_store", {"count": count})["result"]["gcode_store"]

    def restart_service(self, name):
        return self.post("/machine/services/restart", params={"service": name})

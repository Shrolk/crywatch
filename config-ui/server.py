#!/usr/bin/env python3
"""config-ui — small web UI to edit go2rtc camera streams + MQTT settings.

FORK (Pierre): before this, adding/renaming a camera meant hand-editing
go2rtc.yaml (streams) AND .env (CAMS) and keeping the two in sync yourself.
This serves one page that edits both at once, plus the cry-detector's MQTT
settings, and writes the same files the rest of the stack already reads —
it does NOT restart any container itself (see README: run `docker compose
up -d` after saving).

Auth: HTTP Basic, credentials from CONFIG_UI_USER / CONFIG_UI_PASSWORD.
Both are required — the process refuses to start without them, since this
page reads and writes camera RTSP credentials and your MQTT password.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from ruamel.yaml import YAML

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("CONFIG_UI_HOST", "0.0.0.0")
PORT = int(os.environ.get("CONFIG_UI_PORT", "8090"))
USER = os.environ.get("CONFIG_UI_USER", "")
PASSWORD = os.environ.get("CONFIG_UI_PASSWORD", "")

GO2RTC_PATH = os.environ.get("GO2RTC_YAML_PATH", "/data/go2rtc.yaml")
GO2RTC_EXAMPLE_PATH = os.environ.get("GO2RTC_EXAMPLE_PATH", "/data/go2rtc.example.yaml")
ENV_PATH = os.environ.get("ENV_PATH", "/data/.env")
ENV_EXAMPLE_PATH = os.environ.get("ENV_EXAMPLE_PATH", "/data/.env.example")

if not USER or not PASSWORD:
    print("[config-ui] CONFIG_UI_USER and CONFIG_UI_PASSWORD must both be set — "
          "refusing to start unauthenticated (this page handles camera and MQTT "
          "passwords).", file=sys.stderr)
    sys.exit(1)

NAME_RE = re.compile(r"^[a-z0-9_]+$")
yaml = YAML()
yaml.preserve_quotes = True


# ---- go2rtc.yaml (streams) -------------------------------------------------

def load_go2rtc():
    path = GO2RTC_PATH if os.path.exists(GO2RTC_PATH) else GO2RTC_EXAMPLE_PATH
    with open(path) as f:
        return yaml.load(f) or {}


def stream_url(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def cameras_from_go2rtc(data):
    streams = data.get("streams") or {}
    bases, hd_only = {}, {}
    for name, v in streams.items():
        if name.endswith("_hd"):
            hd_only[name[:-3]] = stream_url(v)
        else:
            bases[name] = stream_url(v)
    cams = [{"name": n, "sub_url": url, "hd_url": hd_only.pop(n, "")}
            for n, url in bases.items()]
    cams += [{"name": n, "sub_url": "", "hd_url": url} for n, url in hd_only.items()]
    return cams


def write_go2rtc(cameras):
    data = load_go2rtc()
    streams = data.get("streams")
    if streams is None:
        from ruamel.yaml.comments import CommentedMap
        streams = CommentedMap()
    streams.clear()
    for cam in cameras:
        streams[cam["name"]] = [cam["sub_url"]]
        if cam.get("hd_url"):
            streams[f"{cam['name']}_hd"] = [cam["hd_url"]]
    data["streams"] = streams
    os.makedirs(os.path.dirname(GO2RTC_PATH) or ".", exist_ok=True)
    with open(GO2RTC_PATH, "w") as f:
        yaml.dump(data, f)


# ---- .env (CAMS + MQTT_*) ---------------------------------------------------

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def read_env():
    path = ENV_PATH if os.path.exists(ENV_PATH) else ENV_EXAMPLE_PATH
    values = {}
    if os.path.exists(path):
        for line in open(path):
            m = KEY_RE.match(line.strip())
            if m:
                values[m.group(1)] = m.group(2)
    return values


def update_env(updates):
    if not os.path.exists(ENV_PATH):
        base = open(ENV_EXAMPLE_PATH).read() if os.path.exists(ENV_EXAMPLE_PATH) else ""
        open(ENV_PATH, "w").write(base)
    lines = open(ENV_PATH).read().splitlines(keepends=True)
    seen = set()
    out = []
    for line in lines:
        m = KEY_RE.match(line.strip())
        if m and m.group(1) in updates:
            key = m.group(1)
            out.append(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            out.append(line)
    missing = {k: v for k, v in updates.items() if k not in seen}
    if missing:
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        out.append("\n# --- config-ui ---\n")
        out.extend(f"{k}={v}\n" for k, v in missing.items())
    open(ENV_PATH, "w").writelines(out)


def cams_var_to_labels(cams_value):
    labels = {}
    for pair in (cams_value or "").split(","):
        name, _, label = pair.partition("=")
        name = name.strip()
        if name:
            labels[name] = label.strip() or name
    return labels


def labels_to_cams_var(cameras):
    return ",".join(f"{c['name']}={c['label']}" for c in cameras)


# ---- combined config --------------------------------------------------------

def get_config():
    env = read_env()
    labels = cams_var_to_labels(env.get("CAMS", ""))
    cameras = cameras_from_go2rtc(load_go2rtc())
    for cam in cameras:
        cam["label"] = labels.get(cam["name"], cam["name"])
    mqtt_password = env.get("MQTT_PASSWORD", "")
    return {
        "cameras": cameras,
        "mqtt": {
            "host": env.get("MQTT_HOST", ""),
            "port": env.get("MQTT_PORT", "1883"),
            "user": env.get("MQTT_USER", ""),
            "has_password": bool(mqtt_password),
            "topic_base": env.get("MQTT_TOPIC_BASE", "crywatch"),
            "discovery": env.get("MQTT_DISCOVERY", "1") == "1",
            "state_timeout": env.get("CRY_STATE_TIMEOUT", "60"),
        },
    }


def validate_cameras(cameras):
    if not isinstance(cameras, list) or not cameras:
        return "au moins une caméra est requise"
    seen = set()
    for cam in cameras:
        name = (cam.get("name") or "").strip()
        if not NAME_RE.match(name):
            return f"nom de caméra invalide : '{name}' (minuscules/chiffres/_ uniquement)"
        if name in seen:
            return f"nom de caméra en double : '{name}'"
        seen.add(name)
        if not (cam.get("sub_url") or "").startswith("rtsp://"):
            return f"'{name}' : l'URL RTSP doit commencer par rtsp://"
        if cam.get("hd_url") and not cam["hd_url"].startswith("rtsp://"):
            return f"'{name}' : l'URL RTSP HD doit commencer par rtsp://"
        if not (cam.get("label") or "").strip():
            return f"'{name}' : le libellé ne peut pas être vide"
    return None


def validate_mqtt(m):
    try:
        port = int(m.get("port", 0))
        if not (1 <= port <= 65535):
            raise ValueError
    except (TypeError, ValueError):
        return "port MQTT invalide"
    try:
        if float(m.get("state_timeout", 0)) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return "CRY_STATE_TIMEOUT doit être un nombre positif"
    return None


# ---- HTTP server -------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            u, _, p = decoded.partition(":")
        except Exception:
            return False
        return hmac.compare_digest(u, USER) and hmac.compare_digest(p, PASSWORD)

    def _require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="crywatch config"')
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"authentication required")

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, message):
        self._send(code, json.dumps({"error": message}))

    def do_GET(self):
        if not self._authorized():
            return self._require_auth()
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(HERE, "config_ui.html"), "rb").read(),
                               "text/html; charset=utf-8")
        if path == "/api/config":
            try:
                return self._send(200, json.dumps(get_config()))
            except Exception as e:
                return self._json_error(500, str(e))
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._authorized():
            return self._require_auth()
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json_error(400, "invalid JSON")

        if path == "/api/cameras":
            cameras = payload.get("cameras", [])
            err = validate_cameras(cameras)
            if err:
                return self._json_error(400, err)
            try:
                write_go2rtc(cameras)
                update_env({"CAMS": labels_to_cams_var(cameras)})
            except Exception as e:
                return self._json_error(500, str(e))
            return self._send(200, json.dumps({"ok": True}))

        if path == "/api/mqtt":
            m = payload.get("mqtt", {})
            err = validate_mqtt(m)
            if err:
                return self._json_error(400, err)
            updates = {
                "MQTT_HOST": m.get("host", ""),
                "MQTT_PORT": str(int(m["port"])),
                "MQTT_USER": m.get("user", ""),
                "MQTT_TOPIC_BASE": m.get("topic_base") or "crywatch",
                "MQTT_DISCOVERY": "1" if m.get("discovery") else "0",
                "CRY_STATE_TIMEOUT": str(m.get("state_timeout", "60")),
            }
            if m.get("password"):
                updates["MQTT_PASSWORD"] = m["password"]
            try:
                update_env(updates)
            except Exception as e:
                return self._json_error(500, str(e))
            return self._send(200, json.dumps({"ok": True}))

        self._send(404, b"not found", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"config-ui: http://{HOST}:{PORT}/  (go2rtc={GO2RTC_PATH}  env={ENV_PATH})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

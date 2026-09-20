#!/usr/bin/env python3
"""Crywatch cry-detector — Home Assistant Add-on.

Runs Google's YAMNet on short RTSP audio bursts, one thread per camera, and
serves the current state over a tiny local JSON API for the companion
"crywatch" HA integration (custom_components/crywatch) to poll. No MQTT, no
ntfy — this replaces both with native HA entities via that integration.

Cameras are NOT configured here: this add-on starts with zero cameras and
waits for the integration to POST /api/cameras with the RTSP source of
whichever HA `camera.*` entities the user picked (resolved from HA's own
camera component, so no RTSP URL/credentials are typed twice). Only the
detection tuning (cry_prob, sustain, ...) lives in this add-on's own
Configuration tab.

Not reachable from the LAN by default: this add-on declares no `ports` in
config.yaml, so http://crywatch_cry_detector:8091 only resolves on
Supervisor's internal docker network (i.e. from Home Assistant Core itself).
"""
import csv
import json
import math
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import numpy as np

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
PORT = int(os.environ.get("PORT", "8091"))
SR = 16000

with open(OPTIONS_PATH) as f:
    OPTIONS = json.load(f)

CRY_PROB = float(OPTIONS.get("cry_prob", 0.4))
SUSTAIN = int(OPTIONS.get("sustain_samples", 2))
COOLDOWN = float(OPTIONS.get("cooldown", 60))
SAMPLE_SEC = str(OPTIONS.get("sample_sec", 2.0))
RMS_GATE = float(OPTIONS.get("rms_gate_db", -60))
STATE_TIMEOUT = float(OPTIONS.get("state_timeout", 60))
LOG = bool(OPTIONS.get("log_scores", False))

import tensorflow_hub as hub  # noqa: E402

print("[yamnet] loading model ...", flush=True)
_model = hub.load("https://tfhub.dev/google/yamnet/1")
_cmap = _model.class_map_path().numpy().decode()
CLASS_NAMES = [r["display_name"] for r in csv.DictReader(open(_cmap))]
CRY_IDX = [CLASS_NAMES.index(n) for n in
           ("Baby cry, infant cry", "Crying, sobbing", "Whimper")]
_infer_lock = threading.Lock()   # YAMNet inference is serialized across cam threads
print(f"[yamnet] ready. cry classes={CRY_IDX} prob>={CRY_PROB} sustain={SUSTAIN} "
      f"cooldown={COOLDOWN}s sample={SAMPLE_SEC}s gate={RMS_GATE}dB", flush=True)

_state = {}       # key (HA entity_id) -> {label, crying, score_pct, top, db, last_update}
_state_lock = threading.Lock()
_off_timers = {}  # key -> pending auto-off Timer, so a new cry can cancel/reset it
_monitors = {}    # key -> {"thread": Thread, "stop": Event, "url": str}
_monitors_lock = threading.Lock()


def set_state(key, **fields):
    with _state_lock:
        _state.setdefault(key, {}).update(fields, last_update=time.time())


def drop_state(key):
    with _state_lock:
        _state.pop(key, None)
    old = _off_timers.pop(key, None)
    if old:
        old.cancel()


def sample_audio(url):
    """Return ~SAMPLE_SEC of 16 kHz mono float32 audio pulled directly from the
    camera's RTSP stream, or None."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-rtsp_transport", "tcp",
             "-t", SAMPLE_SEC, "-i", url, "-vn", "-ac", "1", "-ar", str(SR),
             "-f", "f32le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        wav = np.frombuffer(r.stdout, dtype=np.float32).copy()
        return wav if wav.size >= SR // 2 else None    # need >= 0.5s of audio
    except Exception as e:
        print(f"[sample] error: {e}", flush=True)
        return None


def cry_score(wav):
    """(peak cry probability 0..1, loudness dB, top overall class) for a clip."""
    rms = float(np.sqrt(np.mean(wav ** 2)) + 1e-9)
    db = 20 * math.log10(rms)
    if db < RMS_GATE:
        return 0.0, db, "(silence)"
    with _infer_lock:
        scores, _, _ = _model(wav)
    scores = scores.numpy()                              # [frames, 521]
    cry_per_frame = scores[:, CRY_IDX].sum(axis=1)       # cry prob per ~0.48s frame
    peak = float(np.clip(cry_per_frame.max(), 0.0, 1.0))
    top = CLASS_NAMES[int(scores.mean(axis=0).argmax())]
    return peak, db, top


def clear_cry(key):
    set_state(key, crying=False, score_pct=0)


def monitor(key, label, url, stop_event):
    streak = 0
    last_alert = 0.0
    set_state(key, label=label, crying=False, score_pct=0, top="(starting)", db=None)
    while not stop_event.is_set():
        wav = sample_audio(url)
        now = time.time()
        if stop_event.is_set():
            break
        if wav is None:
            time.sleep(2)
            streak = 0
            continue
        score, db, top = cry_score(wav)
        if LOG:
            print(f"[{label}] cry={score:.2f} rms={db:.0f}dB top='{top}' streak={streak}",
                  flush=True)
        if score >= CRY_PROB:
            streak += 1
            if streak >= SUSTAIN and now - last_alert >= COOLDOWN:
                last_alert = now
                pct = round(score * 100)
                print(f"[CRY] {label} cry={score:.2f} x{streak}", flush=True)
                set_state(key, crying=True, score_pct=pct, top=top, db=db)
                old = _off_timers.get(key)
                if old:
                    old.cancel()
                t = threading.Timer(STATE_TIMEOUT, clear_cry, args=(key,))
                t.daemon = True
                t.start()
                _off_timers[key] = t
            else:
                set_state(key, top=top, db=db)
        else:
            streak = 0
            set_state(key, top=top, db=db)


def apply_cameras(cameras):
    """Reconcile the running monitor threads against a fresh camera list
    (key/name/rtsp_url dicts, as pushed by the crywatch integration)."""
    wanted = {c["key"]: c for c in cameras if c.get("key") and c.get("rtsp_url")}
    with _monitors_lock:
        for key in list(_monitors):
            if key not in wanted or _monitors[key]["url"] != wanted[key]["rtsp_url"]:
                _monitors[key]["stop"].set()
                del _monitors[key]
                if key not in wanted:
                    drop_state(key)
        for key, cam in wanted.items():
            if key in _monitors:
                continue
            stop_event = threading.Event()
            t = threading.Thread(
                target=monitor, args=(key, cam.get("name", key), cam["rtsp_url"], stop_event),
                daemon=True)
            _monitors[key] = {"thread": t, "stop": stop_event, "url": cam["rtsp_url"]}
            t.start()
    print(f"[cameras] now watching {len(wanted)} camera(s): {list(wanted)}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path in ("/api/state", "/"):
            with _state_lock:
                body = json.dumps({"cameras": _state}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path == "/api/cameras":
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
                apply_cameras(payload.get("cameras", []))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"[api] serving state on :{PORT} — waiting for the crywatch integration "
          f"to POST /api/cameras", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

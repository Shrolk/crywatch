#!/usr/bin/env python3
"""Crywatch cry-detector — Home Assistant Add-on.

Runs Google's YAMNet on short RTSP audio bursts, one thread per configured
camera (read from the add-on's options, /data/options.json — set from the
Configuration tab, no separate web UI), and serves the current state over a
tiny local JSON API for the companion "crywatch" HA integration
(custom_components/crywatch) to poll. No MQTT, no ntfy — this replaces both
with native HA entities via that integration.

Not reachable from the LAN by default: this add-on declares no `ports` in
config.yaml, so http://crywatch_cry_detector:8091 only resolves on
Supervisor's internal docker network (i.e. from Home Assistant Core itself).
"""
import csv
import json
import math
import os
import re
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

CAMERAS = OPTIONS.get("cameras") or []
CRY_PROB = float(OPTIONS.get("cry_prob", 0.4))
SUSTAIN = int(OPTIONS.get("sustain_samples", 2))
COOLDOWN = float(OPTIONS.get("cooldown", 60))
SAMPLE_SEC = str(OPTIONS.get("sample_sec", 2.0))
RMS_GATE = float(OPTIONS.get("rms_gate_db", -60))
STATE_TIMEOUT = float(OPTIONS.get("state_timeout", 60))
LOG = bool(OPTIONS.get("log_scores", False))

if not CAMERAS:
    raise SystemExit("no cameras configured — add at least one in the add-on's "
                      "Configuration tab before starting")


def slug(label):
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


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

_state = {}       # slug -> {label, crying, score_pct, top, db, last_update}
_state_lock = threading.Lock()
_off_timers = {}  # slug -> pending auto-off Timer, so a new cry can cancel/reset it


def set_state(key, **fields):
    with _state_lock:
        _state.setdefault(key, {}).update(fields, last_update=time.time())


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


def monitor(cam):
    label = cam.get("name") or cam["rtsp_url"]
    key = slug(label)
    url = cam["rtsp_url"]
    streak = 0
    last_alert = 0.0
    set_state(key, label=label, crying=False, score_pct=0, top="(starting)", db=None)
    while True:
        wav = sample_audio(url)
        now = time.time()
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

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    for cam in CAMERAS:
        threading.Thread(target=monitor, args=(cam,), daemon=True).start()
    print(f"[api] serving state on :{PORT}/api/state", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

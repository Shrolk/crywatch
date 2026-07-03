#!/usr/bin/env python3
"""Server-side BABY-CRY CLASSIFIER for self-hosted camera streams.

Instead of a loudness threshold (which false-alarms on the vacuum, TV, talking,
etc.), this runs Google's YAMNet audio classifier (trained on AudioSet) on short
audio bursts pulled from go2rtc, and only alerts when the sound is actually a baby
crying. Cry classes (Baby cry / Crying, sobbing / Whimper) are separate from
Screaming / Shout / Yell / Speech, so "loud" no longer means "crying".

For each camera it repeatedly:
  1. burst-samples ~CRY_SAMPLE_SEC of 16 kHz mono audio via ffmpeg (audio only,
     no video, no GPU),
  2. skips YAMNet if the clip is essentially silence (cheap RMS gate),
  3. runs YAMNet and takes the PEAK per-frame probability of the cry classes,
  4. when that stays >= CRY_PROB for a few consecutive samples, POSTs a push to
     a self-hosted ntfy topic, debounced by a cooldown.

The model is tiny and runs on plain CPU — no GPU needed.

Env vars (see .env.example):
  NTFY_URL            ntfy topic URL           (default http://localhost:8095/baby-cry)
  CRY_PROB            cry probability 0..1 to trigger (default 0.4)
  CRY_SUSTAIN_SAMPLES consecutive cry samples  (default 2)
  CRY_COOLDOWN        min seconds between alerts (default 60)
  CRY_SAMPLE_SEC      audio seconds per sample (default 2.0)
  CRY_RMS_GATE_DB     skip YAMNet below this loudness (default -60 ; ~silence)
  CRY_LOG             "1" = print scores every sample (use to calibrate)
  CAMS                "stream=Label,stream=Label" (stream names must match go2rtc)
  GO2RTC_RTSP         go2rtc RTSP base         (default rtsp://localhost:8554)
  CRY_CLICK_URL       URL opened when the notification is tapped
"""
import os, csv, time, math, threading, subprocess, urllib.request
import numpy as np

NTFY       = os.environ.get("NTFY_URL", "http://localhost:8095/baby-cry")
CRY_PROB   = float(os.environ.get("CRY_PROB", "0.4"))
SUSTAIN    = int(os.environ.get("CRY_SUSTAIN_SAMPLES", "2"))
COOLDOWN   = float(os.environ.get("CRY_COOLDOWN", "60"))
SAMPLE_SEC = os.environ.get("CRY_SAMPLE_SEC", "2.0")
RMS_GATE   = float(os.environ.get("CRY_RMS_GATE_DB", "-60"))
LOG        = os.environ.get("CRY_LOG", "0") == "1"
CAMS       = os.environ.get("CAMS", "cam1=Room 1,cam2=Room 2")
RTSP_BASE  = os.environ.get("GO2RTC_RTSP", "rtsp://localhost:8554")
CLICK_URL  = os.environ.get("CRY_CLICK_URL", "http://localhost:1985/multi.html")
SR = 16000

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


def _h(v):
    # HTTP header values must be latin-1; smuggle UTF-8 through so ntfy decodes it.
    return v.encode("utf-8").decode("latin-1")


def notify(label, pct):
    try:
        req = urllib.request.Request(
            NTFY,
            data=f"\U0001F476 Crying detected — {label} ({pct}%)".encode("utf-8"),
            headers={
                "Title": _h("Baby cry alert"),
                "Priority": "high",
                "Tags": "baby_symbol",
                "Click": CLICK_URL,
                "Actions": _h(f"view, Open camera, {CLICK_URL}"),
            })
        urllib.request.urlopen(req, timeout=5)
        print(f"[notify] sent for {label} ({pct}%)", flush=True)
    except Exception as e:
        print(f"[notify] error: {e}", flush=True)


def sample_audio(url):
    """Return ~SAMPLE_SEC of 16 kHz mono float32 audio from the stream, or None."""
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


def monitor(stream, label):
    url = f"{RTSP_BASE}/{stream}"
    streak = 0
    last_alert = 0.0
    while True:
        wav = sample_audio(url)
        now = time.time()
        if wav is None:
            time.sleep(2); streak = 0; continue
        score, db, top = cry_score(wav)
        if LOG:
            print(f"[{label}] cry={score:.2f} rms={db:.0f}dB top='{top}' streak={streak}",
                  flush=True)
        if score >= CRY_PROB:
            streak += 1
            if streak >= SUSTAIN and now - last_alert >= COOLDOWN:
                last_alert = now
                print(f"[CRY] {label} cry={score:.2f} x{streak}", flush=True)
                notify(label, round(score * 100))
        else:
            streak = 0


if __name__ == "__main__":
    for pair in CAMS.split(","):
        stream, _, label = pair.partition("=")
        threading.Thread(target=monitor, args=(stream.strip(), label.strip()),
                         daemon=True).start()
    while True:
        time.sleep(3600)

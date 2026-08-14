#!/usr/bin/env python3
"""
presence_detector.py — "is the baby in the crib?" alarm service.

Every POLL_SEC it grabs a snapshot from go2rtc, runs a YOLO model to find the
baby, and:
  - baby detected (inside the sleep zone, if set)      -> "present"
  - nothing for ABSENT_SEC seconds                     -> ntfy push "baby not detected"
  - baby detected again                                -> ntfy push "baby is back"
It also flags motion inside the crib ("baby is moving": woke up / rolled / crawling)
and writes the current boxes to boxes.json so a web viewer can overlay them.

IMPORTANT: this ships NO model. Off-the-shelf detectors do NOT reliably see a
night-vision, blanket-covered baby. You train your OWN model on your OWN camera
(see ../training/ and ../labeling/). Point MODEL at your fine-tuned baby.pt.
If MODEL is unset and no baby.pt is present, it falls back to a stock yolo11 model
(which will mostly work in daylight and mostly fail at night — that's the point).

Active-learning loop: when the model misses but the baby is likely there (motion
in-zone or a weak in-zone box), the raw frame is saved to frames/hard/ so you can
label it and retrain. This is what makes each round get sharply better.

All config is via env vars (see .env.example). Runs on CPU or GPU.
"""
import os, time, json, threading, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import cv2
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))

# --- source & model ---
STREAM       = os.environ.get("STREAM", "cam1")               # go2rtc stream name
LABEL        = os.environ.get("LABEL", "Baby")                # shown in notifications
GO2RTC       = os.environ.get("GO2RTC", "http://localhost:1984")
_BABY = os.path.join(HERE, "baby.pt")                         # your fine-tuned model (gitignored)
MODEL        = os.environ.get("MODEL", _BABY if os.path.exists(_BABY) else "yolo11s.pt")
CONF         = float(os.environ.get("CONF", "0.5"))           # display / strong-detection threshold
ZONE_CONF    = float(os.environ.get("ZONE_CONF", "0.15"))     # inside the zone: accept weaker boxes
POLL_SEC     = float(os.environ.get("POLL_SEC", "2"))
ABSENT_SEC   = float(os.environ.get("ABSENT_SEC", "90"))
COOLDOWN     = float(os.environ.get("COOLDOWN", "600"))
MIN_BOX_FRAC = float(os.environ.get("MIN_BOX_FRAC", "0.01"))  # ignore tiny boxes

# --- push (ntfy) ---
NTFY         = os.environ.get("NTFY_URL", "http://localhost:8095/baby")
CLICK_URL    = os.environ.get("CLICK_URL", "http://localhost:1985/multi.html")
LOG          = os.environ.get("PRESENCE_LOG", "0") == "1"

# --- viewer overlay ---
BOXES_JSON   = os.environ.get("BOXES_JSON", os.path.join(HERE, "boxes.json"))

# --- motion (woke up / rolled / crawling): pixel change inside the baby box ---
MOTION_ON       = os.environ.get("MOTION_ON", "1") == "1"
MOTION_PIX      = int(os.environ.get("MOTION_PIX", "25"))        # per-pixel diff threshold 0-255
MOTION_FRAC     = float(os.environ.get("MOTION_FRAC", "0.08"))   # in-box changed fraction >= this = moving
MOTION_SUSTAIN  = int(os.environ.get("MOTION_SUSTAIN", "2"))     # consecutive samples before alerting
MOTION_COOLDOWN = float(os.environ.get("MOTION_COOLDOWN", "300"))
MASK_TOP_FRAC   = float(os.environ.get("MASK_TOP_FRAC", "0.08")) # mask the top timestamp banner
# In-zone motion floor to count as "present" (still baby that the model can't see but that twitches).
# Measured noise floor of a perfectly still frame is ~0.0002, so 0.01 is safely above noise.
ZONE_MOTION_FRAC = float(os.environ.get("ZONE_MOTION_FRAC", "0.01"))

# --- active learning: auto-collect the model's misses for the next training round ---
HARD_ON       = os.environ.get("HARD_COLLECT", "1") == "1"
HARD_SAVE_SEC = float(os.environ.get("HARD_SAVE_SEC", "20"))    # min seconds between saves
HARD_MAX      = int(os.environ.get("HARD_MAX", "3000"))
HARD_FLOOR    = float(os.environ.get("HARD_FLOOR", "0.02"))     # lowest conf to keep a weak box

ZONE_FILE = os.path.join(HERE, "zone.json")
ALERT_DIR = os.path.join(HERE, "alerts")
HARD_DIR  = os.path.join(HERE, "frames", "hard")
os.makedirs(ALERT_DIR, exist_ok=True)

# --- arm/disarm + absent-alarm toggle (controllable from the viewer, so an empty crib
#     during the day doesn't spam you) ---
CONTROL_HOST = os.environ.get("CONTROL_HOST", "0.0.0.0")
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "1986"))
CTRL_FILE = os.path.join(HERE, "control.json")
STATE = {"armed": True, "present": True, "gone": 0.0, "ts": 0.0,
         "moving": False, "motion": 0.0, "zone": None, "absent_alarm": True}
STATE_LOCK = threading.Lock()
ZONE = {"n": None}   # active sleep zone (normalized 0..1); None = whole frame


def _load_state():
    try:
        with open(CTRL_FILE) as f:
            d = json.load(f)
        STATE["armed"] = bool(d.get("armed", True))
        STATE["absent_alarm"] = bool(d.get("absent_alarm", True))
    except Exception:
        pass


def _save_state():
    try:
        with open(CTRL_FILE, "w") as f:
            json.dump({"armed": STATE["armed"], "absent_alarm": STATE["absent_alarm"]}, f)
    except Exception:
        pass


class _Ctrl(BaseHTTPRequestHandler):
    """Tiny control API for the viewer: /arm /disarm /toggle, /absent/{on,off,toggle},
    /zone/set?x1&y1&x2&y2 (normalized), /zone/clear. Any GET returns the current state."""
    def _reply(self):
        with STATE_LOCK:
            body = json.dumps(dict(STATE)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")   # viewer is on a different port
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        with STATE_LOCK:
            if p == "/arm":
                STATE["armed"] = True; _save_state()
            elif p == "/disarm":
                STATE["armed"] = False; _save_state()
            elif p == "/toggle":
                STATE["armed"] = not STATE["armed"]; _save_state()
            elif p == "/absent/on":
                STATE["absent_alarm"] = True; _save_state()
            elif p == "/absent/off":
                STATE["absent_alarm"] = False; _save_state()
            elif p == "/absent/toggle":
                STATE["absent_alarm"] = not STATE["absent_alarm"]; _save_state()
            elif p == "/zone/set":
                try:
                    v = [min(1.0, max(0.0, float(q[k][0]))) for k in ("x1", "y1", "x2", "y2")]
                    x1, y1 = min(v[0], v[2]), min(v[1], v[3])
                    x2, y2 = max(v[0], v[2]), max(v[1], v[3])
                    if x2 - x1 >= 0.02 and y2 - y1 >= 0.02:     # ignore too-small boxes
                        ZONE["n"] = (x1, y1, x2, y2)
                        save_zone(ZONE["n"]); STATE["zone"] = list(ZONE["n"])
                        print(f"[zone] set {tuple(round(t, 3) for t in ZONE['n'])}", flush=True)
                except Exception as e:
                    print(f"[zone] set error: {e}", flush=True)
            elif p == "/zone/clear":
                ZONE["n"] = None; clear_zone_file(); STATE["zone"] = None
                print("[zone] cleared", flush=True)
        self._reply()

    def log_message(self, *a):
        pass


def start_control_server():
    _load_state()
    try:
        srv = ThreadingHTTPServer((CONTROL_HOST, CONTROL_PORT), _Ctrl)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"[control] http://{CONTROL_HOST}:{CONTROL_PORT}  armed={STATE['armed']}", flush=True)
    except Exception as e:
        print(f"[control] server failed: {e}", flush=True)


def _h(v):   # ntfy headers must be latin-1; smuggle UTF-8 through (ntfy decodes it back)
    return v.encode("utf-8").decode("latin-1")


def notify(title, body, tags="warning", click=True):
    try:
        headers = {"Title": _h(title), "Priority": "high", "Tags": tags}
        if click:
            headers["Click"] = CLICK_URL
            headers["Actions"] = _h(f"view, View camera, {CLICK_URL}")
        req = urllib.request.Request(NTFY, data=body.encode("utf-8"), headers=headers)
        urllib.request.urlopen(req, timeout=5)
        print(f"[notify] {body}", flush=True)
    except Exception as e:
        print(f"[notify] error: {e}", flush=True)


def grab():
    """Return a BGR numpy image, or None on failure / empty frame."""
    try:
        with urllib.request.urlopen(f"{GO2RTC}/api/frame.jpeg?src={STREAM}", timeout=10) as r:
            data = r.read()
        if not data:
            return None
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[grab] error: {e}", flush=True)
        return None


def load_zone():
    try:
        with open(ZONE_FILE) as f:
            z = json.load(f)
        n = (float(z["x1"]), float(z["y1"]), float(z["x2"]), float(z["y2"]))
        if all(0.0 <= v <= 1.0 for v in n) and n[2] > n[0] and n[3] > n[1]:
            return n
    except Exception:
        pass
    return None


def save_zone(n):
    tmp = ZONE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"x1": n[0], "y1": n[1], "x2": n[2], "y2": n[3]}, f)
    os.replace(tmp, ZONE_FILE)


def clear_zone_file():
    try:
        os.remove(ZONE_FILE)
    except FileNotFoundError:
        pass


def in_zone(cx, cy, z):   # z = pixel coords (x1,y1,x2,y2)
    return z[0] <= cx <= z[2] and z[1] <= cy <= z[3]


def box_motion(prev_gray, cur_gray, bx):
    """Fraction of changed pixels inside a box (0..1). bx=(x1,y1,x2,y2) pixels."""
    x1, y1 = max(0, int(bx[0])), max(0, int(bx[1]))
    x2, y2 = min(cur_gray.shape[1], int(bx[2])), min(cur_gray.shape[0], int(bx[3]))
    if x2 - x1 < 5 or y2 - y1 < 5:
        return 0.0
    d = cv2.absdiff(prev_gray[y1:y2, x1:x2], cur_gray[y1:y2, x1:x2])
    return float((d >= MOTION_PIX).mean())


def publish(now, present, W, H, boxes, zone, moving=False, motion=0.0):
    """Atomically write the current boxes (normalized) to BOXES_JSON for the viewer."""
    if not BOXES_JSON:
        return
    try:
        data = {
            "ts": now, "stream": STREAM, "present": present,
            "moving": bool(moving), "motion": round(float(motion), 3),
            "boxes": [{"x1": x1 / W, "y1": y1 / H, "x2": x2 / W, "y2": y2 / H,
                       "conf": round(c, 2)} for (x1, y1, x2, y2, c) in boxes],
            "zone": (list(zone) if zone else None),
        }
        tmp = BOXES_JSON + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, BOXES_JSON)   # atomic — the viewer never reads a half-written file
    except Exception as e:
        print(f"[publish] error: {e}", flush=True)


def cuda_ok():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def main():
    start_control_server()
    model = YOLO(MODEL)
    dev = 0 if cuda_ok() else "cpu"
    print(f"[presence] model={MODEL} stream={STREAM} conf={CONF} poll={POLL_SEC}s "
          f"absent={ABSENT_SEC}s cooldown={COOLDOWN}s device={'GPU' if dev == 0 else 'CPU'}",
          flush=True)

    with STATE_LOCK:
        ZONE["n"] = load_zone()
        STATE["zone"] = list(ZONE["n"]) if ZONE["n"] else None

    last_present = time.time()   # assume "present" at boot so we don't false-alarm on startup
    last_alert = 0.0
    alerted = False
    seen = False                 # have we EVER seen the baby since arming? (don't alarm on an empty crib)
    prev_armed = None
    prev_gray = None
    motion_streak = 0
    last_motion_alert = 0.0
    last_hard_save = 0.0
    hard_full_warned = False

    while True:
        img = grab()
        now = time.time()
        if img is None:
            time.sleep(POLL_SEC)
            continue
        H, W = img.shape[:2]
        min_area = MIN_BOX_FRAC * W * H
        with STATE_LOCK:
            armed = STATE["armed"]
            absent_on = STATE["absent_alarm"]
            zone_n = ZONE["n"]
        zone_px = ((zone_n[0] * W, zone_n[1] * H, zone_n[2] * W, zone_n[3] * H) if zone_n else None)

        # With a zone we lower the predict threshold to also surface weak in-zone boxes.
        pconf = min(CONF, HARD_FLOOR) if zone_n else CONF
        res = model.predict(img, conf=pconf, classes=[0], device=dev, verbose=False)[0]
        all_boxes = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            if (x2 - x1) * (y2 - y1) >= min_area:
                all_boxes.append((x1, y1, x2, y2, float(b.conf[0])))
        disp_boxes = [b for b in all_boxes if b[4] >= CONF]

        def _cin(b):
            return in_zone((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, zone_px)

        # --- motion inside the zone (or the top box if no zone) ---
        motion = 0.0; zone_motion = 0.0; moving = False
        if MOTION_ON:
            try:
                cur_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                cur_gray[:int(MASK_TOP_FRAC * H), :] = 0        # mask the ticking timestamp banner
                if prev_gray is not None:
                    if zone_px:
                        zone_motion = box_motion(prev_gray, cur_gray, zone_px)
                    elif disp_boxes:
                        zone_motion = box_motion(prev_gray, cur_gray, max(disp_boxes, key=lambda b: b[4]))
                motion = zone_motion
                prev_gray = cur_gray
            except Exception as e:
                print(f"[motion] error: {e}", flush=True)

        # --- present / absent ---
        if zone_n:
            det_present = (any(_cin(b) for b in disp_boxes)
                           or any(b[4] >= ZONE_CONF and _cin(b) for b in all_boxes))
            present = det_present or (zone_motion >= ZONE_MOTION_FRAC)   # in-zone motion = present
        else:
            det_present = len(disp_boxes) > 0
            present = det_present

        if prev_armed is not None and armed and not prev_armed:   # just armed -> reset
            seen = False; last_present = now; alerted = False
        prev_armed = armed

        if present:
            last_present = now
            seen = True
            if alerted:
                alerted = False
                notify(f"{LABEL} · back", f"{LABEL}: baby detected again", tags="white_check_mark")
        gone = now - last_present
        if (not present) and armed and absent_on and seen and gone >= ABSENT_SEC \
                and now - last_alert >= COOLDOWN:
            last_alert = now
            alerted = True
            cv2.imwrite(os.path.join(ALERT_DIR, f"alert_{int(now)}.jpg"), res.plot())
            notify(f"{LABEL} · not detected",
                   f"{LABEL}: no baby detected for {int(gone)}s (left the crib / covered?)")

        # --- motion alert (woke up / rolled / crawling) ---
        if MOTION_ON and present and prev_gray is not None:
            moving = zone_motion >= MOTION_FRAC
            motion_streak = motion_streak + 1 if moving else 0
            if armed and motion_streak >= MOTION_SUSTAIN and now - last_motion_alert >= MOTION_COOLDOWN:
                last_motion_alert = now
                motion_streak = 0
                notify(f"{LABEL} · moving", f"{LABEL}: baby is moving (woke up / rolled / crawling)",
                       tags="eyes")
        else:
            motion_streak = 0

        # --- active learning: model missed but baby likely there -> save the frame ---
        if (HARD_ON and zone_n and armed and (not det_present)
                and (zone_motion >= ZONE_MOTION_FRAC * 0.5
                     or any(HARD_FLOOR <= b[4] < CONF and _cin(b) for b in all_boxes))
                and now - last_hard_save >= HARD_SAVE_SEC):
            try:
                cnt = len(os.listdir(HARD_DIR)) if os.path.isdir(HARD_DIR) else 0
                if cnt < HARD_MAX:
                    os.makedirs(HARD_DIR, exist_ok=True)
                    cv2.imwrite(os.path.join(HARD_DIR, f"hard_{int(now)}.jpg"), img)
                    last_hard_save = now
                elif not hard_full_warned:
                    print(f"[hard] reached HARD_MAX={HARD_MAX}, stop collecting", flush=True)
                    hard_full_warned = True
            except Exception as e:
                print(f"[hard] error: {e}", flush=True)

        with STATE_LOCK:
            STATE.update(present=present, gone=gone, ts=now, moving=moving, motion=round(motion, 3))
        # Show only the single highest-confidence box (there's one baby) — avoids the
        # occasional "two boxes on one baby" (model firing on legs + torso). Detection
        # logic above still uses all boxes; only the overlay is top-1.
        disp_top = [max(disp_boxes, key=lambda b: b[4])] if disp_boxes else []
        publish(now, present, W, H, disp_top, zone_n, moving, motion)

        if LOG:
            mc = max([c for *_, c in all_boxes], default=0.0)
            print(f"[{LABEL}] armed={armed} present={present} det={det_present} seen={seen} "
                  f"gone={int(gone)}s maxconf={mc:.2f} motion={motion:.4f}", flush=True)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
label_server.py — a tiny browser labeling tool for the single-class "baby" model,
with AI-assisted pre-labels (model-in-the-loop).

Usage (system python3, no GPU needed):
    FRAMES_DIR=frames/review python3 label_server.py
    # then open http://localhost:1987/ and box the baby in each frame.

Model-assisted flow (the fast part):
  1. Run ../training/prelabel.py first: it runs your CURRENT model over the new
     frames and writes a suggested box to prelabels/<name>.txt for each detection.
  2. This tool shows that suggestion as an ORANGE DASHED box. You just confirm
     (Save), nudge it, or clear+redraw. Frames the model missed show no box —
     draw them by hand (those are your model's blind spots, the highest value).
  3. Saving always writes to labels/<name>.txt (YOLO format; empty file = no baby).

Roughly half the frames come pre-boxed, so you only draw the hard misses.
"""
import os, json, glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.environ.get("FRAMES_DIR", os.path.join(HERE, "frames", "review"))
LABELS_DIR = os.environ.get("LABELS_DIR", os.path.join(HERE, "labels"))
# AI pre-labels: when there's no human label yet, show this as a suggestion to confirm.
PRELABELS_DIR = os.environ.get("PRELABELS_DIR", os.path.join(HERE, "prelabels"))
PORT = int(os.environ.get("LABEL_PORT", "1987"))
HOST = os.environ.get("LABEL_HOST", "0.0.0.0")
os.makedirs(LABELS_DIR, exist_ok=True)


def images():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(FRAMES_DIR, "*.jpg")))


def label_path(name):
    return os.path.join(LABELS_DIR, os.path.splitext(name)[0] + ".txt")


def _box_from(path):
    line = open(path).read().strip()
    if not line:
        return None
    xc, yc, w, h = map(float, line.split()[1:5])     # class xc yc w h  (YOLO, normalized)
    return [xc - w / 2, yc - h / 2, w, h]            # -> [x, y, w, h] top-left + size


def read_label(name):
    p = label_path(name)
    if os.path.exists(p):                            # human-confirmed
        b = _box_from(p)
        return {"status": "empty" if b is None else "box", "box": b}
    pp = os.path.join(PRELABELS_DIR, os.path.splitext(name)[0] + ".txt")
    if os.path.exists(pp):                            # AI suggestion (unconfirmed)
        b = _box_from(pp)
        if b:
            return {"status": "suggest", "box": b}
    return {"status": "none", "box": None}


def write_label(name, box, empty):
    p = label_path(name)
    if empty:
        open(p, "w").close()                          # empty file = negative sample (no baby)
    elif box:
        x, y, w, h = box
        with open(p, "w") as f:
            f.write(f"0 {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}\n")
    elif os.path.exists(p):
        os.remove(p)


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(HERE, "label.html"), "rb").read(),
                              "text/html; charset=utf-8")
        if u.path == "/api/list":
            imgs = images()
            done = {os.path.splitext(f)[0] for f in os.listdir(LABELS_DIR) if f.endswith(".txt")}
            sugg = ({os.path.splitext(f)[0] for f in os.listdir(PRELABELS_DIR) if f.endswith(".txt")}
                    if os.path.isdir(PRELABELS_DIR) else set())
            items = [{"name": n, "labeled": os.path.splitext(n)[0] in done,
                      "suggested": os.path.splitext(n)[0] in sugg} for n in imgs]
            return self._send(200, json.dumps({"images": items, "total": len(imgs),
                                               "labeled": sum(i["labeled"] for i in items)}))
        if u.path == "/api/label":
            return self._send(200, json.dumps(read_label(q.get("name", [""])[0])))
        if u.path == "/img":
            name = os.path.basename(q.get("name", [""])[0])
            fp = os.path.join(FRAMES_DIR, name)
            if os.path.exists(fp):
                return self._send(200, open(fp, "rb").read(), "image/jpeg")
            return self._send(404, b"not found", "text/plain")
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path == "/api/label":
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n) or b"{}")
            write_label(d["name"], d.get("box"), d.get("empty", False))
            return self._send(200, json.dumps({"ok": True}))
        self._send(404, b"not found", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"labeling tool: http://{HOST}:{PORT}/")
    print(f"frames={FRAMES_DIR} ({len(images())})  labels={LABELS_DIR}  prelabels={PRELABELS_DIR}")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()

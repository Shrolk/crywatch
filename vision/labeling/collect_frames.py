#!/usr/bin/env python3
"""
collect_frames.py — grab snapshots from go2rtc to build a labeling/training set.

Use this to seed your very first dataset (before you have a model). After that,
the detector's active-learning loop (frames/hard/) collects the *hard* misses for
you automatically — those are worth far more than random frames.

Examples:
  # every 10s, both cameras, save under ./frames/, Ctrl-C to stop
  python3 collect_frames.py

  # every 5s, stop after 60 frames per camera (quick test set)
  python3 collect_frames.py --interval 5 --count 60

  # only the bedroom cam, every 30s (accumulate a night of night-vision frames)
  python3 collect_frames.py --cams cam2 --interval 30

Saves to frames/<label>/<label>_YYYYmmdd_HHMMSS.jpg. Images stay local (frames/ is
gitignored). Zero deps: standard library only.

Env: GO2RTC (default http://localhost:1984), CAMS ("stream=label,stream=label").
"""
import argparse, os, time, urllib.request
from datetime import datetime

GO2RTC = os.environ.get("GO2RTC", "http://localhost:1984")
# stream name -> short label (folder). Override with --cams or CAMS env.
_ENV_CAMS = os.environ.get("CAMS", "cam1=room1,cam2=room2")
CAMS = {}
for pair in _ENV_CAMS.split(","):
    if "=" in pair:
        s, l = pair.split("=", 1)
        CAMS[s.strip()] = l.strip()


def grab(stream, timeout=10):
    url = f"{GO2RTC}/api/frame.jpeg?src={stream}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=10, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="frames per camera then stop (0 = until Ctrl-C)")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
    ap.add_argument("--cams", default=",".join(CAMS) if CAMS else "cam1", help="comma-separated stream names")
    args = ap.parse_args()

    streams = [c.strip() for c in args.cams.split(",") if c.strip()]
    for s in streams:
        os.makedirs(os.path.join(args.outdir, CAMS.get(s, s)), exist_ok=True)

    saved = {s: 0 for s in streams}
    skipped = {s: 0 for s in streams}
    goal = "unlimited (Ctrl-C)" if args.count == 0 else f"{args.count}/cam"
    print(f"collecting: {streams}  every {args.interval}s  goal {goal}")
    try:
        while True:
            for s in streams:
                label = CAMS.get(s, s)
                try:
                    data = grab(s)
                except Exception as e:
                    skipped[s] += 1
                    print(f"  [{label}] grab failed: {e}")
                    continue
                if not data:                       # 0 bytes = camera offline / no snapshot
                    skipped[s] += 1
                    print(f"  [{label}] empty frame (camera offline?), skip")
                    continue
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fn = os.path.join(args.outdir, label, f"{label}_{ts}.jpg")
                with open(fn, "wb") as f:
                    f.write(data)
                saved[s] += 1
                print(f"  [{label}] saved {os.path.basename(fn)}  ({len(data)//1024} KB)  total {saved[s]}")
            if args.count and all(saved[s] >= args.count for s in streams):
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
    total = sum(saved.values())
    print(f"done: {total} frames in {args.outdir}/")
    for s in streams:
        print(f"  {CAMS.get(s, s)}: {saved[s]} (skipped {skipped[s]})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
train_baby.py — fine-tune a small YOLO (yolo11s) into your own single-class "baby"
detector, using the frames you labeled with ../labeling/.

Why fine-tune: stock detectors are trained on clear, daytime, upright people. They
do NOT reliably see a grayscale night-vision baby wrapped in a blanket. Fine-tuning
on YOUR camera's actual footage is what takes it from "conf 0.03, can't see it" to
"recall 90%+".

It builds a YOLO dataset from labels/ + frames/**:
  - positives: every frame with a box
  - negatives: empty-label frames (empty crib), sampled to NEG_MULT x positives so
    the model doesn't just learn "empty crib"
  - 90/10 train/val split
then fine-tunes and writes baby.pt (which presence_detector.py auto-loads).

Usage (needs ultralytics + a GPU; easiest via the official Docker image, see
remote_train.sh):
    python3 train_baby.py --base yolo11s.pt --epochs 80 --imgsz 640 --batch 8
"""
import os, glob, random, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.environ.get("FRAMES", os.path.join(HERE, "frames"))   # scanned recursively
LABELS = os.environ.get("LABELS", os.path.join(HERE, "labels"))
DATASET = os.environ.get("DATASET", os.path.join(HERE, "dataset"))


def _index_images():
    """Index every frames/**/*.jpg by basename, so a label finds its image no matter
    which subfolder it lives in (e.g. frames/hard/ vs frames/room2/)."""
    idx = {}
    for img in glob.glob(os.path.join(FRAMES, "**", "*.jpg"), recursive=True):
        idx.setdefault(os.path.splitext(os.path.basename(img))[0], img)
    return idx


def build_dataset(neg_mult, val_frac, seed):
    random.seed(seed)
    img_index = _index_images()
    pos, neg = [], []
    for txt in glob.glob(os.path.join(LABELS, "*.txt")):
        name = os.path.splitext(os.path.basename(txt))[0]
        img = img_index.get(name)
        if img:
            (neg if os.path.getsize(txt) == 0 else pos).append((img, txt))
    random.shuffle(neg)
    neg = neg[:int(len(pos) * neg_mult)]          # balance negatives
    items = pos + neg
    random.shuffle(items)
    n_val = max(1, int(len(items) * val_frac))
    val, train = items[:n_val], items[n_val:]

    if os.path.isdir(DATASET):
        shutil.rmtree(DATASET)
    for split, rows in (("train", train), ("val", val)):
        idir = os.path.join(DATASET, "images", split)
        ldir = os.path.join(DATASET, "labels", split)
        os.makedirs(idir); os.makedirs(ldir)
        for img, txt in rows:
            b = os.path.basename(img)
            os.symlink(img, os.path.join(idir, b))
            os.symlink(txt, os.path.join(ldir, os.path.splitext(b)[0] + ".txt"))

    yaml = os.path.join(DATASET, "data.yaml")
    with open(yaml, "w") as f:
        f.write(f"path: {DATASET}\ntrain: images/train\nval: images/val\nnames:\n  0: baby\n")
    print(f"[dataset] positives={len(pos)} negatives_used={len(neg)} train={len(train)} val={len(val)}",
          flush=True)
    return yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="yolo11s.pt", help="pretrained base (downloaded on first run)")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--neg-mult", type=float, default=1.5)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    yaml = build_dataset(a.neg_mult, a.val_frac, a.seed)

    from ultralytics import YOLO
    model = YOLO(a.base)
    model.train(data=yaml, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=0,
                project=os.path.join(HERE, "runs"), name="baby", exist_ok=True, patience=25)

    best = os.path.join(HERE, "runs", "baby", "weights", "best.pt")
    if os.path.exists(best):
        shutil.copy(best, os.path.join(HERE, "baby.pt"))
        print(f"[done] -> {os.path.join(HERE, 'baby.pt')}", flush=True)
        print("Deploy: copy baby.pt next to presence_detector.py and restart it.", flush=True)
    else:
        print("[warn] best.pt not found, check runs/baby/", flush=True)


if __name__ == "__main__":
    main()

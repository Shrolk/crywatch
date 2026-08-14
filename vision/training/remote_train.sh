#!/usr/bin/env bash
# Train the "baby" model on a machine with a spare GPU, using the official
# Ultralytics Docker image (no sudo, no system python setup — the image already
# has torch + ultralytics + opencv).
#
# TIP: don't train on the GPU that also drives your desktop — a full training run
# pegs the GPU and freezes the screen. Use a headless box, or a second GPU.
#
# 1. Copy your labeled data + these scripts to the training box, e.g.:
#      rsync -a frames/ labels/ train_baby.py  TRAIN_HOST:~/baby-train/
# 2. Run this there:  bash remote_train.sh
# 3. Copy the result back:  scp TRAIN_HOST:~/baby-train/baby.pt detector/baby.pt
set -e
cd "${WORKDIR:-$HOME/baby-train}"
IMG="${ULTRALYTICS_IMAGE:-ultralytics/ultralytics:latest}"

echo "[$(date +%T)] === docker pull $IMG ==="
docker pull "$IMG"

echo "[$(date +%T)] === CUDA sanity check ==="
docker run --rm --gpus all "$IMG" python -c \
"import torch;print('cuda',torch.cuda.is_available(),torch.__version__,torch.cuda.get_device_name(0))"

echo "[$(date +%T)] === training ==="
docker run --rm --gpus all --ipc=host -v "$PWD:/work" -w /work "$IMG" \
  python train_baby.py --base yolo11s.pt --epochs 80 --imgsz 640 --batch 8

echo "[$(date +%T)] === DONE === baby.pt is in $PWD/baby.pt"

# CPU-friendly image for the presence detector. Runs on CPU out of the box.
# For GPU inference, base this on `ultralytics/ultralytics:latest` instead (it ships
# a CUDA torch), or install a CUDA torch build matching your driver.
#
# Build from the vision/ directory (so it can see requirements.txt):
#   docker build -f detector/Dockerfile -t baby-presence .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY detector/presence_detector.py /app/
# Mount your trained model at /app/baby.pt and set MODEL=/app/baby.pt (see .env.example).
CMD ["python", "presence_detector.py"]

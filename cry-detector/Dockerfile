# YAMNet baby-cry classifier. CPU-only TensorFlow (no GPU needed).
# The model is baked into the image at build time (TFHUB_CACHE_DIR) so the
# container needs no network on start.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV TFHUB_CACHE_DIR=/models/tfhub
RUN mkdir -p /models/tfhub \
    && python -c "import tensorflow_hub as hub; hub.load('https://tfhub.dev/google/yamnet/1')"

COPY yamnet_detect.py /detect.py
ENTRYPOINT ["python3", "-u", "/detect.py"]

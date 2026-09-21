# 3.11, not 3.12: matches cry-detector/Dockerfile (upstream), which doesn't hit
# tensorflow_hub's pkg_resources/setuptools problem on 3.12-slim (see FORK_NOTES.md
# — explicitly installing setuptools on 3.12-slim did not resolve it across three
# rebuilds, including a full uninstall/reinstall, so sidestepping it instead).
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the YAMNet model into the image at build time, so the container needs
# no network at start/restart — only the build itself needs internet (same
# as pulling the base image or pip packages). Without this, hub.load() in
# run.py would re-download it from tfhub.dev on every container start.
ENV TFHUB_CACHE_DIR=/models/tfhub
RUN mkdir -p /models/tfhub \
    && python -c "import tensorflow_hub as hub; hub.load('https://tfhub.dev/google/yamnet/1')"

COPY run.py .

CMD ["python3", "run.py"]

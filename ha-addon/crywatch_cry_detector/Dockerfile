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
COPY run.py .

CMD ["python3", "run.py"]

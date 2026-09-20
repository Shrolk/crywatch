FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# python:3.12-slim's venv/ensurepip no longer bundles setuptools (unlike 3.11 and
# earlier), so pkg_resources — which tensorflow_hub imports at load time — is
# missing unless installed explicitly. Its own RUN step so this can't get lost in
# requirements.txt/layer-cache ambiguity.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY run.py .

CMD ["python3", "run.py"]

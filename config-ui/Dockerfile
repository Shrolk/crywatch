FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py config_ui.html ./

ENV CONFIG_UI_HOST=0.0.0.0
ENV CONFIG_UI_PORT=8090

CMD ["python", "server.py"]

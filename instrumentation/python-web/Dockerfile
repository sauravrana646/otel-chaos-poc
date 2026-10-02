# Operator 0.12x+ copies from /autoinstrumentation into the app volume.
FROM python:3.12-slim-bookworm
WORKDIR /autoinstrumentation
COPY requirements.txt .
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt -t /autoinstrumentation \
  && PYTHONPATH=/autoinstrumentation python -c "import importlib.metadata as m; import opentelemetry; assert m.version('opentelemetry-distro') == '0.51b0'; print(opentelemetry.__file__)"

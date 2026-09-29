# Operator 0.12x+ copies from /autoinstrumentation into the app volume.
FROM python:3.12-slim-bookworm
WORKDIR /autoinstrumentation
COPY requirements.txt .
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt -t /autoinstrumentation \
  && pip install --no-cache-dir opentelemetry-distro -t /autoinstrumentation \
  && PYTHONPATH=/autoinstrumentation python -c "import opentelemetry; print(opentelemetry.__file__)"

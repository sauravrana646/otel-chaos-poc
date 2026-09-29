# Custom Python auto-instrumentation image for OTel Operator injection (web profile).
# Layout must match operator expectations: /otel-auto-instrumentation-python
FROM python:3.12-slim-bookworm
WORKDIR /otel-auto-instrumentation-python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir opentelemetry-distro \
  && opentelemetry-bootstrap -a install || true
# Operator mounts/copies from this path; keep site-packages on PYTHONPATH via sitecustomize.
ENV PYTHONPATH=/otel-auto-instrumentation-python

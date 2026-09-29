FROM python:3.12-slim-bookworm
WORKDIR /otel-auto-instrumentation-python
COPY python-web/requirements.txt /tmp/web-requirements.txt
COPY python-genai/requirements-genai.txt /tmp/genai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/web-requirements.txt \
  && pip install --no-cache-dir -r /tmp/genai-requirements.txt \
  && opentelemetry-bootstrap -a install || true
ENV PYTHONPATH=/otel-auto-instrumentation-python

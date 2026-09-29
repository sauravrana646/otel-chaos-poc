FROM python:3.12-slim-bookworm
WORKDIR /autoinstrumentation
COPY python-web/requirements.txt /tmp/web-requirements.txt
COPY python-genai/requirements-genai.txt /tmp/genai-requirements.txt
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r /tmp/web-requirements.txt -t /autoinstrumentation \
  && pip install --no-cache-dir -r /tmp/genai-requirements.txt -t /autoinstrumentation \
  && pip install --no-cache-dir opentelemetry-distro -t /autoinstrumentation \
  && PYTHONPATH=/autoinstrumentation python -c "import opentelemetry; print(opentelemetry.__file__)"

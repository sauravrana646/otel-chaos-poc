FROM python:3.12-slim-bookworm
WORKDIR /autoinstrumentation
COPY python-genai/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r /tmp/requirements.txt -t /autoinstrumentation \
  && test -f /autoinstrumentation/opentelemetry/instrumentation/openai_v2/__init__.py \
  && test -f /autoinstrumentation/opentelemetry/instrumentation/openai_v2/patch.py \
  && ls /autoinstrumentation/opentelemetry_instrumentation_openai_v2-*.dist-info/entry_points.txt \
  && grep -q OpenAIInstrumentor /autoinstrumentation/opentelemetry_instrumentation_openai_v2-*.dist-info/entry_points.txt \
  && echo "openai_v2 package + entry point OK"

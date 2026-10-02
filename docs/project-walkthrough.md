# Project walkthrough

This POC demonstrates centrally managed OpenTelemetry for Java and Python applications on OrbStack Kubernetes. Application developers write normal HTTP and database code. The platform team owns agent packaging, injection, export configuration, backends, dashboards, and the compatibility pins.

## The complete flow

```text
k6 or curl
   |
   v
Java API ---- JDBC ------------------------------+
   |                                             |
   v                                             v
Python analysis ---- psycopg ----------------> Toxiproxy ----> CloudNativePG/PostgreSQL
   |
   v
Toxiproxy HTTP ----> Python LLM ---- psycopg ----+
                           |
                           +----> local LLM mock (default)
                           +----> OpenRouter (five-request optional smoke)

Injected Java/Python agents
   |
   +---- OTLP traces, metrics, logs ----> OTel Collector
                                             |-- traces --> Tempo
                                             |-- metrics --> Prometheus scrape
                                             +-- logs ----> Loki

CloudNativePG metrics -----------------------> Prometheus
CloudNativePG container logs --> log collector --> Collector --> Loki

Grafana reads Prometheus + Tempo + Loki.
```

One inbound `traceparent` header follows the request through all three services. The auto-instrumentation agents create server, client, and database spans around framework/library calls. The application code does not import OpenTelemetry.

## What each directory owns

- `apps/` contains business behavior. `java-api` is the public entry point, `python-analysis` enriches an item from PostgreSQL, `python-llm` calls a provider and persists an idempotent result, and `llm-mock` provides deterministic OpenAI-compatible responses.
- `instrumentation/` builds the Python agent payloads injected by the OpenTelemetry Operator. The web image covers FastAPI, HTTPX, psycopg, and logging. The GenAI image adds the OpenAI SDK instrumentor.
- `platform/` contains desired Kubernetes state: namespaces, Argo CD Applications, operators, instrumentation rules, CloudNativePG, observability backends, dashboards, and Toxiproxy.
- `tests/k6/` contains arrival-rate load tests. `baseline.js` holds 5 requests per second. `spike.js` runs a 5 RPS warmup, a 50 RPS plateau, and a 5 RPS recovery period with recovery thresholds.
- `cli/poc` is the safety and orchestration layer. It checks the OrbStack context, builds images, requests ordered Argo syncs, runs smoke/load/fault scenarios, verifies evidence, resets faults, and separates stateless teardown from data deletion.
- `compatibility.lock.yaml` is machine-readable input describing the exact component and package pins used by the POC.
- `evidence/` is generated locally. It stores build identities, k6 summaries, smoke responses, trace IDs, and downloaded Tempo traces. It should not contain credentials.

## Application request path

### 1. Java API

`POST /api/recommendations` accepts `request_id`, `item_id`, and an allowlisted `scenario`. It reads the catalog row through Spring JDBC, then calls the analysis service through Spring `RestClient`.

The HTTP client is forced to HTTP/1.1 because the JDK's clear-text HTTP/2 upgrade caused Uvicorn request errors. It has a 3-second connect timeout and 40-second response timeout. PostgreSQL connection, socket, and statement deadlines prevent chaos tests from hanging indefinitely.

### 2. Python analysis

`POST /analyze` reads contextual text with psycopg and calls `/generate` with HTTPX. It closes the database connection before making the LLM call, so a slow provider never holds a database transaction open.

Its default 35-second dependency timeout is deliberately longer than the LLM service's 30-second OpenRouter budget. This ordering lets the inner service finish or fail before the caller gives up.

### 3. Python LLM

`POST /generate` first checks `recommendations` by `request_id`. If a result exists, it returns it, which makes requests idempotent.

The request chooses `mock` by default or `openrouter` explicitly. Both permit three attempts for connection errors, HTTP 429, and HTTP 503 with short backoff. Mock attempts time out after 2 seconds and OpenRouter attempts after 10 seconds, keeping the complete retry budget below the analysis service's 35-second deadline. Both cap the response at 128 tokens.

### 4. LLM mock

The mock implements `/v1/chat/completions` and deterministic modes for normal responses, retry-then-success, persistent 429/503, delay, and server-sent-event streaming. Tests use it so they do not spend money or depend on an external rate limit.

## How automatic instrumentation works

The OpenTelemetry Operator watches pod annotations:

```yaml
instrumentation.opentelemetry.io/inject-java: java
instrumentation.opentelemetry.io/inject-python: python-web
```

Before Kubernetes starts the application container, the admission webhook adds an init container. That init container copies the agent into a shared volume and adds environment variables to start it with the application runtime.

The Java deployment uses the upstream Java agent. Python uses locally built injection images because the exact FastAPI, HTTPX, psycopg, logging, and OpenAI instrumentors must be compatible with Python 3.12 and with each other. This is why simply installing random OTel packages into every application base image is weaker: it couples every image to telemetry packages and still does not centrally select configuration per workload.

Envoy can add useful network-level HTTP metrics and proxy spans, but it cannot see Spring controller names, Python framework routes, JDBC/psycopg operations, or GenAI SDK attributes. It is complementary and is intentionally outside this POC.

Python agents exclude health URLs before export. The central Collector drops Java health and actuator spans by route, so probes do not dominate traces; dashboard queries also exclude probe metrics.

## Collector and backends

The central Collector receives OTLP over ports 4317 and 4318. Its three pipelines are:

- Traces: add the `deployment.environment=poc` resource attribute, batch, export to Tempo, and feed the service-graph/span-metrics connectors.
- Metrics: receive application metrics plus connector-generated metrics and expose them on port 8889 for Prometheus.
- Logs: receive OTLP logs and export them to Loki.

Tempo stores traces. Loki stores logs. Prometheus remains the metrics database. Grafana data sources connect the three so a user can move from a slow metric exemplar to its trace and then to logs around that trace. Tempo's own metrics generator is disabled to avoid duplicate service-graph metrics and failed remote writes.

Python and Java currently emit different HTTP metric names. The overview dashboard queries both families and converts Python milliseconds to seconds before combining latency series.

## PostgreSQL with CloudNativePG

The `Cluster` custom resource asks the CloudNativePG Operator to create one PostgreSQL 17 instance and a 2 GiB `local-path` PVC. This validates restart recovery, not high availability.

The seed Job creates catalog, context, and recommendation tables and inserts three sample items. The application credential lives in a Kubernetes Secret created once by `poc bootstrap`; later bootstraps reuse it instead of silently rotating it.

CloudNativePG exposes built-in metrics through its PodMonitor. A node-level, read-only filelog Collector tails only `otel-poc-apps/poc-postgres-*` container logs and sends them to the central Collector. Application/database correlation happens through client DB spans; PostgreSQL server logs do not automatically contain application trace IDs.

## GitOps deployment

Argo CD owns the desired state. The root Application discovers the child Applications. The CLI still requests child syncs in dependency order because sync waves do not order separate Applications:

1. Namespaces
2. CloudNativePG and OpenTelemetry operators
3. Collector, Tempo, Loki, and database log collector
4. Instrumentation resources and PostgreSQL cluster
5. Toxiproxy
6. Applications
7. Dashboards

Each child uses its declared Git revision or Helm chart version. The CLI never substitutes `HEAD` for Helm chart versions. A failed or unhealthy dependency stops bootstrap. Automated prune and self-heal keep the live cluster aligned after bootstrap.

Grafana's data-source sidecar watches `monitoring`, so the POC data-source ConfigMap is deliberately created there. Dashboards can stay in the POC namespace because the dashboard sidecar watches all namespaces.

## Load and chaos scenarios

- `baseline`: stable 5 RPS with error, latency, dropped-iteration, and check thresholds.
- `spike`: 5 RPS warmup, 50 RPS plateau, then 5 RPS recovery. Recovery has its own error, latency, and response checks.
- `db-outage`: a named Toxiproxy timeout toxic interrupts database calls.
- `latency`: a named Toxiproxy toxic adds 500 ms to Python-to-LLM calls.
- `db-restart`: deletes one CloudNativePG pod and waits for the same Cluster resource/PVC to recover.
- `app-restart`: resolves one running analysis pod by name and deletes only that pod.
- Mock request scenarios: `retry-success`, `retry-exhaust`, and `stream` are exercised through `poc smoke --mock --scenario ...`.

Before adding a persistent Toxiproxy fault, the CLI creates an independent cleanup Job. The Job removes that named toxic after a fixed deadline even if the operator's terminal disconnects. `poc reset` also removes known toxics by name and verifies they are absent.

## Safe command sequence

```bash
./cli/poc doctor
./tests/static/verify.sh
./cli/poc build

# Commit and push the immutable image references written by the build command.
./cli/poc bootstrap
./cli/poc smoke --mock
./cli/poc smoke --mock --scenario retry-success
./cli/poc smoke --mock --scenario retry-exhaust
./cli/poc smoke --mock --scenario stream
./cli/poc retry --provider mock --scenario success
./cli/poc retry --provider mock --scenario exhaust
./cli/poc retry --provider openrouter --scenario live
./cli/poc verify
```

For load, port-forward the Java service and run one scenario at a time:

```bash
kubectl --context orbstack -n otel-poc-apps port-forward svc/java-api 8080:8080
./cli/poc load --scenario baseline
./cli/poc load --scenario spike
./cli/poc load --scenario constant --provider mock --rps 1 --duration 30s
./cli/poc load --scenario constant --provider mock --rps 2 --duration 1m
./cli/poc load --scenario constant --provider openrouter --rps 3 --duration 2m
```

For a fault, start traffic, activate one scenario, and confirm both failure and recovery:

```bash
POC_FAULT_TTL_SECONDS=60 ./cli/poc fault --scenario latency --provider mock
./cli/poc reset
./cli/poc verify
```

`poc destroy` removes stateless application/test resources and retains PostgreSQL, Tempo, Loki, operators, and PVCs. `poc destroy --data` requires a different confirmation phrase and explicitly removes data-bearing resources.

## What the POC proves—and what it does not

It proves centrally injected application-level telemetry, propagation across Java/Python services, client-side database spans, GenAI SDK telemetry, PostgreSQL platform monitoring, and repeatable local failure tests.

It does not prove multi-node availability, PostgreSQL failover, backup/restore, production security, production cardinality/cost controls, or visibility inside OpenRouter's infrastructure. Those require separate production design and tests.

# otel-chaos-poc

Local OrbStack Kubernetes POC for **automatic OpenTelemetry tracing**, **CloudNativePG**, **Argo CD GitOps**, and **repeatable chaos / load tests**, with correlated metrics, traces, and logs in Grafana.

The platform owns instrumentation packaging, injection, configuration, and compatibility. Application source contains business behavior and resilience logic only — no OTel SDK initialization, tracing decorators, or custom spans.

## What this demonstrates

- End-to-end traces: Java API → Python analysis → LLM service → PostgreSQL client spans (+ GenAI outbound calls)
- OpenTelemetry Operator auto-injection (Java + custom Python images)
- CloudNativePG-managed PostgreSQL (metrics, structured logs, restart recovery)
- Tempo + Jaeger + Loki beside existing Grafana / Prometheus
- k6 load + Toxiproxy faults + scoped pod restarts
- Bounded OpenRouter smoke (optional) vs local deterministic LLM mock

## Repository layout

```text
apps/                 Sample services (Java API, Python analysis, LLM, mock)
db/                   Schema and seed Job assets
platform/             Argo CD apps, operators, CNPG, OTel, Tempo/Loki, Toxiproxy
instrumentation/      Custom Python auto-instrumentation image definitions
tests/                k6 scripts and fault Jobs
cli/                  `poc` command interface
docs/                 Architecture and design decisions
compatibility.lock.yaml
```

## Prerequisites

- OrbStack Kubernetes (ARM64), ~**12 GiB** memory recommended
- Existing cluster components reused by this POC: **Argo CD**, **Grafana**, **Prometheus** (kube-prometheus-stack)
- Docker (OrbStack) for local ARM64 image builds
- Argo CD repository credentials for this repository when it is private; configure them as an Argo CD repository Secret or through the Argo CD UI, and keep the credential outside Git
- Optional: OpenRouter API key + model ID for real-model smoke

Recheck cluster state before changing anything:

```bash
./cli/poc doctor
```

## Quick start (high level)

```bash
# 1. Pin / review versions
cat compatibility.lock.yaml

# 2. Build local ARM64 images (immutable tags)
./cli/poc build

# 3. Bootstrap Argo CD apps in documented order
./cli/poc bootstrap

# 4. Mock smoke (full trace assertion)
./cli/poc smoke --mock

# 5. Load / fault scenarios (one at a time)
./cli/poc load --scenario spike
./cli/poc load --scenario constant --provider mock --rps 2 --duration 1m
./cli/poc fault --scenario db-outage --provider mock
./cli/poc retry --provider mock --scenario success
./cli/poc retry --provider openrouter --scenario live

# 6. Optional real-model smoke
./cli/poc smoke --openrouter

# Update or verify the OpenRouter model/key independently
OPENROUTER_API_KEY='new-key' ./cli/poc openrouter update --model openai/gpt-4o-mini
OPENROUTER_API_KEY='rotated-key' ./cli/poc openrouter update
./cli/poc openrouter update --model anthropic/claude-sonnet-4
./cli/poc openrouter verify

# 7. Verify + reset fault state (keeps CNPG data)
./cli/poc verify
./cli/poc reset
```

Provider selection is per request. Commands use the mock unless `--provider openrouter` is present; selecting OpenRouter does not mutate or roll out the application Deployment.

`openrouter update` changes only the values provided and reuses the other value
from the existing Secret. Supply API keys through `OPENROUTER_API_KEY` so they
do not appear in shell command arguments. Both `update` and `verify` compare the
Secret with every running `python-llm` pod, then print the model and a masked
key. OpenRouter load, retry, fault, and smoke commands perform the same exact
projection check once and proceed immediately when it passes. Test commands do
not update the Secret or wait for propagation; run `openrouter update` first
when changing credentials.

Stateless teardown retains PostgreSQL and observability data. Data deletion is a separate explicit operation:

```bash
./cli/poc destroy          # remove stateless POC apps; retain data
./cli/poc destroy --data   # explicit confirmation; remove POC PVC-backed data
```

## Sample request flow

```text
k6 → Java POST /api/recommendations
       → JDBC catalog read
       → Python POST /analyze
            → psycopg context read
            → LLM POST /generate
                 → mock or OpenRouter (/v1/chat/completions)
                 → psycopg idempotent result write
```

Public contract fields: `request_id`, `item_id`, `scenario` (allowlisted). Health endpoints are separate and excluded from tracing dashboards.

## Namespaces

| Namespace | Contents |
|-----------|----------|
| `otel-poc-system` | OpenTelemetry Operator |
| `otel-poc-cnpg-system` | CloudNativePG Operator |
| `otel-poc-observability` | Collector, Tempo, Jaeger, Loki, DB log collector |
| `otel-poc-apps` | Apps, CNPG cluster, mock, Toxiproxy |
| `otel-poc-tests` | k6 / fault Jobs |

## Documentation

- [Architecture](docs/architecture.md)
- [Design decisions](docs/design-decisions.md)
- [Implementation plan](docs/implementation-plan.md)
- [Project walkthrough](docs/project-walkthrough.md)
- [Compatibility lock](compatibility.lock.yaml)

## Boundaries

Single-node development POC. Not a claim of production performance, host HA, replica promotion, backup/restore readiness, or visibility into external LLM provider internals. No Envoy, service mesh, or privileged chaos daemon in the initial scope.

## Status

The pinned stack has passed a clean Argo CD reconciliation and the normal, retry-success, retry-exhaust, and streaming trace assertions on OrbStack. The k6 load and Toxiproxy fault acceptance suite remains a separate, intentionally disruptive validation step.

## Explore traces in Grafana

Use **Drilldown → Traces** for the queryless trace investigation UI. Select
`Tempo-POC`, then choose **Rate**, **Errors**, or **Duration** and filter by
service, span, or attribute. Open an individual result when you need its full
waterfall and span attributes.

Tempo's `local-blocks` processor is enabled specifically for the TraceQL
metrics queries used by Traces Drilldown. Prometheus span metrics and service
graphs continue to come from the central OpenTelemetry Collector, avoiding
duplicate metric series.

## Explore traces in Jaeger UI

The collector sends each trace to both Tempo and Jaeger. Start the local UI:

```bash
kubectl --context orbstack -n otel-poc-observability port-forward svc/jaeger 16686:16686
```

Open [Jaeger UI](http://localhost:16686), select `java-api` under **Service**,
and search for a recent request. You can also open a known trace directly at
`http://localhost:16686/trace/<trace-id>`. Jaeger stores spans in Badger on a
5 GiB `local-path` PVC (`jaeger-data`), with a 24-hour TTL. Its traces survive
Jaeger pod restarts while that PVC remains. The local Badger store is limited
to one Jaeger replica in this POC.

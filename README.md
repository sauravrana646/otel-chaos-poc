# otel-chaos-poc

Local OrbStack Kubernetes POC for **automatic OpenTelemetry tracing**, **CloudNativePG**, **Argo CD GitOps**, and **repeatable chaos / load tests**, with correlated metrics, traces, and logs in Grafana.

The platform owns instrumentation packaging, injection, configuration, and compatibility. Application source contains business behavior and resilience logic only — no OTel SDK initialization, tracing decorators, or custom spans.

## What this demonstrates

- End-to-end traces: Java API → Python analysis → LLM service → PostgreSQL client spans (+ GenAI outbound calls)
- OpenTelemetry Operator auto-injection (Java + custom Python images)
- CloudNativePG-managed PostgreSQL (metrics, structured logs, restart recovery)
- Tempo + Loki beside existing Grafana / Prometheus
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

# 7. Verify + reset fault state (keeps CNPG data)
./cli/poc verify
./cli/poc reset
```

Provider selection is per request. Commands use the mock unless `--provider openrouter` is present; selecting OpenRouter does not mutate or roll out the application Deployment.

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
| `otel-poc-observability` | Collector, Tempo, Loki, DB log collector |
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

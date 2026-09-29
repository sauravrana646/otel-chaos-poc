# Design decisions

Record of choices for the OrbStack OpenTelemetry + CloudNativePG + chaos POC. Update this file when a decision changes.

## DD-001: Tempo instead of Jaeger

**Decision:** Deploy Tempo as the sole trace backend.

**Why:** Grafana already runs in the cluster. The POC needs metrics↔traces↔logs navigation. One backend reduces memory and operational surface on a single OrbStack node.

**Not chosen:** Jaeger (fine for traces/SPM; redundant with Grafana+Tempo for this demo).

## DD-002: Platform-owned auto-instrumentation

**Decision:** No OTel imports, SDK init, or tracing annotations in application source. Injection via OpenTelemetry Operator only.

**Why:** Demonstrates “platform owns telemetry packaging and compatibility”; apps stay focused on business + resilience.

**Implication:** Custom Python injection images are required for Python 3.12 + glibc + FastAPI/HTTPX/psycopg/GenAI packages. Java uses the pinned upstream auto-instrumentation image.

## DD-003: Reuse Argo CD, Grafana, Prometheus

**Decision:** Do not install a second GitOps or metrics stack.

**Why:** Matches the shared OrbStack environment; POC labels ServiceMonitors/PodMonitors with `release: kube-prometheus-stack` so existing Prometheus scrapes them.

**Boundary:** `poc destroy` must never remove shared Argo CD / Grafana / Prometheus.

## DD-004: CloudNativePG over hand-managed StatefulSet

**Decision:** PostgreSQL via `postgresql.cnpg.io/v1` Cluster; operator via official Helm chart.

**Why:** Demonstrates operator lifecycle, built-in metrics exporter, structured JSON logs, and restart recovery with PVC retention.

**Boundary:** Single instance initially — restart recovery, not replica promotion/HA. All replicas on one node would still share host failure risk.

## DD-005: Toxiproxy instead of mesh / privileged chaos

**Decision:** Namespace-scoped Toxiproxy for DB and LLM HTTP paths; k6 + pod deletes for the rest.

**Why:** Avoid Envoy, service mesh, and privileged chaos daemons on a shared laptop cluster. Keep fault blast radius inside POC namespaces.

**Consistency:** Route selected connections through proxies in both baseline and fault runs.

## DD-006: Local LLM mock + bounded OpenRouter

**Decision:** Default load/chaos against a deterministic OpenAI-compatible mock. OpenRouter only for ≤5 smoke requests, concurrency 1, no retries, no chaos.

**Why:** Repeatable assertions (retry counts, latency) without external rate limits. Real-model path proves GenAI instrumentation without blocking the suite if the key is absent (report incomplete explicitly; never silent mock substitution).

## DD-007: Retries only in the LLM service (mock profile)

**Decision:** Max 3 attempts, backoff 100ms then 200ms + jitter, 2s per-attempt timeout; retry 429/503 and selected transient connection errors. Disable SDK built-in retries. No automatic DB write retries. OpenRouter: single attempt, 30s timeout.

**Why:** Makes retry spans and exhaustion behavior assertable under one inbound trace.

## DD-008: Database transactions vs inference

**Decision:** Close DB transactions before LLM calls; do not hold locks during inference. Idempotent recommendation persistence on `request_id`.

**Why:** Avoid lock contention under load and duplicate rows under retries/concurrency.

## DD-009: Namespaces and operators isolated from existing demos

**Decision:** Dedicated `otel-poc-*` namespaces; webhook injection limited to the POC app namespace; verify no foreign APM injectors.

**Why:** Shared cluster already has other workloads, Kyverno policies, and a New Relic operator without active instrumentation resources.

## DD-010: Memory budget and replica defaults

**Decision:** Target OrbStack at 12 GiB. Steady-state POC requests aimed below ~4 GiB. Default two app replicas, one each of PG/mock/Toxiproxy/Collector/Tempo/Loki. One fault scenario at a time.

**Why:** Planning observed ~8 GiB node with ~4.5 GiB already used. Dual replicas support pod-restart scenarios; Phase A may temporarily run 1 replica if headroom is tight.

## DD-011: GitOps sequencing via CLI, not cross-app sync waves

**Decision:** `poc bootstrap` syncs Applications in order and waits for health. Sync waves only within an Application.

**Why:** Argo CD sync waves do not order unrelated Applications (operators before CRDs consumers, etc.).

## DD-012: Secrets and telemetry redaction

**Decision:** Credentials only in Kubernetes Secrets (not Git). Keep prompts, completions, API keys, auth headers, and SQL parameter values out of telemetry.

**Why:** Local POC still handles real OpenRouter keys and should model safe defaults.

## DD-013: Local immutable image tags

**Decision:** Build ARM64 images locally with unique immutable tags; `imagePullPolicy: IfNotPresent`; record digests in build evidence / compatibility process.

**Why:** OrbStack shares local images with the cluster; reproducible demos need pinned identities, not `:latest`.

## DD-014: Completion vs OpenRouter availability

**Decision:** Mock suite is required for POC completion. OpenRouter smoke is required when key+model are configured; otherwise mark real-model verification incomplete without failing the mock path.

**Why:** Aligns completion criteria with environments that cannot call external providers.

## DD-015: Force Java RestClient to HTTP/1.1

**Decision:** Configure JDK `HttpClient` with `Version.HTTP_1_1` via `RestClientCustomizer`.

**Why:** Default JDK client sends `Connection: Upgrade` / `Upgrade: h2c`. Uvicorn/FastAPI then returns 422 with an empty body (`Field required`), breaking Java→Python calls under auto-instrumentation.

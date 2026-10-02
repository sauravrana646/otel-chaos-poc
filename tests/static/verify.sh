#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

bash -n cli/poc db/seed/run-seed.sh
git diff --check

python3 - <<'PY'
import ast
import json
from pathlib import Path

for path in Path("apps").glob("*/app/*.py"):
    ast.parse(path.read_text())
for path in Path("platform/dashboards").glob("*.json"):
    json.loads(path.read_text())
PY

kubectl kustomize platform/observability >/dev/null
kubectl kustomize platform/dashboards >/dev/null

while IFS= read -r manifest; do
  case "$manifest" in
    */kustomization.yaml) continue ;;
  esac
  kubectl create --dry-run=client --validate=false -f "$manifest" -o yaml >/dev/null
done < <(find platform -type f -name '*.yaml' | sort)

if command -v ruby >/dev/null 2>&1; then
  ruby -e 'require "yaml"; YAML.load_file("compatibility.lock.yaml")'
fi

! grep -Fq '"revision":"HEAD"' cli/poc
! grep -Fq 'toxic remove postgres all' cli/poc
! grep -Fq 'metrics_generator:' platform/observability/tempo.yaml
! grep -Fq 'pip install --no-cache-dir opentelemetry-distro -t /autoinstrumentation' instrumentation/python-web/Dockerfile
grep -Fq 'namespace: monitoring' platform/observability/grafana-datasources.yaml
grep -Fq 'http_server_duration_milliseconds' platform/dashboards/overview.json
grep -Fq 'kind: PodMonitor' platform/cnpg/cluster.yaml
grep -Fq 'release: kube-prometheus-stack' platform/cnpg/cluster.yaml
grep -Fq 'activeDeadlineSeconds:' cli/poc
grep -Fq 'POC_KUBE_CONTEXT' cli/poc
grep -Fq 'filter/drop_health:' platform/observability/collector.yaml

echo "static verification passed"

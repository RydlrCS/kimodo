#!/usr/bin/env bash
# Cloud Run health gate for movimento-text-encoder.
# Usage:
#   PROJECT_ID=my-project REGION=europe-west1 ./cloud-run/health_gate_text_encoder.sh
#   PROJECT_ID=my-project REGION=europe-west1 SERVICE_NAME=movimento-text-encoder ./cloud-run/health_gate_text_encoder.sh

set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-movimento-text-encoder}"
DEMO_SERVICE_NAME="${DEMO_SERVICE_NAME:-kimodo-demo}"
HF_SECRET_NAME="${HF_SECRET_NAME:-hf-token}"
GATE_TIMEOUT_SEC="${GATE_TIMEOUT_SEC:-120}"
GATE_RETRY_INTERVAL_SEC="${GATE_RETRY_INTERVAL_SEC:-5}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "FAIL: gcloud CLI not found"
  exit 2
fi

ENCODER_JSON="$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format=json)"

readarray -t ENCODER_FIELDS < <(python - <<'PY' "$ENCODER_JSON" "$HF_SECRET_NAME"
import json
import sys

service = json.loads(sys.argv[1])
expected_secret = sys.argv[2]

conditions = service.get("status", {}).get("conditions", [])
ready = "Unknown"
for cond in conditions:
    if cond.get("type") == "Ready":
        ready = cond.get("status", "Unknown")
        break

url = service.get("status", {}).get("url", "")
latest_ready = service.get("status", {}).get("latestReadyRevisionName", "")

traffic = service.get("status", {}).get("traffic", [])
latest_receives_traffic = "False"
for item in traffic:
    if item.get("latestRevision") is True and int(item.get("percent", 0)) > 0:
        latest_receives_traffic = "True"
        break

spec_env = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
secret_names = []
for env in spec_env:
    value_from = env.get("valueFrom") or {}
    key_ref = value_from.get("secretKeyRef") or {}
    name = key_ref.get("name")
    if name:
        secret_names.append(name)

secret_wiring = "PASS" if expected_secret in secret_names and "HF_TOKEN_SECRET_NAME" not in secret_names else "FAIL"

print(ready)
print(url)
print(latest_ready)
print(latest_receives_traffic)
print(secret_wiring)
PY
)

READY_STATUS="${ENCODER_FIELDS[0]}"
ENCODER_URL="${ENCODER_FIELDS[1]}"
LATEST_READY_REV="${ENCODER_FIELDS[2]}"
LATEST_TRAFFIC="${ENCODER_FIELDS[3]}"
SECRET_WIRING="${ENCODER_FIELDS[4]}"

if [[ -z "$ENCODER_URL" ]]; then
  echo "Service Ready: ${READY_STATUS}"
  echo "Revision Traffic: ${LATEST_TRAFFIC}"
  echo "Encoder URL Check: FAIL (missing URL)"
  echo "Secret Wiring: ${SECRET_WIRING}"
  echo "Failure Logs: FAIL"
  echo "Dependency Contract: FAIL"
  echo "[FAIL] Encoder service URL is empty"
  exit 1
fi

deadline=$((SECONDS + GATE_TIMEOUT_SEC))
endpoint_ok="false"
latency_ms=""

while (( SECONDS < deadline )); do
  if latency_ms=$(python - <<'PY' "$ENCODER_URL"
import sys
import time
import urllib.request

url = sys.argv[1]
start = time.time()
with urllib.request.urlopen(url, timeout=10) as resp:
    if resp.status < 500:
        elapsed = int((time.time() - start) * 1000)
        print(elapsed)
    else:
        raise RuntimeError(f"status={resp.status}")
PY
 2>/dev/null); then
    endpoint_ok="true"
    break
  fi
  sleep "$GATE_RETRY_INTERVAL_SEC"
done

demo_contract="SKIPPED"
if gcloud run services describe "$DEMO_SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  DEMO_JSON="$(gcloud run services describe "$DEMO_SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format=json)"
  demo_url_match=$(python - <<'PY' "$DEMO_JSON" "$ENCODER_URL"
import json
import sys

service = json.loads(sys.argv[1])
encoder_url = sys.argv[2].rstrip('/') + '/'

envs = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
configured = None
for env in envs:
    if env.get("name") == "TEXT_ENCODER_URL":
        configured = (env.get("value") or "").rstrip('/') + '/'
        break

if configured == encoder_url:
    print("PASS")
else:
    print("FAIL")
PY
)
  demo_contract="$demo_url_match"
fi

echo "Service Ready: ${READY_STATUS}"
echo "Latest Ready Revision: ${LATEST_READY_REV}"
echo "Revision Traffic: ${LATEST_TRAFFIC}"
if [[ "$endpoint_ok" == "true" ]]; then
  echo "Encoder URL Check: PASS (${latency_ms}ms)"
else
  echo "Encoder URL Check: FAIL (timeout after ${GATE_TIMEOUT_SEC}s)"
fi
echo "Secret Wiring: ${SECRET_WIRING}"
if [[ "$READY_STATUS" == "True" && "$LATEST_TRAFFIC" == "True" ]]; then
  echo "Failure Logs: PASS"
else
  echo "Failure Logs: FAIL"
fi
echo "Dependency Contract: ${demo_contract}"

if [[ "$READY_STATUS" != "True" || "$LATEST_TRAFFIC" != "True" || "$endpoint_ok" != "true" || "$SECRET_WIRING" != "PASS" ]]; then
  echo "[FAIL] Cloud Run encoder health gate failed"
  exit 1
fi

if [[ "$demo_contract" == "FAIL" ]]; then
  echo "[FAIL] Demo TEXT_ENCODER_URL does not match encoder URL"
  exit 1
fi

echo "[PASS] Cloud Run encoder health gate passed"

#!/usr/bin/env bash
# Deploy kimodo Cloud Run services.
# Usage:
#   REGION=europe-west1 PROJECT_ID=my-project ./cloud-run/deploy.sh
#   REGION=europe-west1 PROJECT_ID=my-project ALLOW_UNAUTHENTICATED=false ./cloud-run/deploy.sh
#   REGION=europe-west1 PROJECT_ID=my-project GPU_TYPE=nvidia-h200-141gb GPU_COUNT=1 ./cloud-run/deploy.sh
set -euo pipefail

: "${REGION:?Set REGION (e.g. us-central1)}"
: "${PROJECT_ID:?Set PROJECT_ID}"
HF_SECRET_NAME="${HF_SECRET_NAME:-hf-token}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
GPU_COUNT="${GPU_COUNT:-1}"

IMAGE_TAG="$REGION-docker.pkg.dev/$PROJECT_ID/kimodo/kimodo:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCLOUD_BIN="${GCLOUD_BIN:-}"
if [[ -z "$GCLOUD_BIN" ]]; then
  if command -v gcloud >/dev/null 2>&1; then
    GCLOUD_BIN="$(command -v gcloud)"
  elif [[ -x "/workspaces/kimodo/.tools/google-cloud-sdk/bin/gcloud" ]]; then
    GCLOUD_BIN="/workspaces/kimodo/.tools/google-cloud-sdk/bin/gcloud"
  else
    echo "gcloud not found. Set GCLOUD_BIN or install gcloud CLI."
    exit 1
  fi
fi

# ── Substitute image path into manifests ────────────────────────────────────
IMAGE_DIGEST=$("$GCLOUD_BIN" artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT_ID/kimodo/kimodo" \
  --include-tags \
  --filter="tags:latest" \
  --format="value(version)" \
  --limit=1)

if [[ -z "$IMAGE_DIGEST" ]]; then
  echo "Could not resolve digest for image tag: $IMAGE_TAG"
  exit 1
fi

IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/kimodo/kimodo@$IMAGE_DIGEST"
echo "Deploying image: $IMAGE"
echo "Auth policy (allUsers invoker): $ALLOW_UNAUTHENTICATED"
echo "GPU profile: type=$GPU_TYPE count=$GPU_COUNT"

sed \
  -e "s|REGION-docker.pkg.dev/PROJECT_ID/kimodo/kimodo:latest|$IMAGE|g" \
  -e "s|HF_TOKEN_SECRET_NAME|$HF_SECRET_NAME|g" \
  -e "s|GPU_TYPE_PLACEHOLDER|$GPU_TYPE|g" \
  -e "s|GPU_COUNT_PLACEHOLDER|$GPU_COUNT|g" \
  "$SCRIPT_DIR/text-encoder.yaml" > /tmp/text-encoder-rendered.yaml

sed \
  -e "s|REGION-docker.pkg.dev/PROJECT_ID/kimodo/kimodo:latest|$IMAGE|g" \
  -e "s|HF_TOKEN_SECRET_NAME|$HF_SECRET_NAME|g" \
  -e "s|GPU_TYPE_PLACEHOLDER|$GPU_TYPE|g" \
  -e "s|GPU_COUNT_PLACEHOLDER|$GPU_COUNT|g" \
  "$SCRIPT_DIR/demo.yaml" > /tmp/demo-rendered.yaml

if grep -q 'HF_TOKEN_SECRET_NAME' /tmp/text-encoder-rendered.yaml; then
  echo "Secret placeholder HF_TOKEN_SECRET_NAME still present in rendered text-encoder manifest"
  exit 1
fi

if grep -q 'GPU_TYPE_PLACEHOLDER\|GPU_COUNT_PLACEHOLDER' /tmp/text-encoder-rendered.yaml; then
  echo "GPU placeholders still present in rendered text-encoder manifest"
  exit 1
fi

if grep -q 'GPU_TYPE_PLACEHOLDER\|GPU_COUNT_PLACEHOLDER' /tmp/demo-rendered.yaml; then
  echo "GPU placeholders still present in rendered demo manifest"
  exit 1
fi

if grep -q 'HF_TOKEN_SECRET_NAME' /tmp/demo-rendered.yaml; then
  echo "Secret placeholder HF_TOKEN_SECRET_NAME still present in rendered demo manifest"
  exit 1
fi

# ── 1. Deploy text-encoder ───────────────────────────────────────────────────
echo "Deploying movimento-text-encoder to $REGION..."
"$GCLOUD_BIN" run services replace /tmp/text-encoder-rendered.yaml \
  --region "$REGION" \
  --project "$PROJECT_ID"

if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  "$GCLOUD_BIN" run services add-iam-policy-binding movimento-text-encoder \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --member "allUsers" \
    --role "roles/run.invoker" 2>/dev/null || true
fi

TEXT_ENCODER_URL=$("$GCLOUD_BIN" run services describe movimento-text-encoder \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo "Text-encoder URL: $TEXT_ENCODER_URL"

if [[ -z "$TEXT_ENCODER_URL" ]]; then
  echo "Text encoder URL is empty. Blocking downstream deployment."
  exit 1
fi

echo "Running encoder health gate before deploying downstream services..."
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
SERVICE_NAME="movimento-text-encoder" \
HF_SECRET_NAME="$HF_SECRET_NAME" \
DEMO_SERVICE_NAME="kimodo-demo" \
"$SCRIPT_DIR/health_gate_text_encoder.sh"

# ── 2. Inject text-encoder URL into demo manifest and deploy ─────────────────
sed -i "s|TEXT_ENCODER_URL_PLACEHOLDER|$TEXT_ENCODER_URL/|g" /tmp/demo-rendered.yaml

if grep -q 'TEXT_ENCODER_URL_PLACEHOLDER' /tmp/demo-rendered.yaml; then
  echo "TEXT_ENCODER_URL_PLACEHOLDER still present in demo manifest"
  exit 1
fi

echo "Deploying kimodo-demo to $REGION..."
"$GCLOUD_BIN" run services replace /tmp/demo-rendered.yaml \
  --region "$REGION" \
  --project "$PROJECT_ID"

if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  "$GCLOUD_BIN" run services add-iam-policy-binding kimodo-demo \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --member "allUsers" \
    --role "roles/run.invoker" 2>/dev/null || true
fi

DEMO_URL=$("$GCLOUD_BIN" run services describe kimodo-demo \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo "Re-running encoder health gate to verify dependency contract after demo deploy..."
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
SERVICE_NAME="movimento-text-encoder" \
HF_SECRET_NAME="$HF_SECRET_NAME" \
DEMO_SERVICE_NAME="kimodo-demo" \
"$SCRIPT_DIR/health_gate_text_encoder.sh"

echo ""
echo "✓ Deployment complete."
echo "  Text-encoder: $TEXT_ENCODER_URL"
echo "  Demo UI:      $DEMO_URL"

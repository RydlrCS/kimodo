#!/usr/bin/env bash
# Deploy kimodo Cloud Run services.
# Usage: REGION=us-central1 PROJECT_ID=my-project ./cloud-run/deploy.sh
set -euo pipefail

: "${REGION:?Set REGION (e.g. us-central1)}"
: "${PROJECT_ID:?Set PROJECT_ID}"

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

sed \
  -e "s|REGION-docker.pkg.dev/PROJECT_ID/kimodo/kimodo:latest|$IMAGE|g" \
  "$SCRIPT_DIR/text-encoder.yaml" > /tmp/text-encoder-rendered.yaml

sed \
  -e "s|REGION-docker.pkg.dev/PROJECT_ID/kimodo/kimodo:latest|$IMAGE|g" \
  "$SCRIPT_DIR/demo.yaml" > /tmp/demo-rendered.yaml

# ── 1. Deploy text-encoder ───────────────────────────────────────────────────
echo "Deploying kimodo-text-encoder to $REGION..."
"$GCLOUD_BIN" run services replace /tmp/text-encoder-rendered.yaml \
  --region "$REGION" \
  --project "$PROJECT_ID"

"$GCLOUD_BIN" run services add-iam-policy-binding kimodo-text-encoder \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --member "allUsers" \
  --role "roles/run.invoker" 2>/dev/null || true

TEXT_ENCODER_URL=$("$GCLOUD_BIN" run services describe kimodo-text-encoder \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo "Text-encoder URL: $TEXT_ENCODER_URL"

# ── 2. Inject text-encoder URL into demo manifest and deploy ─────────────────
sed -i "s|TEXT_ENCODER_URL_PLACEHOLDER|$TEXT_ENCODER_URL/|g" /tmp/demo-rendered.yaml

echo "Deploying kimodo-demo to $REGION..."
"$GCLOUD_BIN" run services replace /tmp/demo-rendered.yaml \
  --region "$REGION" \
  --project "$PROJECT_ID"

"$GCLOUD_BIN" run services add-iam-policy-binding kimodo-demo \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --member "allUsers" \
  --role "roles/run.invoker" 2>/dev/null || true

DEMO_URL=$("$GCLOUD_BIN" run services describe kimodo-demo \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo ""
echo "✓ Deployment complete."
echo "  Text-encoder: $TEXT_ENCODER_URL"
echo "  Demo UI:      $DEMO_URL"

#!/usr/bin/env bash
# Deploy movimento text encoder service to Cloud Run.
# Usage:
#   PROJECT_ID=movimento-text-encoder REGION=europe-west1 HF_TOKEN=hf_xxx ./cloud-run/deploy_text_encoder.sh
#   PROJECT_ID=movimento-text-encoder REGION=europe-west1 HF_SECRET_NAME=hf-token ALLOW_UNAUTHENTICATED=false ./cloud-run/deploy_text_encoder.sh
#   PROJECT_ID=movimento-text-encoder REGION=europe-west1 GPU_TYPE=nvidia-h200-141gb GPU_COUNT=1 ./cloud-run/deploy_text_encoder.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID (e.g. movimento-text-encoder)}"
REGION="${REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-movimento-text-encoder}"
REPO_NAME="${REPO_NAME:-kimodo}"
IMAGE_NAME="${IMAGE_NAME:-kimodo}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
HF_SECRET_NAME="${HF_SECRET_NAME:-hf-token}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
GPU_COUNT="${GPU_COUNT:-1}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI not found. Run this script from Cloud Shell or install gcloud."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG"

echo "[deploy] project=$PROJECT_ID region=$REGION service=$SERVICE_NAME image=$IMAGE_URI"
echo "[deploy] auth policy (allUsers invoker): $ALLOW_UNAUTHENTICATED"
echo "[deploy] gpu profile: type=$GPU_TYPE count=$GPU_COUNT"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "[deploy] enabling required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com >/dev/null

if ! gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" >/dev/null 2>&1; then
  echo "[deploy] creating Artifact Registry repo: $REPO_NAME"
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Movimento container images"
fi

if [[ -n "${HF_TOKEN:-}" ]]; then
  if ! gcloud secrets describe "$HF_SECRET_NAME" >/dev/null 2>&1; then
    echo "[deploy] creating secret: $HF_SECRET_NAME"
    gcloud secrets create "$HF_SECRET_NAME" --replication-policy="automatic" >/dev/null
  fi
  echo "[deploy] updating secret version: $HF_SECRET_NAME"
  printf '%s' "$HF_TOKEN" | gcloud secrets versions add "$HF_SECRET_NAME" --data-file=- >/dev/null
else
  echo "[deploy] HF_TOKEN env var not set; expecting existing secret '$HF_SECRET_NAME'"
  gcloud secrets describe "$HF_SECRET_NAME" >/dev/null
fi

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "[deploy] granting Secret Manager access to runtime SA: $RUNTIME_SA"
gcloud secrets add-iam-policy-binding "$HF_SECRET_NAME" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "[deploy] building image: $IMAGE_URI"
gcloud builds submit "$REPO_ROOT" --config "$REPO_ROOT/cloudbuild.yaml" --substitutions="_IMAGE=$IMAGE_URI"

echo "[deploy] rendering Cloud Run manifest"
RENDERED_MANIFEST="/tmp/${SERVICE_NAME}-rendered.yaml"
sed \
  -e "s|REGION-docker.pkg.dev/PROJECT_ID/kimodo/kimodo:latest|$IMAGE_URI|g" \
  -e "s|HF_TOKEN_SECRET_NAME|$HF_SECRET_NAME|g" \
  -e "s|GPU_TYPE_PLACEHOLDER|$GPU_TYPE|g" \
  -e "s|GPU_COUNT_PLACEHOLDER|$GPU_COUNT|g" \
  "$REPO_ROOT/cloud-run/text-encoder.yaml" > "$RENDERED_MANIFEST"

if grep -q 'HF_TOKEN_SECRET_NAME\|GPU_TYPE_PLACEHOLDER\|GPU_COUNT_PLACEHOLDER' "$RENDERED_MANIFEST"; then
  echo "[deploy] rendered manifest still contains placeholders"
  exit 1
fi

echo "[deploy] applying Cloud Run service"
gcloud run services replace "$RENDERED_MANIFEST" --region "$REGION" --project "$PROJECT_ID"

if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  echo "[deploy] allowing unauthenticated invoke"
  gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --member "allUsers" \
    --role "roles/run.invoker" >/dev/null || true
fi

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')"
echo "[deploy] text encoder url: ${SERVICE_URL}/"

#!/usr/bin/env bash
# Sync local repository content to a Hugging Face bucket.
#
# Usage examples:
#   HF_TOKEN=hf_xxx ./cloud-run/sync_hf_bucket.sh
#   ./cloud-run/sync_hf_bucket.sh --source ./kimodo --dry-run
#   ./cloud-run/sync_hf_bucket.sh --dest hf://buckets/rydlrKE/movimento-bucket --include-build

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="hf://buckets/rydlrKE/movimento-bucket/kimodo"
SOURCE="."
DRY_RUN=false
INCLUDE_BUILD=false
VERBOSE=false
DELETE_MISSING=false
FILTER_FILE="$SCRIPT_DIR/hf_sync_filters.txt"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      DEST="$2"
      shift 2
      ;;
    --source)
      SOURCE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --include-build)
      INCLUDE_BUILD=true
      shift
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --delete)
      DELETE_MISSING=true
      shift
      ;;
    --filter-file)
      FILTER_FILE="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Sync local files to a Hugging Face bucket.

Options:
  --source <path>         Local source directory (default: .)
  --dest <hf://...>       HF bucket destination (default: hf://buckets/rydlrKE/movimento-bucket)
  --dry-run               Print planned actions without uploading
  --include-build         Include build/ artifacts (excluded by default)
  --verbose               Enable verbose sync output
  --delete                Delete destination files missing from source
  --filter-file <path>    Use custom include/exclude filter file
  -h, --help              Show this help
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$SOURCE" ]]; then
  echo "Source directory not found: $SOURCE" >&2
  exit 1
fi

if ! command -v hf >/dev/null 2>&1; then
  echo "Installing Hugging Face CLI..."
  curl -LsSf https://hf.co/cli/install.sh | bash
fi

echo "Using HF CLI: $(command -v hf)"
hf --version

TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-${HF_HUB_TOKEN:-${HUGGINGFACEHUB_API_TOKEN:-}}}}"
SYNC_ARGS=()

if [[ -n "$TOKEN" ]]; then
  SYNC_ARGS+=(--token "$TOKEN")
else
  if ! hf auth whoami >/dev/null 2>&1; then
    echo "No valid HF authentication found." >&2
    echo "Set HF_TOKEN (or compatible HF token env var), or run: hf auth login --force" >&2
    exit 1
  fi
fi

SYNC_ARGS+=(
  --exclude ".git/**"
  --exclude ".pytest_cache/**"
  --exclude ".mypy_cache/**"
  --exclude ".ruff_cache/**"
  --exclude ".nox/**"
  --exclude ".tox/**"
  --exclude ".venv/**"
  --exclude ".tools/**"
  --exclude "__pycache__/**"
  --exclude "*/__pycache__/**"
  --exclude "**/__pycache__/**"
  --exclude "*.pyc"
  --exclude "**/*.pyc"
  --exclude "kimodo.egg-info/**"
  --exclude "dist/**"
  --exclude "docs/_build/**"
)

if [[ -n "$FILTER_FILE" ]]; then
  if [[ ! -f "$FILTER_FILE" ]]; then
    echo "Filter file not found: $FILTER_FILE" >&2
    exit 1
  fi
  SYNC_ARGS+=(--filter-from "$FILTER_FILE")
fi

if [[ "$INCLUDE_BUILD" == "false" ]]; then
  SYNC_ARGS+=(--exclude "build/**")
fi

if [[ "$DELETE_MISSING" == "true" ]]; then
  SYNC_ARGS+=(--delete)
fi

if [[ "$DRY_RUN" == "true" ]]; then
  SYNC_ARGS+=(--dry-run)
fi

if [[ "$VERBOSE" == "true" ]]; then
  SYNC_ARGS+=(--verbose)
fi

echo "Syncing source: $SOURCE"
echo "Syncing destination: $DEST"
if [[ -n "$FILTER_FILE" ]]; then
  echo "Using filter file: $FILTER_FILE"
fi
hf sync "$SOURCE" "$DEST" "${SYNC_ARGS[@]}"

echo "Sync complete."

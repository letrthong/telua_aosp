#!/usr/bin/env bash
#
# install_model.sh — Pre-download the ChromaDB ONNX embedding model (offline install)
#
# ChromaDB's default embedding function (ONNXMiniLM_L6_V2 / all-MiniLM-L6-v2)
# downloads its model from S3 on first use. Behind a corporate SSL proxy this
# fails with "CERTIFICATE_VERIFY_FAILED: self-signed certificate", breaking
# the "Sync to ChromaDB" feature (POST /api/ai/mcp/sync -> 500).
#
# This script:
#   1. Downloads the model with `curl -k` (skip SSL verify) into this directory
#   2. Extracts it to ai_agent/models/onnx/
#   3. Symlinks ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2 -> this directory
#      (ChromaDB hardcodes that cache path; there is no env var override)
#   4. Verifies the installation
#
# Usage:
#   ./install_model.sh
#
# Run once per machine. Idempotent: safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_NAME="all-MiniLM-L6-v2"
ARCHIVE_URL="https://chroma-onnx-models.s3.amazonaws.com/${MODEL_NAME}/onnx.tar.gz"
ARCHIVE_FILE="${SCRIPT_DIR}/onnx.tar.gz"
CHROMA_CACHE_DIR="${HOME}/.cache/chroma/onnx_models"
CHROMA_MODEL_LINK="${CHROMA_CACHE_DIR}/${MODEL_NAME}"

log()  { echo -e "[install_model] $*"; }
warn() { echo -e "[install_model][WARN] $*" >&2; }
die()  { echo -e "[install_model][ERROR] $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Download the model archive (bypass SSL proxy with -k)
# ---------------------------------------------------------------------------
if [[ -f "${SCRIPT_DIR}/onnx/model.onnx" ]]; then
    log "Model already extracted at ${SCRIPT_DIR}/onnx/ — skipping download."
else
    log "Downloading model (~80 MB) from ${ARCHIVE_URL} ..."
    curl -k -L --connect-timeout 30 --retry 3 \
        -o "${ARCHIVE_FILE}" "${ARCHIVE_URL}" \
        || die "Download failed. Check network/proxy connectivity."
    log "Downloaded: $(du -h "${ARCHIVE_FILE}" | cut -f1)"
fi

# ---------------------------------------------------------------------------
# Step 2: Extract
# ---------------------------------------------------------------------------
if [[ ! -f "${SCRIPT_DIR}/onnx/model.onnx" ]]; then
    log "Extracting archive ..."
    tar -xzf "${ARCHIVE_FILE}" -C "${SCRIPT_DIR}" \
        || die "Extraction failed."
    rm -f "${ARCHIVE_FILE}"
    log "Extracted to ${SCRIPT_DIR}/onnx/"
fi

[[ -f "${SCRIPT_DIR}/onnx/model.onnx" ]] \
    || die "model.onnx not found after extraction — archive layout unexpected?"

# ---------------------------------------------------------------------------
# Step 3: Symlink ChromaDB cache path -> this directory
# ---------------------------------------------------------------------------
mkdir -p "${CHROMA_CACHE_DIR}"

# Remove a pre-existing real directory (e.g. empty dir from a failed download)
if [[ -d "${CHROMA_MODEL_LINK}" && ! -L "${CHROMA_MODEL_LINK}" ]]; then
    warn "Removing existing non-symlink directory ${CHROMA_MODEL_LINK}"
    rm -rf "${CHROMA_MODEL_LINK}"
fi

ln -sfn "${SCRIPT_DIR}" "${CHROMA_MODEL_LINK}"
log "Symlinked: ${CHROMA_MODEL_LINK} -> ${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# Step 4: Verify
# ---------------------------------------------------------------------------
if [[ -f "${CHROMA_MODEL_LINK}/onnx/model.onnx" ]]; then
    log "Verification OK: ${CHROMA_MODEL_LINK}/onnx/model.onnx exists."
else
    die "Verification failed: model not reachable via ${CHROMA_MODEL_LINK}"
fi

cat <<EOF

[install_model] Done! Next steps:
  1. Restart tel web:        tel web restart
  2. Retry the sync:         curl -X POST http://127.0.0.1:8788/api/ai/mcp/sync
     (or click "🔄 Sync to ChromaDB" in the Web UI config dialog)

EOF

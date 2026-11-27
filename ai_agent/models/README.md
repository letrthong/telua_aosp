# ai_agent/models — Offline Embedding Model Cache

This directory holds the **ONNX embedding model** used by ChromaDB (RAG /
semantic search), allowing Telua Web to sync knowledge **offline / behind a
corporate proxy** without downloading the model from the internet at runtime.

## Problem

When clicking **🔄 Sync to ChromaDB** in the Web UI (`⚙ Config`), ChromaDB uses
the default embedding function `ONNXMiniLM_L6_V2` (all-MiniLM-L6-v2). On first
run, it automatically downloads the model from:

```
https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz
```

and extracts it to:

```
~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/
```

On corporate networks with an SSL proxy (self-signed certificate), this
download fails with:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
self-signed certificate in certificate chain
```

→ The `POST /api/ai/mcp/sync` API returns **500 Internal Server Error**.

## Installation (pre-download the model)

### Quick install (recommended)

```bash
cd /home/etr1hc/telua_aosp/ai_agent/models
./install_model.sh
```

The script is idempotent (safe to re-run): it downloads the model with
`curl -k`, extracts it, creates the ChromaDB cache symlink, and verifies
the installation.

### Manual install (Step by Step)

#### Step 1 — Download the model into this directory (bypass SSL proxy)

```bash
cd /home/etr1hc/telua_aosp/ai_agent/models
curl -k -L -o onnx.tar.gz \
  "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
```

> `-k` skips SSL verification (required behind corporate proxies).
> The model is ~80 MB compressed, ~90 MB extracted.

#### Step 2 — Extract

```bash
tar -xzf onnx.tar.gz
# Result: ai_agent/models/onnx/{model.onnx, tokenizer.json, ...}
rm onnx.tar.gz   # (optional) remove the archive after extraction
```

#### Step 3 — Point the ChromaDB cache to the pre-downloaded model

ChromaDB hardcodes its cache path at `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2`
(there is no env var override). Use a symlink:

```bash
mkdir -p ~/.cache/chroma/onnx_models
ln -sfn /home/etr1hc/telua_aosp/ai_agent/models \
        ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2
```

#### Step 4 — Verify

```bash
ls ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/model.onnx
# → model.onnx must exist

# Restart tel web, then retry the sync:
curl -X POST http://127.0.0.1:8788/api/ai/mcp/sync
```

A successful sync returns JSON like:

```json
{"ok": true, "indexed": 134, "collection": "telua_knowledge", ...}
```

## Directory layout after installation

```
ai_agent/models/                  ← this directory (git-ignored)
├── README.md                     ← the file you are reading
├── install_model.sh              ← one-shot installer (download + extract + symlink)
└── onnx/                         ← extracted from onnx.tar.gz
    ├── model.onnx                ← embedding model (~90 MB)
    ├── tokenizer.json
    └── ...
```

## Notes

- This directory is **git-ignored** (see `.gitignore` — ChromaDB vector data &
  model binaries are not committed to the repo).
- The model only needs to be installed **once per machine**. Subsequent syncs
  use the cache and require no network access.
- If you switch machines / users, just re-run `./install_model.sh`.
- Do **not** delete the `onnx/` directory — ChromaDB will attempt to
  re-download it and fail behind a proxying network.

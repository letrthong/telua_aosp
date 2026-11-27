# Weaviate VectorDB Backend (Template)

This folder is a ready-to-fill skeleton for integrating [Weaviate](https://weaviate.io) behind the `VectorDB` interface (`web/ai/db/base.py`) without modifying `telua_web_ai.py` or `telua_mcp_skill.py`.

## Why Weaviate fits large AOSP repos
- **Multi-Tenancy**: Maps 1-to-1 to `shard_key(project, aosp_version)` (e.g. `aosp_aaos__a12`, `aosp_aaos__a16`). Inactive Android versions can be offloaded to disk (`TenantActivityStatus.INACTIVE`) to save RAM.
- **Hybrid Search (BM25 + Vector)**: Combines exact symbol/log-tag matching (`CarAudioService`, `avc: denied`) with semantic vector search via `search_mode="hybrid"` and `alpha`.

## How to enable later
1. Install the v4 client:
   ```bash
   pip install weaviate-client
   ```
2. Run Weaviate locally (e.g. Docker) or use Weaviate Cloud, and set:
   ```bash
   export TELUA_VECTOR_DB=weaviate
   export WEAVIATE_URL=http://localhost:8080
   export WEAVIATE_API_KEY=...   # optional for local
   ```
3. Implement the `TODO` methods in `web/ai/db/weaviate/store.py` (already registered as `"weaviate"` in `web/ai/db/__init__.py`).

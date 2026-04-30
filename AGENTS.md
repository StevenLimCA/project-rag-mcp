## Context Policy (Project RAG)

Use `project-rag` as the primary source of code context for this repo.

Workflow:
1. Run `search` with a targeted query (`top_k` 3-5).
2. Select the most relevant files.
3. Run `get_document` only for selected files.
4. Answer or implement using retrieved files.
5. If confidence is low, run one additional targeted `search` before expanding scope.
6. If retrieval fails or returns weak/empty results, run `index_project` once, then retry `search` once.
7. If retrieval still fails after retry, stop and ask the user for reindex/path correction; do not proceed with broad local context.

Rules:
- Do not rely on broad thread context when `project-rag` data is available.
- Keep retrieved context minimal (2-4 files unless task requires more).
- Prefer project-scoped retrieval (`project_name`) over global retrieval.
- Fail closed: if retrieval is unavailable, do not silently fall back to full local context.

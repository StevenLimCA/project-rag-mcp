# Project RAG MCP

Local-first RAG indexing and semantic search for software projects, exposed as an MCP server.

## What This Tool Is

Project RAG MCP is a context router for coding agents. Instead of sending broad repo context to the model on every task, it indexes your project once and retrieves only the most relevant chunks per query.

## Why It Matters

For real codebases, most token waste comes from irrelevant context. This tool reduces that by narrowing each request to high-signal files/snippets.

Practical impact:

- Lower token usage per request (often large reductions vs full-context prompts)
- Faster responses due to smaller prompts
- Lower model/API cost when using hosted models
- Better focus by grounding answers in project-scoped retrieval

The core value is not summary text; it is retrieval precision. You pay the indexing cost once, then reuse targeted context many times.

## Features

- Local embeddings by default (`sentence-transformers`)
- Incremental indexing (mtime + size + content hash)
- SQLite + `sqlite-vec` storage
- Project-scoped semantic search
- MCP tools for add/index/search/context/document access
- Optional auto-sync on read operations

No OpenAI key is required for semantic search in default mode.

## Requirements

- Python 3.11+
- macOS/Linux shell (Windows works with path adjustments)

## Quickstart

```bash
git clone <your-repo-url>
cd project-rag-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Register and index a project:

```bash
.venv/bin/python cli.py add MyRepo /absolute/path/to/my/repo
.venv/bin/python cli.py index MyRepo
.venv/bin/python cli.py search "auth middleware" MyRepo 5
```

## CLI Commands

```bash
.venv/bin/python cli.py add <project_name> <project_path>
.venv/bin/python cli.py pick <project_name>
.venv/bin/python cli.py discover [base_path] [max_depth]
.venv/bin/python cli.py index <project_name> [project_path]
.venv/bin/python cli.py watch <project_name> [interval_seconds]
.venv/bin/python cli.py search <query> [project_name] [top_k]
.venv/bin/python cli.py list
.venv/bin/python cli.py context <project_name>
.venv/bin/python cli.py get <project_name> <file_path>
```

## MCP Setup (Codex)

From this repo root:

```bash
codex mcp add project-rag -- "$(pwd)/.venv/bin/python" "$(pwd)/mcp/server.py"
```

Restart Codex after registering.

Available MCP tools:

- `add_project`
- `index_project`
- `search`
- `list_projects`
- `get_project_context`
- `get_document`

## Retrieval-First Prompting Pattern

Use this pattern to keep context tight:

```text
Use project-rag as the source of truth for code context.
1) search "<topic>" in <project_name> (top_k 3-5)
2) fetch only the most relevant files with get_document
3) answer/implement from retrieved files
4) expand scope only if confidence is low
```

## Optional AI Summaries (Bring Your Own LLM)

By default, summaries are `extractive` (deterministic, no LLM call).

If you want AI-generated summaries, set `SUMMARY_BACKEND=openai_compatible` and point to any OpenAI-compatible endpoint.

### Option A: OpenAI

```bash
export SUMMARY_BACKEND=openai_compatible
export SUMMARY_API_KEY="sk-..."
export SUMMARY_MODEL="gpt-4.1-mini"
```

### Option B: Local LLM via Ollama (OpenAI-compatible `/v1`)

```bash
export SUMMARY_BACKEND=openai_compatible
export SUMMARY_BASE_URL="http://localhost:11434/v1"
export SUMMARY_API_KEY="ollama"
export SUMMARY_MODEL="qwen2.5:7b"
```

### Option C: LM Studio / vLLM / Other OpenAI-Compatible Server

```bash
export SUMMARY_BACKEND=openai_compatible
export SUMMARY_BASE_URL="http://localhost:8000/v1"
export SUMMARY_API_KEY="local"
export SUMMARY_MODEL="<your-model-name>"
```

## Configuration

See `config.py`:

- `USE_LOCAL_EMBEDDINGS` (default `true`)
- `EMBEDDING_MODEL` (default local model)
- `EMBEDDING_DIM`
- `SUMMARY_BACKEND` (`extractive` or `openai_compatible`)
- `SUMMARY_MODEL`
- `SUMMARY_API_KEY`
- `SUMMARY_BASE_URL`
- `USE_OPENAI_SUMMARIZATION` (legacy compatibility flag)
- `OPENAI_MODEL` (legacy default for summary model)
- `AUTO_SYNC_ON_QUERY` (default `true`)
- `AUTO_SYNC_MIN_INTERVAL_SECONDS` (default `30`)
- `MAX_FILE_SIZE_BYTES`
- `MAX_CHUNKS_PER_DOCUMENT`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`

## Verify It Works

1. `add` succeeds for a real repo path.
2. `index` reports non-zero documents.
3. `search` returns file paths + relevance.
4. Re-running `index` after no file changes should report near-zero updates.

## Troubleshooting

`Indexed 0 documents`
- Verify the path contains indexable files.
- Check with: `find /path/to/repo -type f | head`

`search` returns 0 results
- Ensure indexing succeeded first.
- Try a narrower query tied to real identifiers.

`readonly database`
- Ensure process can write to the configured DB path.

`local embedding model failed to initialize`
- Reinstall deps in venv:
  - `.venv/bin/python -m pip install -r requirements.txt`

## Project Layout

```text
project-rag-mcp/
├── cli.py
├── config.py
├── core/
│   ├── database.py
│   ├── embeddings.py
│   ├── indexer.py
│   └── retriever.py
├── mcp/
│   ├── models.py
│   ├── server.py
│   └── tools.py
└── requirements.txt
```

## License

MIT

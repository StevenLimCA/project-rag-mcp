# Project RAG MCP

Local-first RAG indexing and semantic search for software projects, exposed as an MCP server.

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

## Optional OpenAI Summaries

By default, summaries are local/extractive.  
Enable OpenAI summarization only if you explicitly want it:

```bash
export OPENAI_API_KEY="sk-..."
export USE_OPENAI_SUMMARIZATION=true
```

## Configuration

See `config.py`:

- `USE_LOCAL_EMBEDDINGS` (default `true`)
- `EMBEDDING_MODEL` (default local model)
- `EMBEDDING_DIM`
- `USE_OPENAI_SUMMARIZATION` (default `false`)
- `OPENAI_MODEL`
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

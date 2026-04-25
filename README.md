# Project RAG MCP

Local-first RAG indexing and semantic search for code/document projects, exposed as an MCP server.

## What This Does

1. Registers project folders.
2. Scans indexable files (`.py`, `.ts`, `.js`, `.md`, `.json`, etc.).
3. Stores summaries and chunk embeddings in SQLite (`sqlite-vec`).
4. Serves search/context tools via MCP.

## Current Defaults

- Embeddings: local (`sentence-transformers`, `all-MiniLM-L6-v2`)
- Summarization: local fallback (OpenAI optional)
- Incremental indexing: enabled (mtime + size + content hash)
- Common build/cache/vendor folders are skipped
- Root `.gitignore` patterns are respected

No OpenAI key is required for semantic search in default mode.

## Requirements

- Python 3.11+ recommended
- macOS/Linux shell

## Setup

```bash
cd /Users/steve/Documents/project-rag-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Optional OpenAI Summaries

Only needed if you want OpenAI-based summaries:

```bash
export OPENAI_API_KEY="sk-..."
export USE_OPENAI_SUMMARIZATION=true
```

## CLI Usage

All examples assume:

```bash
cd /Users/steve/Documents/project-rag-mcp
```

### Register a Project

Manual:

```bash
.venv/bin/python cli.py add MyRepo /absolute/path/to/repo
```

Native folder picker:

```bash
.venv/bin/python cli.py pick MyRepo
```

Auto-discover likely projects:

```bash
.venv/bin/python cli.py discover ~/Documents 3
```

### Index and Search

```bash
.venv/bin/python cli.py index MyRepo
.venv/bin/python cli.py search "mcp server" MyRepo 5
```

Continuous local sync loop:

```bash
.venv/bin/python cli.py watch MyRepo 5
```

### Other Commands

```bash
.venv/bin/python cli.py list
.venv/bin/python cli.py context MyRepo
.venv/bin/python cli.py get MyRepo path/inside/repo/file.py
```

## Verify It Works

1. `add` or `pick` succeeds.
2. `index` returns non-zero docs for a real code/doc repo.
3. `search` returns results with file paths and relevance.
4. Running `index` again should usually return near-zero changes unless files changed.

## Codex Desktop MCP Setup

Register this server with Codex:

```bash
codex mcp add project-rag -- /Users/steve/Documents/project-rag-mcp/.venv/bin/python /Users/steve/Documents/project-rag-mcp/mcp/server.py
```

Then restart Codex Desktop.

By default, MCP read calls (`search`, `get_project_context`, `get_document`) auto-run an incremental sync for that project (throttled).

You can now call these MCP tools:

- `add_project`
- `index_project`
- `search`
- `list_projects`
- `get_project_context`
- `get_document`

## Using It From the AI Bot (Codex Chat)

Once the MCP server is registered and Codex Desktop is restarted, ask Codex in plain English to use `project-rag`.

Example prompts:

```text
Use project-rag to add a project named "ScoreAI" at /Users/steve/Documents/ScoreAI, then index it.
```

```text
Use project-rag to search ScoreAI for "practice scoring pipeline" and show top 5 results.
```

```text
Use project-rag to list indexed projects and then give me full context for ScoreAI.
```

```text
Use project-rag to fetch the document "src/scoring/engine.py" from ScoreAI.
```

Recommended first-run chat flow:

1. Ask Codex to call `list_projects`.
2. If missing, ask Codex to call `add_project`.
3. Ask Codex to call `index_project`.
4. Ask Codex to call `search`.

### Force Retrieval-First Behavior (Avoid Huge Context Dumps)

Use this prompt pattern when you want Codex to rely on `project-rag` instead of broad thread context:

```text
Use project-rag as the source of truth for code context.
Do not rely on broad thread context.
1) search "<topic>" in ScoreAI (top_k 5)
2) choose best files
3) get_document for only those files
4) then answer/implement
```

For implementation tasks:

```text
Use project-rag retrieval-first for ScoreAI.
Before coding: run search for "<feature/bug>" and fetch the 2-4 most relevant files.
Only use those files as context unless more are required.
```

For question answering:

```text
Use project-rag only. Search ScoreAI for "<question topic>" and answer from retrieved files.
If confidence is low, run one more targeted search instead of using general context.
```

## Using It From Claude Desktop Chat

If this MCP server is added to Claude Desktop, use the same plain-English style and explicitly name the tool.

Example prompts:

```text
Use the project-rag tool to add project "ScoreAI" at /Users/steve/Documents/ScoreAI and index it.
```

```text
Use the project-rag tool to search ScoreAI for "practice scoring pipeline" with top_k 5.
```

```text
Use the project-rag tool to list projects, then get project context for ScoreAI.
```

```text
Use the project-rag tool to get document "src/scoring/engine.py" from ScoreAI.
```

### MCP Tool Inputs

`add_project`

```json
{
  "project_name": "MyRepo",
  "project_path": "/absolute/path/to/repo"
}
```

`index_project`

```json
{
  "project_name": "MyRepo"
}
```

`index_project` (register/update path inline)

```json
{
  "project_name": "MyRepo",
  "project_path": "/absolute/path/to/repo"
}
```

`search`

```json
{
  "query": "semantic indexing",
  "project_name": "MyRepo",
  "top_k": 5
}
```

## Configuration

See `config.py`:

- `USE_LOCAL_EMBEDDINGS` (default `true`)
- `EMBEDDING_MODEL` (default local `all-MiniLM-L6-v2`)
- `USE_OPENAI_SUMMARIZATION` (default `false`)
- `OPENAI_MODEL` (used only when OpenAI summarization is enabled)
- `AUTO_SYNC_ON_QUERY` (default `true`)
- `AUTO_SYNC_MIN_INTERVAL_SECONDS` (default `30`)
- `MAX_FILE_SIZE_BYTES`
- `MAX_CHUNKS_PER_DOCUMENT`
- `CHUNK_SIZE` / `CHUNK_OVERLAP`

## Notes on Performance

- First local embedding run downloads model weights once.
- Embedding writes are batched per file transaction.
- Indexing is incremental and removes stale deleted files from the DB.

## Troubleshooting

`Indexed 0 documents`:
- You likely pointed at a folder without indexable files.
- Verify with: `find /path/to/repo -type f | head`

`search` returns 0:
- Ensure index had non-zero docs.
- Query with terms that exist in that repo.

`readonly database`:
- Ensure the process can write under your home/project path.
- Avoid running with mismatched `HOME` unless intentional.

`Could not initialize local embedding model`:
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

---
name: "rag-retrieval-first"
description: "Force project-rag retrieval-first behavior for coding tasks, and auto-bootstrap project registration when missing."
---

# RAG Retrieval First

Use this skill when `project-rag` is available and the goal is to minimize token usage while keeping answers grounded in retrieved source files.

## Policy

1. Treat `project-rag` as the primary context source.
2. Ensure the target project is registered before retrieval.
3. Prefer `get_context_pack` with `max_tokens` between 1500 and 3000.
4. Use `search` only when `get_context_pack` is unavailable or weak.
5. Fetch full files with `get_document` only when snippets are insufficient.
6. Expand scope only if confidence is low or evidence conflicts.
7. Do not rely on broad thread context when retrieval data exists.
8. Fail closed: if retrieval fails, reindex + retry once; do not fall back to full local context.

## Bootstrap Workflow (Project Registration)

1. Determine `project_name` from user prompt/context.
2. Run `list_projects` and check whether `project_name` is already registered.
3. If missing, try registering automatically:
   - Preferred: call `add_project` with a likely absolute path inferred from context.
   - Fallback path heuristics (in order):
     - `<cwd>/<project_name>`
     - `<cwd>/../<project_name>`
     - `~/Documents/<project_name>`
     - `~/Documents/<project_name>/<project_name>`
4. If registration fails for all inferred paths, ask the user for an absolute path, then call `add_project`.
5. Run `index_project` once after successful registration.

## Retrieval Workflow

1. Run `get_context_pack` with a focused query, `project_name`, and a small `max_tokens`.
2. Answer or implement from returned snippets when evidence is sufficient.
3. If snippets are insufficient, run one targeted `search` or fetch only the specific file with `get_document`.
4. If still uncertain, run one additional targeted retrieval.
5. If retrieval is empty/weak, run `index_project` once and retry retrieval once.
6. If still empty/weak, stop and ask user to verify project path or reindex.

## Query Guidance

- Prefer concrete identifiers over broad topics.
- Good: `"PracticeJournalCoach save logic and error handling"`
- Weak: `"how scoring works"`

## Prompt Template (Execution)

```text
Use project-rag as source of truth.
0) if <project_name> is not registered: add_project + index_project
1) get_context_pack "<topic>" in <project_name> (max_tokens 1500-3000)
2) answer/implement from returned snippets
3) if confidence is low, run one additional targeted retrieval
4) fetch full files with get_document only when snippets are insufficient
5) if retrieval fails: index_project once, retry once, then stop and ask user (no broad fallback)
```

## Prompt Template (Q&A)

```text
Use project-rag only for context.
If <project_name> is missing, register/index it first.
Get a context pack for "<question topic>" and answer from retrieved snippets.
If evidence is weak, perform one additional targeted retrieval before concluding.
If retrieval remains weak/empty, reindex once and retry once; then stop and ask user for path/index correction.
```

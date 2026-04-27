---
name: "rag-retrieval-first"
description: "Force project-rag retrieval-first behavior for coding tasks, and auto-bootstrap project registration when missing."
---

# RAG Retrieval First

Use this skill when `project-rag` is available and the goal is to minimize token usage while keeping answers grounded in retrieved source files.

## Policy

1. Treat `project-rag` as the primary context source.
2. Ensure the target project is registered before retrieval.
3. Use `top_k` between 3 and 5 by default.
4. Fetch only 2 to 4 files via `get_document`.
5. Expand scope only if confidence is low or evidence conflicts.
6. Do not rely on broad thread context when retrieval data exists.

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

1. Run `search` with a focused query and `project_name`.
2. Select best files from results.
3. Run `get_document` for selected files only.
4. Answer or implement from retrieved evidence.
5. If still uncertain, run one additional targeted `search`.

## Query Guidance

- Prefer concrete identifiers over broad topics.
- Good: `"PracticeJournalCoach save logic and error handling"`
- Weak: `"how scoring works"`

## Prompt Template (Execution)

```text
Use project-rag as source of truth.
0) if <project_name> is not registered: add_project + index_project
1) search "<topic>" in <project_name> (top_k 5)
2) fetch 2-4 relevant files with get_document
3) answer/implement from those files
4) if confidence is low, run one additional targeted search
```

## Prompt Template (Q&A)

```text
Use project-rag only for context.
If <project_name> is missing, register/index it first.
Search <project_name> for "<question topic>" and answer from retrieved files.
If evidence is weak, perform one additional targeted search before concluding.
```

"""Retrieval logic for querying indexed projects."""
from typing import List, Dict, Any, Optional, Tuple

from core.database import Database
from core.embeddings import EmbeddingProvider


class Retriever:
    """Query indexed projects."""

    def __init__(self, db: Database):
        self.db = db
        self.embedding_provider = EmbeddingProvider()

    def search(self, query: str, project_name: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search across projects using semantic similarity."""
        if not self.embedding_provider.available():
            return []

        try:
            project_id = None
            if project_name:
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
                row = cursor.fetchone()
                if not row:
                    return []
                project_id = row[0]

            query_embedding = self.embedding_provider.embed(query)
            if not query_embedding:
                return []

            # Search embeddings
            results = self.db.search_embeddings(
                query_embedding,
                top_k=top_k,
                project_id=project_id,
            )

            # Enrich results with document info
            enriched = []
            for result in results:
                doc = self.db.get_document_with_summary(result["document_id"])
                if doc:
                    enriched.append({
                        "file_path": doc["file_path"],
                        "chunk_text": result["text"],
                        "summary": doc["summary"],
                        "relevance": 1 - (result["distance"] / 2)  # Convert distance to relevance
                    })

            return enriched
        except Exception as e:
            print(f"Error searching: {e}")
            return []

    def get_project_summary(self, project_name: str) -> Dict[str, Any]:
        """Get summary of indexed project."""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Project {project_name} not indexed"}

            project_id = row[0]
            return self.db.get_project_summary(project_id)
        except Exception as e:
            return {"error": str(e)}

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all indexed projects."""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                "SELECT id, name, path, last_indexed FROM projects ORDER BY last_indexed DESC"
            )
            projects = []
            for proj_id, name, path, last_indexed in cursor.fetchall():
                summary = self.db.get_project_summary(proj_id)
                summary["last_indexed"] = last_indexed
                projects.append(summary)
            return projects
        except Exception as e:
            return [{"error": str(e)}]

    def get_full_context(self, project_name: str) -> str:
        """Get concatenated summaries for full project context."""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            row = cursor.fetchone()
            if not row:
                return ""

            project_id = row[0]
            cursor.execute(
                """SELECT file_path, summary FROM documents 
                   LEFT JOIN summaries ON documents.id = summaries.document_id
                   WHERE documents.project_id = ? AND summary IS NOT NULL
                   ORDER BY file_path""",
                (project_id,)
            )

            lines = [f"# {project_name} Summary\n"]
            for file_path, summary in cursor.fetchall():
                lines.append(f"## {file_path}\n{summary}\n")

            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def get_document_content(self, file_path: str, project_name: str) -> Optional[str]:
        """Get original document content."""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                """SELECT documents.content FROM documents 
                   JOIN projects ON documents.project_id = projects.id
                   WHERE projects.name = ? AND documents.file_path = ?""",
                (project_name, file_path)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"Error retrieving document: {e}")
            return None

    def get_context_pack(
        self,
        query: str,
        project_name: str,
        max_tokens: int = 2500,
        top_k: int = 8,
        snippet_tokens: int = 300,
        include_summaries: bool = True,
    ) -> Dict[str, Any]:
        """Build a bounded context pack from semantic search results."""
        token_budget = max(100, int(max_tokens or 2500))
        per_snippet_budget = max(50, min(int(snippet_tokens or 300), token_budget))
        requested_top_k = max(1, int(top_k or 8))

        results = self.search(query, project_name, requested_top_k)
        snippets = []
        used_tokens = self._estimate_tokens(f"Project: {project_name}\nQuery: {query}")
        omitted_for_budget = 0
        seen = set()

        for result in results:
            raw_text = result.get("chunk_text") or ""
            content = self.get_document_content(result["file_path"], project_name) or ""
            source_text = self._snap_to_line_boundaries(content, raw_text)
            compact_text = self._trim_to_token_budget(source_text, per_snippet_budget)
            if not compact_text:
                continue

            key = (result.get("file_path"), compact_text)
            if key in seen:
                continue
            seen.add(key)

            line_start, line_end = self._line_range_for_snippet(content, source_text)
            summary = result.get("summary") if include_summaries else None
            entry = {
                "file_path": result["file_path"],
                "line_start": line_start,
                "line_end": line_end,
                "relevance": round(result["relevance"], 3),
                "snippet": compact_text,
            }
            if summary:
                entry["summary"] = self._trim_to_token_budget(summary, 80)

            entry_tokens = self._estimate_entry_tokens(entry)
            if used_tokens + entry_tokens > token_budget:
                omitted_for_budget += 1
                continue

            snippets.append(entry)
            used_tokens += entry_tokens

        return {
            "project_name": project_name,
            "query": query,
            "max_tokens": token_budget,
            "estimated_tokens": used_tokens,
            "result_count": len(results),
            "included_count": len(snippets),
            "omitted_count": max(0, len(results) - len(snippets)),
            "omitted_for_budget": omitted_for_budget,
            "snippets": snippets,
        }

    def _line_range_for_snippet(self, content: str, snippet: str) -> Tuple[Optional[int], Optional[int]]:
        """Best-effort line range for a retrieved snippet."""
        if not content or not snippet:
            return None, None

        position = content.find(snippet)
        if position < 0:
            probe = snippet.strip()[:120]
            position = content.find(probe) if probe else -1
        if position < 0:
            return None, None

        line_start = content.count("\n", 0, position) + 1
        line_count = max(1, snippet.count("\n") + 1)
        return line_start, line_start + line_count - 1

    def _snap_to_line_boundaries(self, content: str, snippet: str) -> str:
        """Avoid returning snippets that start or end in the middle of a line."""
        if not content or not snippet:
            return snippet.strip("\r\n") if snippet else ""

        position = content.find(snippet)
        if position < 0:
            return snippet.strip("\r\n")

        line_start = content.rfind("\n", 0, position) + 1
        line_end = content.find("\n", position + len(snippet))
        if line_end < 0:
            line_end = len(content)

        return content[line_start:line_end].strip("\r\n")

    def _trim_to_token_budget(self, text: str, max_tokens: int) -> str:
        """Trim text to an approximate token budget."""
        if not text:
            return ""
        max_chars = max(1, int(max_tokens * 4))
        cleaned = text.strip("\r\n")
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars].rstrip() + "\n...[truncated]"

    def _estimate_entry_tokens(self, entry: Dict[str, Any]) -> int:
        """Estimate serialized entry token count."""
        parts = [
            entry.get("file_path", ""),
            str(entry.get("line_start") or ""),
            str(entry.get("line_end") or ""),
            str(entry.get("relevance") or ""),
            entry.get("summary", ""),
            entry.get("snippet", ""),
        ]
        return self._estimate_tokens("\n".join(parts)) + 12

    def _estimate_tokens(self, text: str) -> int:
        """Approximate tokens from text length."""
        return max(1, len(text) // 4)

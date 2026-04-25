"""Retrieval logic for querying indexed projects."""
from typing import List, Dict, Any, Optional

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

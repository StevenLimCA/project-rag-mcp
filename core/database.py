"""SQLite database with vector search support."""
import sqlite3
import struct
from typing import Any, Dict, List, Optional, Set

import sqlite_vec

from config import DB_PATH, EMBEDDING_DIM, SEARCH_TOP_K


class Database:
    """SQLite + vec database for RAG."""

    def __init__(self):
        self.db_path = DB_PATH
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initialize database with schema."""
        self.conn = sqlite3.connect(str(self.db_path))
        # Enable vec extension
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        
        cursor = self.conn.cursor()
        
        # Projects table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_indexed TIMESTAMP
            )
        """)
        
        # Documents table (original content)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                file_type TEXT,
                content_hash TEXT,
                file_mtime REAL,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                UNIQUE(project_id, file_path)
            )
        """)
        self._migrate_documents_table(cursor)
        
        # Summaries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)

        # Internal settings table for lightweight schema coordination.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        self._ensure_embeddings_table(cursor)
        
        # Chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER,
                content TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)
        
        self.conn.commit()

    def begin(self):
        """Begin an explicit transaction if one is not already open."""
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN")

    def commit(self):
        """Commit current transaction."""
        self.conn.commit()

    def rollback(self):
        """Rollback current transaction when errors occur."""
        if self.conn.in_transaction:
            self.conn.rollback()

    def _migrate_documents_table(self, cursor: sqlite3.Cursor):
        """Add newly introduced columns on existing databases."""
        cursor.execute("PRAGMA table_info(documents)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = (
            ("content_hash", "TEXT"),
            ("file_mtime", "REAL"),
            ("file_size", "INTEGER"),
        )
        for col_name, col_type in migrations:
            if col_name not in existing:
                cursor.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")

    def _ensure_embeddings_table(self, cursor: sqlite3.Cursor):
        """Ensure embeddings table exists and matches configured vector dimension."""
        configured_dim = str(EMBEDDING_DIM)
        cursor.execute("SELECT value FROM settings WHERE key = 'embedding_dim'")
        row = cursor.fetchone()
        stored_dim = row[0] if row else None

        if stored_dim != configured_dim:
            cursor.execute("DROP TABLE IF EXISTS embeddings")
            cursor.execute(
                f"""
                CREATE VIRTUAL TABLE embeddings
                USING vec0(
                    embedding FLOAT32[{EMBEDDING_DIM}],
                    document_id INT,
                    chunk_index INT,
                    chunk_text TEXT
                )
                """
            )
            cursor.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES('embedding_dim', ?)",
                (configured_dim,),
            )
        else:
            cursor.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS embeddings
                USING vec0(
                    embedding FLOAT32[{EMBEDDING_DIM}],
                    document_id INT,
                    chunk_index INT,
                    chunk_text TEXT
                )
                """
            )

    def add_project(self, name: str, path: str) -> int:
        """Add or update project."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO projects (name, path) VALUES (?, ?)""",
                (name, path)
            )
        except sqlite3.IntegrityError:
            cursor.execute(
                """UPDATE projects SET path = ? WHERE name = ?""",
                (path, name)
            )
        self.conn.commit()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (name,))
        return cursor.fetchone()[0]

    def add_document(
        self,
        project_id: int,
        file_path: str,
        content: str,
        file_type: str,
        content_hash: str,
        file_mtime: float,
        file_size: int,
        commit: bool = True,
    ) -> int:
        """Add or update document."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO documents (
                       project_id, file_path, content, file_type, content_hash, file_mtime, file_size
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_id, file_path, content, file_type, content_hash, file_mtime, file_size)
            )
        except sqlite3.IntegrityError:
            cursor.execute(
                """UPDATE documents SET
                       content = ?,
                       file_type = ?,
                       content_hash = ?,
                       file_mtime = ?,
                       file_size = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE project_id = ? AND file_path = ?""",
                (content, file_type, content_hash, file_mtime, file_size, project_id, file_path)
            )
        if commit:
            self.conn.commit()
        cursor.execute(
            "SELECT id FROM documents WHERE project_id = ? AND file_path = ?",
            (project_id, file_path)
        )
        return cursor.fetchone()[0]

    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a project by name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, path FROM projects WHERE name = ?", (name,))
        row = cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "path": row[2]}

    def get_document_index_state(self, project_id: int, file_path: str) -> Optional[Dict[str, Any]]:
        """Get persisted file fingerprint fields for incremental indexing."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT id, content_hash, file_mtime, file_size
               FROM documents
               WHERE project_id = ? AND file_path = ?""",
            (project_id, file_path),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "content_hash": row[1],
            "file_mtime": row[2],
            "file_size": row[3],
        }

    def has_embeddings_for_document(self, document_id: int) -> bool:
        """Return True if document already has at least one embedding chunk."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM embeddings WHERE document_id = ? LIMIT 1",
            (document_id,),
        )
        return cursor.fetchone() is not None

    def remove_missing_documents(self, project_id: int, seen_paths: Set[str]) -> int:
        """Delete documents/related data no longer present on disk."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, file_path FROM documents WHERE project_id = ?",
            (project_id,),
        )
        stale_doc_ids = [doc_id for doc_id, file_path in cursor.fetchall() if file_path not in seen_paths]
        if not stale_doc_ids:
            return 0

        for doc_id in stale_doc_ids:
            cursor.execute("DELETE FROM summaries WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM embeddings WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()
        return len(stale_doc_ids)

    def add_summary(self, document_id: int, summary: str, token_count: int, commit: bool = True):
        """Add summary for document."""
        cursor = self.conn.cursor()
        cursor.execute(
            """DELETE FROM summaries WHERE document_id = ?""",
            (document_id,)
        )
        cursor.execute(
            """INSERT INTO summaries (document_id, summary, token_count) VALUES (?, ?, ?)""",
            (document_id, summary, token_count)
        )
        if commit:
            self.conn.commit()

    def add_embedding(
        self,
        document_id: int,
        chunk_index: int,
        embedding: List[float],
        chunk_text: str,
        commit: bool = True,
    ):
        """Add embedding for chunk."""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO embeddings (embedding, document_id, chunk_index, chunk_text) 
               VALUES (?, ?, ?, ?)""",
            (self._to_float32_blob(embedding), document_id, chunk_index, chunk_text)
        )
        if commit:
            self.conn.commit()

    def clear_embeddings_for_document(self, document_id: int, commit: bool = True):
        """Remove old embeddings for a document before re-indexing."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM embeddings WHERE document_id = ?", (document_id,))
        if commit:
            self.conn.commit()

    def search_embeddings(
        self,
        embedding: List[float],
        top_k: int = SEARCH_TOP_K,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar embeddings."""
        cursor = self.conn.cursor()
        if project_id is None:
            cursor.execute(
                """SELECT document_id, chunk_index, chunk_text, distance 
                   FROM embeddings 
                   WHERE embedding MATCH ? AND k = ?
                   ORDER BY distance""",
                (self._to_float32_blob(embedding), top_k)
            )
        else:
            cursor.execute(
                """SELECT e.document_id, e.chunk_index, e.chunk_text, e.distance
                   FROM embeddings e
                   JOIN documents d ON d.id = e.document_id
                   WHERE e.embedding MATCH ? AND e.k = ? AND d.project_id = ?
                   ORDER BY e.distance""",
                (self._to_float32_blob(embedding), top_k, project_id)
            )
        results = []
        for doc_id, chunk_idx, text, dist in cursor.fetchall():
            results.append({
                "document_id": doc_id,
                "chunk_index": chunk_idx,
                "text": text,
                "distance": dist
            })
        return results

    def get_project_summary(self, project_id: int) -> Dict[str, Any]:
        """Get summary stats for a project."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name, path FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if not row:
            return {}
        
        cursor.execute("SELECT COUNT(*) FROM documents WHERE project_id = ?", (project_id,))
        doc_count = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM summaries WHERE document_id IN (SELECT id FROM documents WHERE project_id = ?)",
            (project_id,)
        )
        summary_count = cursor.fetchone()[0]
        
        return {
            "name": row[0],
            "path": row[1],
            "documents": doc_count,
            "summarized": summary_count
        }

    def get_document_with_summary(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Get document path and its summary."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT file_path FROM documents WHERE id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            return None
        
        cursor.execute("SELECT summary, token_count FROM summaries WHERE document_id = ?", (document_id,))
        summary = cursor.fetchone()
        
        return {
            "file_path": doc[0],
            "summary": summary[0] if summary else None,
            "tokens": summary[1] if summary else 0
        }

    def update_project_timestamp(self, project_id: int):
        """Update last_indexed timestamp."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE projects SET last_indexed = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        self.conn.commit()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    @staticmethod
    def _to_float32_blob(embedding: List[float]) -> bytes:
        """Convert embedding list to sqlite-vec compatible float32 blob."""
        return struct.pack(f"{len(embedding)}f", *embedding)

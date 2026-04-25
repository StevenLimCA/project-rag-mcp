"""Indexing logic for scanning projects and generating summaries."""
import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

from config import (
    PROJECTS, INDEXABLE_EXTENSIONS, OPENAI_API_KEY, OPENAI_MODEL, USE_OPENAI_SUMMARIZATION,
    CHUNK_SIZE, CHUNK_OVERLAP, SUMMARY_MAX_TOKENS,
    MAX_CHUNKS_PER_DOCUMENT, MAX_FILE_SIZE_BYTES
)
from core.database import Database
from core.embeddings import EmbeddingProvider


class Indexer:
    """Scan projects, chunk content, and generate summaries."""

    DEFAULT_EXCLUDED_DIRS = {
        ".git", "__pycache__", "node_modules", ".xcodeproj", "xcuserdata",
        "Pods", "Carthage", ".venv", "venv", ".mypy_cache", ".pytest_cache",
        ".next", ".nuxt", ".turbo", "dist", "build", "DerivedData", ".idea",
        ".vscode", ".cache", "coverage", ".gradle", "target", ".tox"
    }

    def __init__(self, db: Database):
        self.db = db
        self.openai_client = self._init_openai()
        self.embedding_provider = EmbeddingProvider()

    def _init_openai(self):
        """Initialize OpenAI client."""
        if not USE_OPENAI_SUMMARIZATION or not OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            print(f"Warning: Could not initialize OpenAI: {e}")
            return None

    def index_project(self, project_name: str, project_path: Optional[str] = None) -> Tuple[int, int]:
        """Index all files in a project. Returns (documents_found, summaries_generated)."""
        project_path = self._resolve_project_path(project_name, project_path)
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Project path not found: {project_path}")

        # Register project
        project_id = self.db.add_project(project_name, project_path)
        ignore_patterns = self._load_ignore_patterns(project_path)

        doc_count = 0
        summary_count = 0
        tracked_paths: Set[str] = set()

        # Recursively scan directory
        for root, dirs, files in os.walk(project_path):
            rel_root = os.path.relpath(root, project_path).replace(os.sep, "/")
            rel_root = "" if rel_root == "." else rel_root

            filtered_dirs: List[str] = []
            for directory in dirs:
                if directory in self.DEFAULT_EXCLUDED_DIRS:
                    continue
                rel_dir = f"{rel_root}/{directory}" if rel_root else directory
                if self._is_ignored(rel_dir, is_dir=True, patterns=ignore_patterns):
                    continue
                filtered_dirs.append(directory)
            dirs[:] = filtered_dirs

            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, project_path).replace(os.sep, "/")

                # Check if indexable
                if not any(file.endswith(ext) for ext in INDEXABLE_EXTENSIONS):
                    continue
                if self._is_ignored(rel_path, is_dir=False, patterns=ignore_patterns):
                    continue

                try:
                    stat = os.stat(file_path)
                    file_size = stat.st_size
                    file_mtime = stat.st_mtime

                    # Treat oversized files as unindexed to keep storage and memory bounded.
                    if file_size > MAX_FILE_SIZE_BYTES:
                        continue

                    content = self._read_file(file_path)
                    if content and len(content.strip()) > 20:  # Skip empty files
                        tracked_paths.add(rel_path)

                        existing = self.db.get_document_index_state(project_id, rel_path)
                        if (
                            existing
                            and existing.get("file_mtime") == file_mtime
                            and existing.get("file_size") == file_size
                        ):
                            if existing.get("id") and self.db.has_embeddings_for_document(existing["id"]):
                                continue

                        file_type = Path(file_path).suffix
                        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                        self.db.begin()
                        try:
                            doc_id = self.db.add_document(
                                project_id,
                                rel_path,
                                content,
                                file_type,
                                content_hash,
                                file_mtime,
                                file_size,
                                commit=False,
                            )

                            # If only mtime/size changed but content hash stayed the same, skip expensive work.
                            if existing and existing.get("content_hash") == content_hash:
                                self.db.commit()
                                continue

                            doc_count += 1

                            # Generate summary
                            summary = self._generate_summary(content)
                            if summary:
                                token_count = self._estimate_tokens(summary)
                                self.db.add_summary(doc_id, summary, token_count, commit=False)
                                summary_count += 1

                                # Generate embeddings for chunks
                                self.db.clear_embeddings_for_document(doc_id, commit=False)
                                self._embed_and_store_chunks(doc_id, content, commit=False)

                            self.db.commit()
                        except Exception:
                            self.db.rollback()
                            raise

                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

        self.db.remove_missing_documents(project_id, tracked_paths)
        self.db.update_project_timestamp(project_id)
        return doc_count, summary_count

    def _read_file(self, file_path: str) -> str:
        """Read file content safely."""
        try:
            if os.path.getsize(file_path) > MAX_FILE_SIZE_BYTES:
                return ""
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""

    def _generate_summary(self, content: str) -> str:
        """Generate summary using OpenAI."""
        if not self.openai_client:
            return self._simple_summary(content)

        try:
            # Limit content to first 3000 chars for cost
            content_chunk = content[:3000]
            
            response = self.openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a concise summarizer. Summarize the content in 2-3 sentences focusing on key points."},
                    {"role": "user", "content": f"Summarize this:\n\n{content_chunk}"}
                ],
                max_tokens=SUMMARY_MAX_TOKENS,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating summary with OpenAI: {e}")
            return self._simple_summary(content)

    def _simple_summary(self, content: str) -> str:
        """Fallback: simple extractive summary."""
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        # Take first few non-empty lines
        return ' '.join(lines[:3]) if lines else ""

    def _embed_and_store_chunks(self, doc_id: int, content: str, commit: bool = True):
        """Split content into chunks and generate embeddings."""
        for chunk_idx, chunk in enumerate(self._iter_chunks(content)):
            if chunk_idx >= MAX_CHUNKS_PER_DOCUMENT:
                break
            try:
                embedding = self._get_embedding(chunk)
                if embedding:
                    self.db.add_embedding(doc_id, chunk_idx, embedding, chunk, commit=commit)
            except Exception as e:
                print(f"Error embedding chunk {chunk_idx}: {e}")

    def _iter_chunks(self, content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterator[str]:
        """Yield overlapping chunks (by tokens, approximate)."""
        # Simple token approximation: 4 chars ≈ 1 token
        char_size = chunk_size * 4
        char_overlap = min(overlap * 4, char_size - 1) if char_size > 1 else 0

        if not content or char_size <= 0:
            return

        step = max(1, char_size - char_overlap)
        start = 0
        while start < len(content):
            end = min(start + char_size, len(content))
            chunk = content[start:end]
            if len(chunk.strip()) > 10:
                yield chunk
            if end >= len(content):
                break
            start += step

    def _get_embedding(self, text: str) -> list:
        """Get embedding from configured provider."""
        return self.embedding_provider.embed(text)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text.split()) // 1.3  # Rough approximation

    def _resolve_project_path(self, project_name: str, project_path: Optional[str]) -> str:
        """Resolve project path from explicit argument, DB registration, or static config."""
        if project_path:
            return str(Path(project_path).expanduser().resolve())

        db_project = self.db.get_project_by_name(project_name)
        if db_project:
            return db_project["path"]

        if project_name in PROJECTS:
            return PROJECTS[project_name]

        raise ValueError(
            f"Unknown project: {project_name}. Register it first with add_project or pass project_path."
        )

    def _load_ignore_patterns(self, project_path: str) -> List[str]:
        """Load root ignore patterns (subset of .gitignore syntax)."""
        ignore_file = Path(project_path) / ".gitignore"
        if not ignore_file.exists():
            return []

        patterns: List[str] = []
        try:
            for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                patterns.append(entry)
        except Exception:
            return []
        return patterns

    def _is_ignored(self, rel_path: str, is_dir: bool, patterns: List[str]) -> bool:
        """Apply simple gitignore-like matching with support for ! negation."""
        path = rel_path.strip("/").replace("\\", "/")
        if not path:
            return False

        ignored = False
        for pattern in patterns:
            negate = pattern.startswith("!")
            check_pattern = pattern[1:] if negate else pattern
            if not check_pattern:
                continue
            if self._matches_ignore_pattern(path, check_pattern, is_dir):
                ignored = not negate
        return ignored

    def _matches_ignore_pattern(self, rel_path: str, pattern: str, is_dir: bool) -> bool:
        """Best-effort support for common .gitignore patterns."""
        anchored = pattern.startswith("/")
        if anchored:
            pattern = pattern[1:]

        dir_pattern = pattern.endswith("/")
        if dir_pattern:
            pattern = pattern[:-1]

        if not pattern:
            return False

        if dir_pattern:
            if rel_path == pattern or rel_path.startswith(f"{pattern}/"):
                return True
            return False

        if "/" not in pattern and fnmatch.fnmatch(Path(rel_path).name, pattern):
            return True

        if anchored:
            return fnmatch.fnmatch(rel_path, pattern)

        return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, f"*/{pattern}")

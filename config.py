"""Configuration for Project RAG MCP."""
import os
from pathlib import Path

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
USE_OPENAI_SUMMARIZATION = os.getenv("USE_OPENAI_SUMMARIZATION", "false").lower() in {"1", "true", "yes"}

# Embeddings Configuration
USE_LOCAL_EMBEDDINGS = os.getenv("USE_LOCAL_EMBEDDINGS", "true").lower() in {"1", "true", "yes"}
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2" if USE_LOCAL_EMBEDDINGS else "text-embedding-3-small"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
EMBEDDING_DIM = 384 if USE_LOCAL_EMBEDDINGS else 1536
EMBEDDING_CACHE_DIR = Path.home() / ".cache" / "sentence-transformers"

# Database
DB_PATH = Path.home() / ".project-rag" / "index.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Projects to index
PROJECTS = {
    "Codex": str(Path.home() / "Documents" / "Codex"),
    "DogeMonsters": str(Path.home() / "Documents" / "DogeMonsters"),
    "ScoreAI": str(Path.home() / "Documents" / "ScoreAI"),
}

# File extensions to index
INDEXABLE_EXTENSIONS = {
    ".md", ".swift", ".py", ".js", ".ts", ".json",
    ".txt", ".yaml", ".yml", ".html", ".css"
}

# Chunk settings
CHUNK_SIZE = 500  # tokens
CHUNK_OVERLAP = 100
MAX_CHUNKS_PER_DOCUMENT = 200
MAX_FILE_SIZE_BYTES = 1_000_000  # 1 MB cap per indexed file

# Summarization settings
SUMMARY_MAX_TOKENS = 300
SEARCH_TOP_K = 5

# Auto-sync settings
AUTO_SYNC_ON_QUERY = os.getenv("AUTO_SYNC_ON_QUERY", "true").lower() in {"1", "true", "yes"}
AUTO_SYNC_MIN_INTERVAL_SECONDS = int(os.getenv("AUTO_SYNC_MIN_INTERVAL_SECONDS", "30"))

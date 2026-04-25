"""Embedding provider abstraction (local-first, OpenAI optional)."""
from functools import lru_cache
from typing import List, Optional

from config import EMBEDDING_MODEL, OPENAI_API_KEY, USE_LOCAL_EMBEDDINGS


class EmbeddingProvider:
    """Get embeddings from local model or OpenAI based on configuration."""

    def __init__(self):
        self.openai_client = self._init_openai() if not USE_LOCAL_EMBEDDINGS else None

    def available(self) -> bool:
        """Return True if an embedding backend is available."""
        if USE_LOCAL_EMBEDDINGS:
            return _load_local_model() is not None
        return self.openai_client is not None

    def embed(self, text: str) -> Optional[List[float]]:
        """Generate an embedding vector."""
        if USE_LOCAL_EMBEDDINGS:
            model = _load_local_model()
            if model is None:
                return None
            try:
                vector = model.encode(text[:8000], normalize_embeddings=True)
                return vector.tolist()
            except Exception as e:
                print(f"Error getting local embedding: {e}")
                return None

        if not self.openai_client:
            return None
        try:
            response = self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text[:2000],
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error getting OpenAI embedding: {e}")
            return None

    def _init_openai(self):
        """Initialize OpenAI client if key exists."""
        if not OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI

            return OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            print(f"Warning: Could not initialize OpenAI client for embeddings: {e}")
            return None


@lru_cache(maxsize=1)
def _load_local_model():
    """Load and cache sentence-transformers model once per process."""
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(EMBEDDING_MODEL)
    except Exception as e:
        print(f"Warning: Could not initialize local embedding model '{EMBEDDING_MODEL}': {e}")
        return None

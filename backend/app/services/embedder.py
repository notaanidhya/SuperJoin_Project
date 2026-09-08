import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from app.models.fact import ExtractedFact

class Embedder:
    """Local dense embedding service using SentenceTransformers (384-dim, $0 cost)."""
    _instance = None
    _model = None

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2"):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._model = SentenceTransformer(model_name)
        return cls._instance

    def embed_text(self, text: str) -> np.ndarray:
        vec = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vec.astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return vecs.astype(np.float32)

    @staticmethod
    def format_fact_for_embedding(fact: ExtractedFact) -> str:
        period_str = f" in {fact.period}" if fact.period else ""
        scope_str = f" [{fact.scope}]" if fact.scope else ""
        return f"{fact.subject}: {fact.predicate} is {fact.object_value}{period_str}{scope_str}"

    @staticmethod
    def serialize_vector(vector: np.ndarray) -> bytes:
        return vector.astype(np.float32).tobytes()

    @staticmethod
    def deserialize_vector(blob: bytes) -> np.ndarray:
        if not blob:
            return np.zeros(384, dtype=np.float32)
        return np.frombuffer(blob, dtype=np.float32)

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

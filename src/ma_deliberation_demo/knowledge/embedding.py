"""Embedding providers; the heavy model is loaded only when indexing/searching."""

from __future__ import annotations

from typing import Protocol, Sequence

from .config import EmbeddingConfig


class EmbeddingProvider(Protocol):
    model_name: str

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Local BGE embedding adapter with normalized vectors for cosine search."""

    def __init__(self, config: EmbeddingConfig):
        self.model_name = config.model_name
        self._config = config
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "RAG embedding dependencies are missing. Install sentence-transformers, "
                "torch, numpy, and faiss-cpu before building or querying the index."
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self._config.device)
        return self._model

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load_model().encode(
            list(texts),
            batch_size=self._config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        prefix = self._config.query_prefix
        return self._encode([f"{prefix}{text}" if prefix else text for text in texts])

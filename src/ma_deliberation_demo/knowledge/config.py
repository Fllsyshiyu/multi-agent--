"""Configuration for the local, shared deliberation knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "BAAI/bge-small-zh-v1.5"
    query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    device: str = "cpu"
    batch_size: int = 16


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 1200


@dataclass(frozen=True)
class RetrievalConfig:
    lexical_candidates: int = 20
    vector_candidates: int = 20
    final_chunks_per_agent: int = 4
    max_chunks_per_case: int = 1
    reciprocal_rank_k: int = 60
    allow_knowledge_types: tuple[str, ...] = ("external_case",)


@dataclass(frozen=True)
class KnowledgeConfig:
    source_paths: tuple[Path, ...]
    index_dir: Path
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_knowledge_config(config_path: str | Path | None = None) -> KnowledgeConfig:
    """Read the YAML configuration without creating any index artifacts."""
    path = _project_path(config_path or "configs/knowledge_base.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    embedding_raw = raw.get("embedding", {})
    chunking_raw = raw.get("chunking", {})
    retrieval_raw = raw.get("retrieval", {})
    return KnowledgeConfig(
        source_paths=tuple(_project_path(item) for item in raw.get("source_paths", [])),
        index_dir=_project_path(raw.get("index_dir", "data/knowledge/index")),
        embedding=EmbeddingConfig(**embedding_raw),
        chunking=ChunkingConfig(**chunking_raw),
        retrieval=RetrievalConfig(
            lexical_candidates=int(retrieval_raw.get("lexical_candidates", 20)),
            vector_candidates=int(retrieval_raw.get("vector_candidates", 20)),
            final_chunks_per_agent=int(retrieval_raw.get("final_chunks_per_agent", 4)),
            max_chunks_per_case=int(retrieval_raw.get("max_chunks_per_case", 1)),
            reciprocal_rank_k=int(retrieval_raw.get("reciprocal_rank_k", 60)),
            allow_knowledge_types=tuple(retrieval_raw.get("allow_knowledge_types", ["external_case"])),
        ),
    )

"""Build reproducible, incrementally embedded local knowledge artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .chunking import chunk_cases
from .config import KnowledgeConfig
from .embedding import EmbeddingProvider
from .schema import CaseChunk, IndexBuildReport


MANIFEST_NAME = "index_manifest.json"
CHUNKS_NAME = "case_chunks.jsonl"
VECTORS_NAME = "vectors.jsonl"
SQLITE_NAME = "knowledge.db"
FAISS_NAME = "vectors.faiss"
VECTOR_IDS_NAME = "vector_ids.json"


def _read_jsonl(paths: Iterable[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Knowledge source does not exist: {path}")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Knowledge record {path}:{line_number} must be an object")
            records.append(record)
    return records


def _load_existing_vectors(index_dir: Path, model_name: str) -> dict[str, dict]:
    manifest_path = index_dir / MANIFEST_NAME
    vector_path = index_dir / VECTORS_NAME
    if not manifest_path.exists() or not vector_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if manifest.get("embedding_model") != model_name:
        return {}
    result: dict[str, dict] = {}
    for line in vector_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("model_name") == model_name:
                result[item["chunk_id"]] = item
    return result


def _write_sqlite(index_dir: Path, chunks: list[CaseChunk]) -> None:
    db_path = index_dir / SQLITE_NAME
    with sqlite3.connect(db_path) as connection:
        connection.executescript("""
            DROP TABLE IF EXISTS chunks;
            DROP TABLE IF EXISTS chunks_fts;
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                topic TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                text TEXT NOT NULL,
                region TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                retrieval_tags_json TEXT NOT NULL,
                source_records_json TEXT NOT NULL,
                verification_gaps_json TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED,
                text,
                topic,
                retrieval_tags
            );
        """)
        rows = []
        fts_rows = []
        for chunk in chunks:
            rows.append((
                chunk.chunk_id, chunk.case_id, chunk.knowledge_type, chunk.topic,
                chunk.chunk_type, chunk.text, chunk.region, chunk.evidence_level,
                json.dumps(list(chunk.retrieval_tags), ensure_ascii=False),
                json.dumps(list(chunk.source_records), ensure_ascii=False),
                json.dumps(list(chunk.verification_gaps), ensure_ascii=False),
                chunk.content_hash,
            ))
            fts_rows.append((chunk.chunk_id, chunk.text, chunk.topic, " ".join(chunk.retrieval_tags)))
        connection.executemany(
            "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
        )
        connection.executemany("INSERT INTO chunks_fts VALUES (?, ?, ?, ?)", fts_rows)


def _write_faiss(index_dir: Path, vectors: list[list[float]], vector_ids: list[str]) -> str:
    """Persist FAISS when installed; JSON vectors remain the portable fallback."""
    if not vectors:
        return "none"
    try:
        import faiss
        import numpy as np
    except ImportError:
        return "python_fallback"
    matrix = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, str(index_dir / FAISS_NAME))
    (index_dir / VECTOR_IDS_NAME).write_text(
        json.dumps(vector_ids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return "faiss_flat_ip"


def build_knowledge_index(config: KnowledgeConfig, embedder: EmbeddingProvider) -> IndexBuildReport:
    """Build all generated artifacts, re-embedding only changed chunk content."""
    cases = _read_jsonl(config.source_paths)
    chunks = chunk_cases(cases, max_chars=config.chunking.max_chars)
    index_dir = config.index_dir
    index_dir.mkdir(parents=True, exist_ok=True)
    existing = _load_existing_vectors(index_dir, embedder.model_name)

    vectors_by_id: dict[str, list[float]] = {}
    missing_chunks: list[CaseChunk] = []
    reused_count = 0
    for chunk in chunks:
        prior = existing.get(chunk.chunk_id)
        if prior and prior.get("content_hash") == chunk.content_hash:
            vectors_by_id[chunk.chunk_id] = list(prior["vector"])
            reused_count += 1
        else:
            missing_chunks.append(chunk)

    if missing_chunks:
        embedded = embedder.encode_documents([chunk.text for chunk in missing_chunks])
        if len(embedded) != len(missing_chunks):
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        vectors_by_id.update({chunk.chunk_id: vector for chunk, vector in zip(missing_chunks, embedded)})

    ordered_ids = [chunk.chunk_id for chunk in chunks]
    ordered_vectors = [vectors_by_id[chunk_id] for chunk_id in ordered_ids]
    _write_sqlite(index_dir, chunks)
    (index_dir / CHUNKS_NAME).write_text(
        "".join(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    (index_dir / VECTORS_NAME).write_text(
        "".join(json.dumps({
            "chunk_id": chunk.chunk_id,
            "content_hash": chunk.content_hash,
            "model_name": embedder.model_name,
            "vector": vectors_by_id[chunk.chunk_id],
        }, ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    backend = _write_faiss(index_dir, ordered_vectors, ordered_ids)
    manifest = {
        "embedding_model": embedder.model_name,
        "source_case_count": len(cases),
        "chunk_count": len(chunks),
        "vector_dimension": len(ordered_vectors[0]) if ordered_vectors else 0,
        "vector_backend": backend,
        "source_paths": [str(path) for path in config.source_paths],
    }
    (index_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return IndexBuildReport(
        source_case_count=len(cases),
        chunk_count=len(chunks),
        embedded_count=len(missing_chunks),
        reused_count=reused_count,
        backend=backend,
    )


def load_chunks(index_dir: Path) -> dict[str, CaseChunk]:
    path = index_dir / CHUNKS_NAME
    if not path.exists():
        return {}
    return {
        raw["chunk_id"]: CaseChunk.from_dict(raw)
        for raw in (
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }


def load_vectors(index_dir: Path) -> dict[str, list[float]]:
    path = index_dir / VECTORS_NAME
    if not path.exists():
        return {}
    return {
        raw["chunk_id"]: list(raw["vector"])
        for raw in (
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }

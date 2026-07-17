"""Hybrid retrieval and role-specific views over the shared case corpus."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..schemas import AgentCard, ConcernType, EvidenceCard, EvidenceSourceType
from .config import KnowledgeConfig
from .embedding import EmbeddingProvider, SentenceTransformerEmbedder
from .indexer import FAISS_NAME, MANIFEST_NAME, VECTOR_IDS_NAME, load_chunks, load_vectors
from .schema import CaseChunk, RetrievalHit


def build_agent_query(agent: AgentCard, topic: str, question: str) -> str:
    """Give each agent a role-specific retrieval view without copying the corpus."""
    role_focus = ""
    if agent.agent_id == "agent_host":
        role_focus = "程序公平 发言机会 协商机制 执行条件 少数意见"
    elif agent.agent_id == "agent_reviewer":
        role_focus = "证据等级 失败模式 迁移条件 待核验事项 风险"
    return " ".join(part for part in (
        topic, question, agent.archetype, agent.relationship_to_topic,
        " ".join(agent.main_interests), " ".join(agent.evidence_focus), role_focus,
    ) if part)


def _safe_fts_terms(query: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", query)


def _source_type(source_records: Iterable[dict]) -> EvidenceSourceType:
    value = str(next(iter(source_records), {}).get("source_type", "")).lower()
    if value in {"court", "court_case"}:
        return EvidenceSourceType.COURT_CASE
    if value in {"academic", "research"}:
        return EvidenceSourceType.ACADEMIC
    if value in {"news", "media"}:
        return EvidenceSourceType.NEWS
    return EvidenceSourceType.EXTERNAL_CASE


class KnowledgeRetriever:
    """A shared corpus with per-agent retrieval and evidence attribution."""

    def __init__(self, config: KnowledgeConfig, embedder: EmbeddingProvider | None = None):
        self.config = config
        self.embedder = embedder or SentenceTransformerEmbedder(config.embedding)
        self.chunks = load_chunks(config.index_dir)
        self.vectors = load_vectors(config.index_dir)
        self._faiss_index = None
        self._faiss_ids: list[str] | None = None

    @property
    def is_ready(self) -> bool:
        return bool(self.chunks and self.vectors)

    def _eligible(self) -> dict[str, CaseChunk]:
        allowed = set(self.config.retrieval.allow_knowledge_types)
        return {key: chunk for key, chunk in self.chunks.items() if chunk.knowledge_type in allowed}

    def _lexical_search(self, query: str, limit: int) -> list[str]:
        if not self.chunks:
            return []
        terms = _safe_fts_terms(query)
        if not terms:
            return []
        db_path = self.config.index_dir / "knowledge.db"
        if db_path.exists():
            try:
                expression = " OR ".join(f'"{term}"' for term in terms[:12])
                with sqlite3.connect(db_path) as connection:
                    rows = connection.execute(
                        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                        (expression, limit),
                    ).fetchall()
                ids = [row[0] for row in rows if row[0] in self._eligible()]
                if ids:
                    return ids
            except sqlite3.Error:
                pass
        lowered = query.lower()
        scored = []
        for chunk_id, chunk in self._eligible().items():
            text = f"{chunk.topic} {chunk.text} {' '.join(chunk.retrieval_tags)}".lower()
            score = sum(term.lower() in text for term in terms)
            if score:
                scored.append((score, chunk_id))
        return [chunk_id for _, chunk_id in sorted(scored, reverse=True)[:limit]]

    def _load_faiss(self) -> tuple[object, list[str]] | None:
        if self._faiss_index is not None and self._faiss_ids is not None:
            return self._faiss_index, self._faiss_ids
        index_path = self.config.index_dir / FAISS_NAME
        ids_path = self.config.index_dir / VECTOR_IDS_NAME
        if not index_path.exists() or not ids_path.exists():
            return None
        try:
            import faiss
            self._faiss_index = faiss.read_index(str(index_path))
            self._faiss_ids = json.loads(ids_path.read_text(encoding="utf-8"))
            return self._faiss_index, self._faiss_ids
        except (ImportError, RuntimeError, ValueError, OSError):
            return None

    def _vector_search(self, query: str, limit: int) -> list[str]:
        if not self.vectors:
            return []
        vector = self.embedder.encode_queries([query])[0]
        faiss_data = self._load_faiss()
        eligible = self._eligible()
        if faiss_data is not None:
            try:
                import numpy as np
                index, ids = faiss_data
                _, positions = index.search(np.asarray([vector], dtype="float32"), min(limit * 3, len(ids)))
                return [ids[position] for position in positions[0] if position >= 0 and ids[position] in eligible][:limit]
            except (ImportError, RuntimeError, ValueError):
                pass
        scores = []
        for chunk_id, chunk_vector in self.vectors.items():
            if chunk_id not in eligible:
                continue
            score = sum(left * right for left, right in zip(vector, chunk_vector))
            scores.append((score, chunk_id))
        return [chunk_id for _, chunk_id in sorted(scores, reverse=True)[:limit]]

    def retrieve(self, agent: AgentCard, topic: str, question: str, *, limit: int | None = None) -> list[RetrievalHit]:
        if not self.is_ready:
            return []
        query = build_agent_query(agent, topic, question)
        lexical = self._lexical_search(query, self.config.retrieval.lexical_candidates)
        vector = self._vector_search(query, self.config.retrieval.vector_candidates)
        rrf_scores: defaultdict[str, float] = defaultdict(float)
        lexical_rank: dict[str, int] = {}
        vector_rank: dict[str, int] = {}
        rank_offset = self.config.retrieval.reciprocal_rank_k
        for rank, chunk_id in enumerate(lexical, 1):
            lexical_rank[chunk_id] = rank
            rrf_scores[chunk_id] += 1 / (rank_offset + rank)
        for rank, chunk_id in enumerate(vector, 1):
            vector_rank[chunk_id] = rank
            rrf_scores[chunk_id] += 1 / (rank_offset + rank)

        per_case: defaultdict[str, int] = defaultdict(int)
        hits: list[RetrievalHit] = []
        max_per_case = self.config.retrieval.max_chunks_per_case
        final_limit = limit or self.config.retrieval.final_chunks_per_agent
        for chunk_id, score in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True):
            chunk = self.chunks[chunk_id]
            if per_case[chunk.case_id] >= max_per_case:
                continue
            per_case[chunk.case_id] += 1
            hits.append(RetrievalHit(chunk, score, lexical_rank.get(chunk_id), vector_rank.get(chunk_id)))
            if len(hits) >= final_limit:
                break
        return hits

    def evidence_for_agent(self, agent: AgentCard, topic: str, question: str, *, limit: int | None = None) -> list[EvidenceCard]:
        """Return only this agent's window as normal evidence cards."""
        cards = []
        for hit in self.retrieve(agent, topic, question, limit=limit):
            chunk = hit.chunk
            source = chunk.source_records[0] if chunk.source_records else {}
            limitations = "；".join(chunk.verification_gaps) or "未提供额外待核验项"
            cards.append(EvidenceCard(
                evidence_id=f"RAG:{chunk.chunk_id}",
                topic=chunk.topic,
                source_type=_source_type(chunk.source_records),
                source_title=str(source.get("title") or f"外部参考案例 {chunk.case_id}"),
                source_url=str(source.get("url", "")),
                date=str(source.get("published_at", "")),
                actor_type="external_case",
                archetype=agent.archetype,
                stance="reference_only",
                concern_type=ConcernType.GOVERNANCE,
                core_claim=chunk.text,
                evidence_quote=(
                    f"外部参考案例片段 {chunk.chunk_id}，不是当前社区事实。\n"
                    f"{chunk.text}\n"
                    f"待核验事项：{limitations}"
                ),
                reliability_score={"high": 0.8, "medium": 0.6, "low": 0.4}.get(chunk.evidence_level, 0.4),
                usable_agent=agent.agent_id,
            ))
        return cards


def load_knowledge_retriever(
    config: KnowledgeConfig,
    embedder: EmbeddingProvider | None = None,
) -> KnowledgeRetriever | None:
    """Return None when the generated index does not exist yet."""
    if not (config.index_dir / MANIFEST_NAME).exists():
        return None
    retriever = KnowledgeRetriever(config, embedder=embedder)
    return retriever if retriever.is_ready else None

from __future__ import annotations

import json
from pathlib import Path

from ma_deliberation_demo.evidence import retrieve_for_agent
from ma_deliberation_demo.knowledge.config import (
    ChunkingConfig,
    EmbeddingConfig,
    KnowledgeConfig,
    RetrievalConfig,
)
from ma_deliberation_demo.knowledge.indexer import build_knowledge_index
from ma_deliberation_demo.knowledge.retrieval import KnowledgeRetriever
from ma_deliberation_demo.schemas import AgentCard, EvidenceSourceType


class ToyEmbedder:
    """A deterministic test-only embedder; production uses local BGE."""

    model_name = "test-toy-v1"

    def __init__(self) -> None:
        self.document_calls = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        text = text.lower()
        return [
            float(text.count("noise") + text.count("quiet")),
            float(text.count("space") + text.count("relocate")),
            float(text.count("mediation") + text.count("agreement")),
            1.0,
        ]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += len(texts)
        return [self._vector(text) for text in texts]

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


def _case(case_id: str = "C-001") -> dict:
    return {
        "id": case_id,
        "knowledge_type": "external_case",
        "topic": "community dancing noise",
        "region": "example district",
        "scenario": "Night noise affects nearby residents.",
        "deliberation_method": "mediation agreement",
        "evidence_level": "high",
        "summary_for_rag": "An external reference case, not a local fact, about night noise.",
        "stakeholders": ["residents", "dancers"],
        "interventions": ["relocate activity to another space", "set quiet hours"],
        "implementers": ["community"],
        "outcomes": ["temporary agreement"],
        "failure_modes": ["long-term compliance was not verified"],
        "transfer_conditions": ["an alternative space exists"],
        "non_transferable_differences": ["some communities have no spare space"],
        "retrieval_tags": ["noise", "space", "mediation"],
        "verification_gaps": ["long-term complaint data"],
        "source_records": [{
            "title": "Example government case",
            "url": "https://example.gov/case",
            "publisher": "Example government",
            "published_at": "2025-01-01",
            "source_type": "government",
        }],
    }


def _config(tmp_path: Path, source: Path) -> KnowledgeConfig:
    return KnowledgeConfig(
        source_paths=(source,),
        index_dir=tmp_path / "index",
        embedding=EmbeddingConfig(model_name="test-toy-v1", query_prefix=""),
        chunking=ChunkingConfig(max_chars=1200),
        retrieval=RetrievalConfig(final_chunks_per_agent=2, max_chunks_per_case=1),
    )


def _write_cases(path: Path, cases: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8"
    )


def test_index_reuses_unchanged_chunks_and_reembeds_changed_content(tmp_path: Path) -> None:
    source = tmp_path / "cases.jsonl"
    _write_cases(source, [_case()])
    config = _config(tmp_path, source)
    embedder = ToyEmbedder()

    first = build_knowledge_index(config, embedder)
    second = build_knowledge_index(config, embedder)

    changed = _case()
    changed["summary_for_rag"] = "An updated external reference case about quiet hours and night noise."
    _write_cases(source, [changed])
    third = build_knowledge_index(config, embedder)

    assert first.chunk_count == 4
    assert first.embedded_count == 4
    assert second.embedded_count == 0
    assert second.reused_count == 4
    assert third.embedded_count == 1
    assert third.reused_count == 3


def test_shared_index_creates_scoped_agent_evidence_windows(tmp_path: Path) -> None:
    source = tmp_path / "cases.jsonl"
    _write_cases(source, [_case(), _case("C-002")])
    config = _config(tmp_path, source)
    embedder = ToyEmbedder()
    build_knowledge_index(config, embedder)
    retriever = KnowledgeRetriever(config, embedder=embedder)
    resident = AgentCard(
        agent_id="resident", agent_name="resident", archetype="resident",
        relationship_to_topic="affected by night noise", main_interests=["noise", "quiet"],
    )
    manager = AgentCard(
        agent_id="manager", agent_name="manager", archetype="manager",
        relationship_to_topic="coordinates shared space", main_interests=["space", "mediation"],
    )

    resident_cards = retriever.evidence_for_agent(resident, "community dancing", "How should noise be managed?")
    manager_cards = retriever.evidence_for_agent(manager, "community dancing", "How should space be allocated?")

    assert resident_cards and manager_cards
    assert all(card.usable_agent == "resident" for card in resident_cards)
    assert all(card.usable_agent == "manager" for card in manager_cards)
    assert all(card.evidence_id.startswith("RAG:C-") for card in resident_cards + manager_cards)
    assert all(card.source_type == EvidenceSourceType.EXTERNAL_CASE for card in resident_cards + manager_cards)
    assert all("外部参考案例" in card.evidence_quote for card in resident_cards + manager_cards)

    selected_for_resident = retrieve_for_agent(resident, resident_cards + manager_cards)
    selected_for_manager = retrieve_for_agent(manager, resident_cards + manager_cards)
    assert selected_for_resident and selected_for_manager
    assert all(card.usable_agent == "resident" for card in selected_for_resident)
    assert all(card.usable_agent == "manager" for card in selected_for_manager)

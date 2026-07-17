"""Evidence Retriever: matches evidence cards to agents by archetype + concern."""

from __future__ import annotations

import csv
from pathlib import Path

from .schemas import AgentCard, ConcernType, EvidenceCard, EvidenceSourceType


def load_evidence(data_path: str | None = None) -> list[EvidenceCard]:
    """Load evidence cards from CSV."""
    if data_path is None:
        data_path = Path(__file__).parent.parent.parent / "data" / "evidence_cards.csv"

    cards = []
    with open(data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card = EvidenceCard(
                evidence_id=row.get("evidence_id", ""),
                topic=row.get("topic", ""),
                source_type=EvidenceSourceType(row.get("source_type", "12345_complaint")),
                source_title=row.get("source_title", ""),
                source_url=row.get("source_url", ""),
                date=row.get("date", ""),
                actor_type=row.get("actor_type", ""),
                archetype=row.get("archetype", ""),
                stance=row.get("stance", ""),
                concern_type=ConcernType(row.get("concern_type", "social")),
                core_claim=row.get("core_claim", ""),
                evidence_quote=row.get("evidence_quote", ""),
                reliability_score=float(row.get("reliability_score", 0.5)),
                usable_agent=row.get("usable_agent", ""),
            )
            cards.append(card)
    return cards


def retrieve_for_agent(
    agent: AgentCard,
    evidence_pool: list[EvidenceCard],
    max_cards: int = 5,
) -> list[EvidenceCard]:
    """Retrieve evidence cards relevant to an agent.

    Two-stage retrieval:
    L1: Match by archetype / actor_type overlap
    L2: Filter by concern_type relevance and stance compatibility
    """
    direct_matches = []
    matched = []

    for card in evidence_pool:
        # L1: archetype match
        if card.usable_agent:
            # RAG case cards are scoped to one agent_id.  Legacy CSV cards
            # may use an agent name or an archetype, so keep all three forms.
            if card.usable_agent not in {agent.agent_id, agent.agent_name, agent.archetype}:
                continue
            direct_matches.append(card)
            continue
        else:
            # Check if archetype matches loosely
            if card.archetype not in agent.archetype and card.actor_type not in agent.archetype:
                continue

        # L2: concern match (agent interests overlap with card concern)
        concern_match = False
        for interest in agent.main_interests:
            if any(kw in interest for kw in [card.concern_type.value, card.archetype]):
                concern_match = True
                break

        if concern_match or not matched:
            matched.append(card)

    selected = (direct_matches + matched)[:max_cards]
    # Assign evidence IDs to agent. This is also enforced by boundary_checker.
    agent.evidence_ids = [c.evidence_id for c in selected]

    return selected


def format_evidence_context(cards: list[EvidenceCard]) -> str:
    """Format evidence cards as context for LLM prompt."""
    if not cards:
        return "（无可用证据）"

    lines = []
    for i, card in enumerate(cards, 1):
        reliability_label = "高" if card.reliability_score >= 0.7 else ("中" if card.reliability_score >= 0.4 else "低")
        lines.append(
            f"[证据 {i}] {card.evidence_id} | 来源：{card.source_type.value} | "
            f"可信度：{reliability_label}({card.reliability_score})\n"
            f"  标题：{card.source_title}\n"
            f"  核心主张：{card.core_claim}\n"
            f"  原文引用：{card.evidence_quote}"
        )
    return "\n".join(lines)

from __future__ import annotations

import csv
from pathlib import Path
from .schemas import EvidenceCard


def load_evidence_cards(path: str | Path) -> list[EvidenceCard]:
    cards: list[EvidenceCard] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items()}
            row["reliability_score"] = int(row.get("reliability_score") or 3)
            cards.append(EvidenceCard(**row))
    return cards


def retrieve_evidence(
    cards: list[EvidenceCard],
    topic: str,
    agent_name: str = "",
    archetype: str = "",
    concerns: list[str] | None = None,
    stance_hint: str = "",
    top_k: int = 2,
) -> list[EvidenceCard]:
    concerns = concerns or []
    scored: list[tuple[int, EvidenceCard]] = []
    topic_tokens = set(topic.replace("？", "").replace("是否", " ").split())
    for card in cards:
        score = 0
        if card.topic in topic or topic in card.topic:
            score += 6
        if any(tok and tok in card.topic for tok in topic_tokens):
            score += 2
        if archetype and (archetype in card.archetype or card.archetype in archetype):
            score += 5
        if agent_name and card.usable_agent and (card.usable_agent in agent_name or agent_name in card.usable_agent):
            score += 5
        if stance_hint and stance_hint in card.stance:
            score += 2
        for concern in concerns:
            if concern and (concern in card.concern_type or concern in card.core_claim or concern in card.evidence_quote):
                score += 2
        score += card.reliability_score
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in scored[:top_k]]

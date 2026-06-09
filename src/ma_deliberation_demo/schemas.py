from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class EvidenceCard:
    evidence_id: str
    topic: str
    topic_type: str
    source_type: str
    source_title: str
    source_url: str
    date: str
    actor_type: str
    archetype: str
    stance: str
    concern_type: str
    core_claim: str
    evidence_quote: str
    reliability_score: int
    usable_agent: str


@dataclass
class TopicAnalysis:
    topic: str
    topic_type: str
    difficulty: str
    difficulty_score: int
    conflict_dimensions: list[str]
    potential_stakeholders: list[str]
    required_archetypes: list[str]
    suggested_agents: list[str]


@dataclass
class AgentCard:
    agent_id: str
    agent_name: str
    archetype: str
    topic: str
    relationship_to_topic: str
    main_interests: list[str]
    stance: float
    possible_stance: str
    concerns: list[str]
    can_say: list[str]
    cannot_say: list[str]
    tool_permissions: list[str] = field(default_factory=lambda: ["request_evidence"])


@dataclass
class Utterance:
    turn_id: int
    phase: str
    round_id: int
    speaker: str
    speaker_id: str
    content: str
    stance: float
    evidence_ids: list[str] = field(default_factory=list)
    reply_to: str | None = None


@dataclass
class ObserverMetrics:
    speaking_share: dict[str, float]
    speaking_chars: dict[str, int]
    grounding_rate: float
    reply_edges: list[dict[str, Any]]
    stance_history: list[dict[str, Any]]
    consensus_history: list[dict[str, Any]]
    fairness_gini: float
    minority_agents: list[str]


@dataclass
class DeliberationResult:
    topic_analysis: TopicAnalysis
    agents: list[AgentCard]
    transcript: list[Utterance]
    metrics: ObserverMetrics
    report_markdown: str


def to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_dict(value) for key, value in obj.items()}
    return obj

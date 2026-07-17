"""Core data schemas for the multi-agent deliberation system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TopicType(str, Enum):
    PUBLIC_SPACE = "public_space"
    INFRASTRUCTURE = "infrastructure"
    ENVIRONMENT = "environment"
    SOCIAL_SERVICE = "social_service"
    TRANSPORTATION = "transportation"
    HOUSING = "housing"


class ConcernType(str, Enum):
    ECONOMIC = "economic"
    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    HEALTH = "health"
    SAFETY = "safety"
    GOVERNANCE = "governance"
    CULTURAL = "cultural"


class Stance(str, Enum):
    STRONG_SUPPORT = "strong_support"
    SUPPORT = "support"
    CONDITIONAL_SUPPORT = "conditional_support"
    NEUTRAL = "neutral"
    CONDITIONAL_OPPOSE = "conditional_oppose"
    OPPOSE = "oppose"
    STRONG_OPPOSE = "strong_oppose"


class EvidenceSourceType(str, Enum):
    GOV_POLICY = "gov_policy"
    GOV_REPLY = "gov_reply"
    COMPLAINT_12345 = "12345_complaint"
    LEADER_BOARD = "leader_board"
    NPC_PROPOSAL = "npc_proposal"
    CPPCC_PROPOSAL = "cppcc_proposal"
    NEWS = "news"
    ACADEMIC = "academic"
    COURT_CASE = "court_case"
    EXTERNAL_CASE = "external_case"


@dataclass
class ConflictAxis:
    name: str
    parties: list[str]
    intensity: str  # low, medium, high
    description: str = ""


@dataclass
class TopicAnalysis:
    topic_type: TopicType
    conflict_axes: list[ConflictAxis] = field(default_factory=list)
    silent_stakeholders: list[str] = field(default_factory=list)
    power_asymmetry: str = ""
    complexity_score: int = 0
    complexity_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class AgentCard:
    agent_id: str
    agent_name: str
    archetype: str
    relationship_to_topic: str
    main_interests: list[str] = field(default_factory=list)
    possible_stance: str = ""
    stance_score: float = 0.0
    can_say: list[str] = field(default_factory=list)
    cannot_say: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    avatar_color: str = "#6366f1"
    avatar_emoji: str = "?"


@dataclass
class EvidenceCard:
    evidence_id: str
    topic: str
    source_type: EvidenceSourceType
    source_title: str
    source_url: str
    date: str
    actor_type: str
    archetype: str
    stance: str
    concern_type: ConcernType
    core_claim: str
    evidence_quote: str
    reliability_score: float
    usable_agent: str


@dataclass
class Utterance:
    utterance_id: str
    speaker_id: str
    speaker_name: str
    turn: int
    stance_score: float
    reply_to: Optional[str] = None
    evidence_ids: list[str] = field(default_factory=list)
    content: str = ""
    is_boundary_violation: bool = False
    violation_reason: str = ""


@dataclass
class DeliberationState:
    topic: str
    question: str
    turn: int = 0
    max_turns: int = 20
    agents: list[AgentCard] = field(default_factory=list)
    history: list[Utterance] = field(default_factory=list)
    speaker_stats: dict[str, int] = field(default_factory=dict)
    stance_trajectory: dict[str, list[float]] = field(default_factory=dict)
    finished: bool = False


@dataclass
class ObserverMetrics:
    fairness_gini: float = 0.0
    grounding_rate: float = 0.0
    consensus: float = 0.0
    polarization: float = 0.0
    minority_retention: float = 0.0
    reply_graph: dict[str, list[str]] = field(default_factory=dict)
    speaker_share: dict[str, float] = field(default_factory=dict)
    stance_variance_trajectory: list[float] = field(default_factory=list)
    anomaly_flags: list[str] = field(default_factory=list)
    minority_opinions: list[dict] = field(default_factory=list)
    unanswered_questions: list[str] = field(default_factory=list)


@dataclass
class DeliberationReport:
    topic: str
    question: str
    agents: list[AgentCard]
    total_turns: int
    metrics: ObserverMetrics
    transcript: list[Utterance]
    conflict_structure: list[dict]
    consensus_points: list[str]
    divergence_points: list[str]
    minority_opinions: list[dict]
    actionable_proposals: list[dict]
    field_research_questions: list[str]
    generated_at: str = ""

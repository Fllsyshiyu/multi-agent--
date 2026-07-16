"""Fishbowl Engine — inner/outer circle selection, rotation, and round execution.

Key rules (code-driven, not LLM-driven):
  1. Quota-based selection: each round MUST include resident, vulnerable, expert, manager
  2. Priority to less-frequent speakers
  3. Outer circle only receives RoundSummary, not full chat history
  4. Summary MUST preserve minority views (6 required fields)

Configuration (from doc Table 2):
  First Demo: 3-4 inner agents, 2 rounds
  Demo Version: 4-6 inner agents, 2-3 rounds, stratified rotation
"""

from __future__ import annotations

import random
from typing import Any

from .artifacts import (
    DeliberationPlan,
    ObserverSnapshot,
    OuterObservationCard,
    PositionCard,
    RoleType,
    RoundSummary,
    Stance,
)
from .schemas import AgentCard
from .protocols.speaker_scheduler import schedule_speakers


# ── Inner Circle Selection ─────────────────────────────────────────────────

def select_inner_circle(
    agents: list[AgentCard],
    round_no: int,
    max_speakers: int = 4,
    speak_counts: dict[str, int] | None = None,
) -> list[AgentCard]:
    """Quota-based inner circle selection.

    Each round must include at least:
      - 1 RESIDENT or directly-affected stakeholder
      - 1 VULNERABLE / silent stakeholder
      - 1 EXPERT or professional observer
      - 1 MANAGER or governance role

    Ties broken by lower speak_count, then agent_id.
    """
    if speak_counts is None:
        speak_counts = {}

    # Map agent archetypes to role types for quota matching
    resident_types = {"直接受影响者", "直接受益者", "resident"}
    vulnerable_types = {"间接影响者", "silent_stakeholder", "弱势群体", "vulnerable_group"}
    expert_types = {"专业观察者", "expert"}
    manager_types = {"治理方", "manager"}

    def _get_quota_role(agent: AgentCard) -> str:
        arch = agent.archetype
        if arch in resident_types:
            return "resident"
        if arch in vulnerable_types:
            return "vulnerable"
        if arch in expert_types:
            return "expert"
        if arch in manager_types:
            return "manager"
        return "other"

    selected: list[AgentCard] = []
    used_quotas: set[str] = set()

    # Sort candidates by speak_count (fewer first)
    def sort_key(a: AgentCard) -> tuple:
        count = speak_counts.get(a.agent_id, 0)
        return (count, a.agent_id)

    # First pass: fill quotas
    for quota in ["resident", "vulnerable", "expert", "manager"]:
        candidates = [
            a for a in agents
            if _get_quota_role(a) == quota and a not in selected
        ]
        if candidates:
            candidates.sort(key=sort_key)
            selected.append(candidates[0])
            used_quotas.add(quota)

    # Second pass: fill remaining slots
    if len(selected) < max_speakers:
        remaining = [a for a in agents if a not in selected]
        remaining.sort(key=sort_key)
        selected.extend(remaining[:max_speakers - len(selected)])

    return selected


def get_outer_circle(
    agents: list[AgentCard],
    inner: list[AgentCard],
) -> list[AgentCard]:
    """Get agents NOT in the inner circle."""
    inner_ids = {a.agent_id for a in inner}
    return [a for a in agents if a.agent_id not in inner_ids]


def order_inner_circle_speakers(
    inner: list[AgentCard],
    speak_counts: dict[str, int] | None = None,
    last_stance_sign: int | None = None,
) -> list[AgentCard]:
    """Expose the Robert/Fishbowl hybrid speaking order to both API modes."""
    return schedule_speakers(inner, speak_counts, last_stance_sign)


# ── Round Execution ────────────────────────────────────────────────────────

def run_fishbowl_round_simulation(
    agents: list[AgentCard],
    inner: list[AgentCard],
    outer: list[AgentCard],
    round_no: int,
    prior_summary: RoundSummary | None = None,
) -> tuple[list[PositionCard], RoundSummary]:
    """Execute one fishbowl round in simulation mode.

    Each inner agent produces a PositionCard based on their role profile.
    Moderator generates a RoundSummary with 6 required fields.

    Returns (position_cards, round_summary).
    """
    position_cards: list[PositionCard] = []

    for agent in inner:
        card = _simulate_position_card(agent, round_no, prior_summary)
        position_cards.append(card)

    # Generate round summary
    summary = _generate_round_summary(
        cards=position_cards,
        inner_names=[a.agent_name for a in inner],
        outer_names=[a.agent_name for a in outer],
        round_no=round_no,
        prior_summary=prior_summary,
    )

    return position_cards, summary


# ── Simulation helpers ─────────────────────────────────────────────────────

def _simulate_position_card(
    agent: AgentCard,
    round_no: int,
    prior_summary: RoundSummary | None = None,
) -> PositionCard:
    """Generate a rule-based PositionCard from agent profile."""
    # Determine stance from agent's stance_score
    score = agent.stance_score
    if score > 0.3:
        stance = Stance.SUPPORT if score > 0.6 else Stance.CONDITIONAL_SUPPORT
    elif score < -0.3:
        stance = Stance.OPPOSE if score < -0.6 else Stance.CONDITIONAL_OPPOSE
    else:
        stance = Stance.NEUTRAL

    # Claims from interests
    claims = agent.main_interests[:3] if agent.main_interests else [f"{agent.agent_name}的核心诉求"]

    # Non-negotiables from cannot_say (inverted)
    non_negotiables = agent.cannot_say[:2] if agent.cannot_say else ["保持角色立场一致"]

    # Risks from main interests
    risks = [
        f"如果{claim[:30]}不被满足，{agent.agent_name}将面临风险"
        for claim in agent.main_interests[:2]
    ]

    # Suggested changes based on can_say
    suggested = agent.can_say[:2] if agent.can_say else []

    # Confidence based on evidence availability
    confidence = 0.5 + (len(agent.evidence_ids) * 0.1)
    confidence = min(0.95, max(0.3, confidence))

    return PositionCard(
        agent_id=agent.agent_id,
        stakeholder_group=agent.archetype,
        stance=stance,
        claims=claims,
        evidence_ids=agent.evidence_ids[:3],
        non_negotiables=non_negotiables,
        risks=risks,
        suggested_changes=suggested,
        confidence=round(confidence, 2),
        round_no=round_no,
    )


def _generate_round_summary(
    cards: list[PositionCard],
    inner_names: list[str],
    outer_names: list[str],
    round_no: int,
    prior_summary: RoundSummary | None = None,
) -> RoundSummary:
    """Generate a structured round summary from position cards.

    MUST preserve minority views per the doc specification.
    6 required fields:
      1. majority_views
      2. minority_views
      3. unresolved_conflicts
      4. evidence_gaps (证据来源)
      5. involved_groups (涉及的利益群体)
      6. next_round_questions (需要下一轮确认的问题)
    """
    # Classify positions
    supporters = [c for c in cards if c.stance in (Stance.SUPPORT, Stance.CONDITIONAL_SUPPORT)]
    opposers = [c for c in cards if c.stance in (Stance.OPPOSE, Stance.CONDITIONAL_OPPOSE)]
    neutrals = [c for c in cards if c.stance == Stance.NEUTRAL]

    # Majority views: from the larger group
    majority_group = supporters if len(supporters) >= len(opposers) else opposers
    majority_views = []
    for c in majority_group:
        for claim in c.claims[:2]:
            majority_views.append(f"[{c.stakeholder_group}] {claim}")

    # Minority views: from the smaller group AND neutral agents
    minority_group = opposers if len(supporters) >= len(opposers) else supporters
    minority_views = []
    for c in minority_group:
        for claim in c.claims[:1]:
            minority_views.append(f"[{c.stakeholder_group}] {claim}")
    for c in neutrals:
        for claim in c.claims[:1]:
            minority_views.append(f"[{c.stakeholder_group}] {claim}")

    # Unresolved conflicts: opposing stances on same topics
    unresolved_conflicts = []
    if supporters and opposers:
        unresolved_conflicts.append(
            f"立场分歧：{', '.join(c.stakeholder_group for c in supporters)} (支持) "
            f"vs {', '.join(c.stakeholder_group for c in opposers)} (反对)"
        )

    # Non-negotiable conflicts
    all_non_negotiables = []
    for c in cards:
        for nn in c.non_negotiables[:1]:
            all_non_negotiables.append(f"[{c.stakeholder_group}] {nn}")
    if len(all_non_negotiables) >= 2:
        unresolved_conflicts.append(f"底线冲突：{'；'.join(all_non_negotiables[:4])}")

    # Evidence gaps: agents with low evidence or weak confidence
    evidence_gaps = []
    for c in cards:
        if len(c.evidence_ids) == 0:
            evidence_gaps.append(f"{c.stakeholder_group} 未引用任何证据")
        elif c.confidence < 0.5:
            evidence_gaps.append(f"{c.stakeholder_group} 置信度仅 {c.confidence:.0%}，证据基础薄弱")

    # Involved groups
    involved_groups = list(set(c.stakeholder_group for c in cards))

    # Next round questions
    next_round_questions = []
    for c in cards:
        for risk in c.risks[:1]:
            if "风险" in risk or "成本" in risk or "如何" in risk:
                next_round_questions.append(f"如何应对{c.stakeholder_group}提出的风险：{risk[:60]}")

    if not next_round_questions:
        # Synthesize from unresolved conflicts
        for uc in unresolved_conflicts[:2]:
            next_round_questions.append(f"需要进一步讨论：{uc[:80]}")

    # If prior summary exists, carry forward unresolved items
    if prior_summary and prior_summary.unresolved_conflicts:
        carry_over = [
            uc for uc in prior_summary.unresolved_conflicts[:2]
            if uc not in str(unresolved_conflicts)
        ]
        if carry_over:
            unresolved_conflicts.extend(carry_over)

    return RoundSummary(
        round_no=round_no,
        inner_circle=inner_names,
        majority_views=majority_views[:6],
        minority_views=minority_views[:4],
        unresolved_conflicts=unresolved_conflicts[:4],
        evidence_gaps=evidence_gaps[:3],
        next_round_questions=next_round_questions[:3],
        involved_groups=involved_groups,
    )


# ── S5: Deliberation Plan Generation ───────────────────────────────────────

def generate_deliberation_plan(
    agent: AgentCard,
    round_no: int,
    prior_summary: RoundSummary | None = None,
    topic: str = "",
) -> DeliberationPlan:
    """Generate a Deliberation Plan for an inner-circle agent before speaking.

    Per SOP v1.2 S5: each inner agent must state round_goal, core_interest,
    non_negotiables, possible_concessions, question_to_others, and evidence_to_use.
    Generated deterministically from agent profile + prior round context.
    """
    # Core interest: primary from main_interests
    core_interest = agent.main_interests[0] if agent.main_interests else "表达核心诉求"

    # Non-negotiables from cannot_say (inverted — what they insist on)
    non_negotiables = agent.cannot_say[:2] if agent.cannot_say else ["维护本群体基本权益"]

    # Possible concessions from can_say (areas of flexibility)
    possible_concessions = agent.can_say[:2] if agent.can_say else ["接受有条件方案"]

    # Question to others based on prior unresolved conflicts
    question_to_others = ""
    if prior_summary and prior_summary.unresolved_conflicts:
        question_to_others = prior_summary.unresolved_conflicts[0][:80]
    elif prior_summary and prior_summary.next_round_questions:
        question_to_others = prior_summary.next_round_questions[0]
    else:
        # Default question based on stance
        if agent.stance_score > 0.3:
            question_to_others = "其他群体对方案的可接受条件是什么？"
        elif agent.stance_score < -0.3:
            question_to_others = "方案设计方如何回应我们的核心关切？"
        else:
            question_to_others = "各方能否提出具体的折中参数？"

    # Round goal depends on round_no
    if round_no == 1:
        round_goal = f"清晰表达{agent.agent_name}的核心立场和不可接受条件"
    elif round_no == 2:
        round_goal = f"回应上一轮遗漏问题，对具体参数提出修正建议"
    else:
        round_goal = f"推动方案收敛，明确{agent.agent_name}的最终条件"

    return DeliberationPlan(
        plan_id=f"plan_r{round_no}_{agent.agent_id}",
        agent_id=agent.agent_id,
        agent_name=agent.agent_name,
        round_id=round_no,
        round_goal=round_goal,
        core_interest=core_interest,
        non_negotiables=non_negotiables,
        possible_concessions=possible_concessions,
        question_to_others=question_to_others,
        evidence_to_use=agent.evidence_ids[:3],
        produced_by=agent.agent_id,
        input_refs=[],
    )


# ── S7: Outer Observations ─────────────────────────────────────────────────

def run_outer_observations(
    outer_agents: list[AgentCard],
    inner_agent_names: list[str],
    round_no: int,
    inner_topics: list[str] | None = None,
) -> list[OuterObservationCard]:
    """Generate Outer Observation Cards from outer-circle agents.

    Per SOP v1.2 S7: outer agents don't speak but must record what was missed,
    objections, missing evidence, and whether they want to enter inner circle.
    """
    inner_topics = inner_topics or []
    cards = []

    for i, agent in enumerate(outer_agents):
        # Missed issue: what the agent's perspective was not addressed
        missed = ""
        if agent.main_interests:
            missed_topic = agent.main_interests[0]
            if not any(missed_topic[:10] in t for t in inner_topics):
                missed = f"内圈讨论未充分涉及{agent.agent_name}的核心关切：{missed_topic}"
            else:
                missed = f"{agent.agent_name}希望补充关于{missed_topic}的具体数据"

        # Objection: if agent has opposing stance, record it
        objection = ""
        if agent.stance_score < -0.3:
            objection = f"{agent.agent_name}对内圈的主流方向持保留意见：{agent.main_interests[0] if agent.main_interests else '核心利益未获保障'}"
        elif agent.cannot_say:
            objection = f"{agent.agent_name}关注：{agent.cannot_say[0][:60]}"

        # Evidence needed
        evidence_needed = []
        if not agent.evidence_ids:
            evidence_needed = [f"{agent.agent_name}相关的一手数据或案例"]

        # Request to enter inner circle: if agent has strong stance and wasn't heard
        request_to_enter = agent.stance_score < -0.2 or agent.stance_score > 0.5
        reason = ""
        if request_to_enter:
            reason = f"{agent.agent_name}的{'反对' if agent.stance_score < -0.2 else '支持'}立场需要被更充分讨论"

        cards.append(OuterObservationCard(
            card_id=f"obs_r{round_no}_{agent.agent_id}",
            observer_id=agent.agent_id,
            observer_name=agent.agent_name,
            round_id=round_no,
            missed_issue=missed,
            objection=objection,
            evidence_needed=evidence_needed,
            request_to_enter_inner_circle=request_to_enter,
            reason_to_enter=reason,
            produced_by=agent.agent_id,
        ))

    # Sort: agents requesting inner circle entry come first
    cards.sort(key=lambda c: not c.request_to_enter_inner_circle)
    return cards


# ── S8: Observer Snapshot ───────────────────────────────────────────────────

def compute_observer_snapshot(
    utterances: list[dict],
    agents: list[AgentCard],
    round_no: int,
    round_summary: RoundSummary | None = None,
) -> ObserverSnapshot:
    """Compute per-round metrics quantifying deliberation quality.

    Per SOP v1.2 S8: tracks speaker fairness, evidence grounding,
    minority retention, and boundary violations.
    """
    if not utterances:
        return ObserverSnapshot(
            snapshot_id=f"snap_r{round_no}",
            round_id=round_no,
            produced_by="Observer",
        )

    # Speaker share
    total_chars = sum(len(u.get("content", "")) for u in utterances)
    speaker_share = {}
    if total_chars > 0:
        for u in utterances:
            name = u.get("speaker", u.get("agent_name", "?"))
            chars = len(u.get("content", ""))
            speaker_share[name] = round(chars / total_chars, 3)

    # Grounding rate: fraction of utterances with evidence references
    grounded = sum(
        1 for u in utterances
        if u.get("evidence_ids") and len(u.get("evidence_ids", [])) > 0
    )
    grounding_rate = round(grounded / len(utterances), 2) if utterances else 0.0

    # Minority retention: check if minority views appear in summary
    minority_retention = 0.0
    if round_summary:
        has_minority = bool(round_summary.minority_views)
        has_conflicts = bool(round_summary.unresolved_conflicts)
        minority_retention = 0.75 if (has_minority and has_conflicts) else (0.5 if has_minority else 0.25)

    # Role boundary violations: heuristically detect
    role_violations = 0
    for u in utterances:
        content = u.get("content", "")
        # Check for generic "everyone agrees" language (pseudo-consensus marker)
        pseudo_markers = ["大家一致", "所有人都同意", "没有分歧", "各方都"]
        if any(m in content for m in pseudo_markers):
            role_violations += 0.5

    # Unanswered questions from summary
    unanswered = round_summary.next_round_questions[:3] if round_summary else []

    # Anomaly flags
    anomaly_flags = []
    if grounding_rate < 0.3:
        anomaly_flags.append(f"证据引用率仅{grounding_rate:.0%}，低于30%阈值")
    if round_summary and round_summary.majority_views and not round_summary.minority_views:
        anomaly_flags.append("疑似假共识：多数意见存在但少数意见为空")
    # Check for speaker dominance (>40% share)
    for name, share in speaker_share.items():
        if share > 0.4:
            anomaly_flags.append(f"发言失衡：{name}占据{share:.0%}发言份额")

    return ObserverSnapshot(
        snapshot_id=f"snap_r{round_no}",
        round_id=round_no,
        speaker_share=speaker_share,
        grounding_rate=grounding_rate,
        minority_retention=minority_retention,
        role_boundary_violations=int(role_violations),
        unanswered_questions=unanswered,
        anomaly_flags=anomaly_flags,
        produced_by="Observer",
    )


# ── Run All Rounds ─────────────────────────────────────────────────────────

def run_all_fishbowl_rounds(
    agents: list[AgentCard],
    max_rounds: int = 2,
    max_speakers: int = 4,
) -> tuple[list[PositionCard], list[RoundSummary], list[dict]]:
    """Execute all fishbowl rounds, tracking state externally.

    Returns:
      - all_position_cards: flattened list of all cards from all rounds
      - round_summaries: one summary per round
      - round_events: list of {type, data} for SSE streaming
    """
    speak_counts: dict[str, int] = {}
    all_cards: list[PositionCard] = []
    all_deliberation_plans: list[DeliberationPlan] = []
    all_outer_observations: list[OuterObservationCard] = []
    all_snapshots: list[ObserverSnapshot] = []
    round_summaries: list[RoundSummary] = []
    round_events: list[dict] = []
    prior_summary: RoundSummary | None = None
    participants = [a for a in agents if a.archetype not in ("主持人", "评审员")]

    for r in range(max_rounds):
        round_no = r + 1

        # Select inner circle with quota
        inner = select_inner_circle(participants, round_no, max_speakers, speak_counts)
        inner = order_inner_circle_speakers(inner, speak_counts)
        outer = get_outer_circle(participants, inner)

        # Update speak counts
        for a in inner:
            speak_counts[a.agent_id] = speak_counts.get(a.agent_id, 0) + 1

        # Emit fishbowl inner/outer selection
        round_events.append({
            "type": "fishbowl_inner",
            "round_no": round_no,
            "agents": [
                {"id": a.agent_id, "name": a.agent_name, "emoji": a.avatar_emoji, "color": a.avatar_color}
                for a in inner
            ],
        })
        round_events.append({
            "type": "fishbowl_outer",
            "round_no": round_no,
            "agents": [
                {"id": a.agent_id, "name": a.agent_name, "emoji": a.avatar_emoji, "color": a.avatar_color}
                for a in outer
            ],
        })

        # ── S5: Deliberation Plans for inner agents ──
        plans = []
        for agent in inner:
            plan = generate_deliberation_plan(agent, round_no, prior_summary)
            plans.append(plan)
            all_deliberation_plans.append(plan)
            round_events.append({
                "type": "deliberation_plan",
                "plan": _plan_to_dict(plan),
            })

        # Execute round
        cards, summary = run_fishbowl_round_simulation(
            agents=agents,
            inner=inner,
            outer=outer,
            round_no=round_no,
            prior_summary=prior_summary,
        )

        # Emit position cards
        for card in cards:
            round_events.append({
                "type": "position_card",
                "card": _card_to_dict(card),
            })

        # ── S7: Outer Observations ──
        inner_topics = []
        for card in cards:
            inner_topics.extend(card.claims)
        observations = run_outer_observations(outer, [a.agent_name for a in inner], round_no, inner_topics)
        all_outer_observations.extend(observations)
        for obs in observations:
            round_events.append({
                "type": "outer_observation",
                "observation": _observation_to_dict(obs),
            })

        # ── S8: Observer Snapshot ──
        utterances = []
        for c_idx, card in enumerate(cards):
            utterances.append({
                "speaker": inner[c_idx].agent_name if c_idx < len(inner) else "?",
                "content": card.claims[0] if card.claims else "",
                "evidence_ids": card.evidence_ids,
            })
        snapshot = compute_observer_snapshot(utterances, agents, round_no, summary)
        all_snapshots.append(snapshot)
        round_events.append({
            "type": "observer_snapshot",
            "snapshot": _snapshot_to_dict(snapshot),
        })

        # Emit round summary
        round_events.append({
            "type": "round_summary",
            "summary": _summary_to_dict(summary),
        })

        all_cards.extend(cards)
        round_summaries.append(summary)
        prior_summary = summary

    return all_cards, round_summaries, round_events


# ── Serialization helpers ──────────────────────────────────────────────────

def _card_to_dict(card: PositionCard) -> dict:
    return {
        "agent_id": card.agent_id,
        "stakeholder_group": card.stakeholder_group,
        "stance": card.stance.value,
        "claims": card.claims,
        "evidence_ids": card.evidence_ids,
        "non_negotiables": card.non_negotiables,
        "risks": card.risks,
        "suggested_changes": card.suggested_changes,
        "confidence": card.confidence,
        "round_no": card.round_no,
    }


def _summary_to_dict(s: RoundSummary) -> dict:
    return {
        "round_no": s.round_no,
        "inner_circle": s.inner_circle,
        "majority_views": s.majority_views,
        "minority_views": s.minority_views,
        "unresolved_conflicts": s.unresolved_conflicts,
        "evidence_gaps": s.evidence_gaps,
        "next_round_questions": s.next_round_questions,
        "involved_groups": s.involved_groups,
    }


def _plan_to_dict(p: DeliberationPlan) -> dict:
    return {
        "plan_id": p.plan_id,
        "agent_id": p.agent_id,
        "agent_name": p.agent_name,
        "round_id": p.round_id,
        "round_goal": p.round_goal,
        "core_interest": p.core_interest,
        "non_negotiables": p.non_negotiables,
        "possible_concessions": p.possible_concessions,
        "question_to_others": p.question_to_others,
        "evidence_to_use": p.evidence_to_use,
    }


def _observation_to_dict(o: OuterObservationCard) -> dict:
    return {
        "card_id": o.card_id,
        "observer_id": o.observer_id,
        "observer_name": o.observer_name,
        "round_id": o.round_id,
        "missed_issue": o.missed_issue,
        "objection": o.objection,
        "evidence_needed": o.evidence_needed,
        "request_to_enter_inner_circle": o.request_to_enter_inner_circle,
        "reason_to_enter": o.reason_to_enter,
    }


def _snapshot_to_dict(s: ObserverSnapshot) -> dict:
    return {
        "snapshot_id": s.snapshot_id,
        "round_id": s.round_id,
        "speaker_share": s.speaker_share,
        "grounding_rate": s.grounding_rate,
        "minority_retention": s.minority_retention,
        "role_boundary_violations": s.role_boundary_violations,
        "unanswered_questions": s.unanswered_questions,
        "anomaly_flags": s.anomaly_flags,
    }

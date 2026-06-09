from __future__ import annotations

from statistics import pvariance
from .schemas import AgentCard, ObserverMetrics, Utterance


def _gini(values: list[float]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    cumulative = sum((i + 1) * value for i, value in enumerate(sorted_values))
    return (2 * cumulative) / (n * sum(sorted_values)) - (n + 1) / n


def compute_metrics(transcript: list[Utterance], agents: list[AgentCard]) -> ObserverMetrics:
    agent_names = [agent.agent_name for agent in agents]
    chars = {name: 0 for name in agent_names}
    evidence_turns = 0
    agent_turns = 0
    edges: list[dict] = []
    stance_history: list[dict] = []

    for utt in transcript:
        if utt.speaker in chars:
            chars[utt.speaker] += len(utt.content)
            agent_turns += 1
            if utt.evidence_ids:
                evidence_turns += 1
            stance_history.append({
                "turn_id": utt.turn_id,
                "round_id": utt.round_id,
                "phase": utt.phase,
                "agent": utt.speaker,
                "stance": round(utt.stance, 3),
            })
            if utt.reply_to:
                edges.append({"source": utt.speaker, "target": utt.reply_to, "turn_id": utt.turn_id})

    total_chars = sum(chars.values()) or 1
    share = {name: round(chars[name] / total_chars, 4) for name in agent_names}
    grounding_rate = round(evidence_turns / agent_turns, 4) if agent_turns else 0.0

    consensus_history: list[dict] = []
    by_round: dict[int, dict[str, float]] = {}
    for item in stance_history:
        by_round.setdefault(item["round_id"], {})[item["agent"]] = item["stance"]
    latest = {agent.agent_name: agent.stance for agent in agents}
    for round_id in sorted(by_round):
        latest.update(by_round[round_id])
        values = list(latest.values())
        variance = pvariance(values) if len(values) > 1 else 0.0
        consensus_history.append({
            "round_id": round_id,
            "stance_variance": round(variance, 4),
            "consensus_score": round(max(0.0, 1.0 - min(variance, 1.0)), 4),
        })

    expected_share = 1 / max(len(agent_names), 1)
    minority_agents = [name for name, val in share.items() if val < expected_share * 0.65]

    return ObserverMetrics(
        speaking_share=share,
        speaking_chars=chars,
        grounding_rate=grounding_rate,
        reply_edges=edges,
        stance_history=stance_history,
        consensus_history=consensus_history,
        fairness_gini=round(_gini(list(chars.values())), 4),
        minority_agents=minority_agents,
    )

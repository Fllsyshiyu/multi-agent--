"""Observer: computes fairness, consensus, grounding rate, polarization, and anomaly flags."""

from __future__ import annotations

import math

from .schemas import (
    AgentCard,
    DeliberationState,
    ObserverMetrics,
    Utterance,
)


def compute_metrics(state: DeliberationState) -> ObserverMetrics:
    """Compute all observer metrics from the deliberation state."""
    if not state.history:
        return ObserverMetrics()

    metrics = ObserverMetrics()

    # 1. Speaker share
    total_utterances = len(state.history)
    metrics.speaker_share = {
        a.agent_name: state.speaker_stats.get(a.agent_id, 0) / max(total_utterances, 1)
        for a in state.agents
    }

    # 2. Fairness Gini (lower is more fair)
    metrics.fairness_gini = _compute_gini(list(metrics.speaker_share.values()))

    # 3. Grounding rate
    grounded = sum(1 for u in state.history if u.evidence_ids)
    metrics.grounding_rate = grounded / max(total_utterances, 1)

    # 4. Consensus (1 - normalized stance variance)
    current_stances = _get_current_stances(state)
    if len(current_stances) > 1:
        mean_stance = sum(current_stances.values()) / len(current_stances)
        variance = sum((v - mean_stance) ** 2 for v in current_stances.values()) / len(current_stances)
        # Normalize: max variance for scores in [-1, 1] is 1.0 (when half at -1, half at +1)
        metrics.consensus = 1.0 - min(variance, 1.0)

        # Track variance trajectory
        metrics.stance_variance_trajectory = _compute_variance_trajectory(state)

        # Initial vs final consensus
        if state.stance_trajectory:
            initial_stances = {aid: scores[0] for aid, scores in state.stance_trajectory.items() if scores}
            if len(initial_stances) > 1:
                init_mean = sum(initial_stances.values()) / len(initial_stances)
                init_var = sum((v - init_mean) ** 2 for v in initial_stances.values()) / len(initial_stances)
                # We track this in the report, not directly in metrics
    else:
        metrics.consensus = 1.0

    # 5. Polarization (max pairwise stance distance)
    stance_list = list(current_stances.values())
    max_dist = 0.0
    for i in range(len(stance_list)):
        for j in range(i + 1, len(stance_list)):
            dist = abs(stance_list[i] - stance_list[j])
            if dist > max_dist:
                max_dist = dist
    metrics.polarization = max_dist / 2.0  # normalize to [0, 1]

    # 6. Reply graph
    metrics.reply_graph = _build_reply_graph(state)

    # 7. Minority retention
    metrics.minority_retention = _compute_minority_retention(state)

    # 8. Anomaly flags
    metrics.anomaly_flags = _detect_anomalies(state, metrics)

    # 9. Minority opinions
    metrics.minority_opinions = _extract_minority_opinions(state)

    # 10. Unanswered questions
    metrics.unanswered_questions = _find_unanswered(state)

    return metrics


def _get_current_stances(state: DeliberationState) -> dict[str, float]:
    """Get the most recent stance for each agent."""
    stances = {}
    for agent in state.agents:
        trajectory = state.stance_trajectory.get(agent.agent_id, [])
        if trajectory:
            stances[agent.agent_name] = trajectory[-1]
        else:
            stances[agent.agent_name] = agent.stance_score
    return stances


def _compute_gini(values: list[float]) -> float:
    """Compute Gini coefficient."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    index_sum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    gini = (2 * index_sum) / (n * sum(sorted_vals)) - (n + 1) / n
    return round(max(0.0, gini), 4)


def _compute_variance_trajectory(state: DeliberationState) -> list[float]:
    """Compute stance variance after each turn."""
    variances = []
    for t in range(1, len(state.history) + 1):
        stances_at_t = {}
        for agent in state.agents:
            traj = state.stance_trajectory.get(agent.agent_id, [])
            relevant = [s for i, s in enumerate(traj) if _turn_of_stance(state, agent.agent_id, i) <= t]
            if relevant:
                stances_at_t[agent.agent_name] = relevant[-1]
            else:
                stances_at_t[agent.agent_name] = agent.stance_score
        if len(stances_at_t) > 1:
            mean_s = sum(stances_at_t.values()) / len(stances_at_t)
            var = sum((v - mean_s) ** 2 for v in stances_at_t.values()) / len(stances_at_t)
            variances.append(round(var, 4))
    return variances


def _turn_of_stance(state: DeliberationState, agent_id: str, stance_idx: int) -> int:
    """Map stance index to turn number."""
    count = 0
    for u in state.history:
        if u.speaker_id == agent_id:
            if count == stance_idx:
                return u.turn
            count += 1
    return 999


def _build_reply_graph(state: DeliberationState) -> dict[str, list[str]]:
    """Build directed reply graph: speaker -> [who they replied to]."""
    graph = {}
    for u in state.history:
        if u.speaker_name not in graph:
            graph[u.speaker_name] = []
        if u.reply_to:
            graph[u.speaker_name].append(u.reply_to)
    return graph


def _compute_minority_retention(state: DeliberationState) -> float:
    """Check if minority/silent stakeholders were responded to."""
    silent_keywords = ["环卫", "弱势", "低收入", "外来"]
    minority_mentions = 0
    minority_replies = 0
    for u in state.history:
        for kw in silent_keywords:
            if kw in u.content:
                minority_mentions += 1
                break
        if u.reply_to:
            for kw in silent_keywords:
                if kw in u.reply_to:
                    minority_replies += 1
                    break
    if minority_mentions == 0:
        return 0.0
    return minority_replies / minority_mentions


def _detect_anomalies(state: DeliberationState, metrics: ObserverMetrics) -> list[str]:
    """Detect deliberation anomalies."""
    flags = []

    # Check for viewpoint collapse (variance dropping too fast)
    if len(metrics.stance_variance_trajectory) >= 3:
        recent = metrics.stance_variance_trajectory[-3:]
        if recent[0] > 0.1 and recent[-1] < 0.02:
            flags.append("观点坍缩警告：立场方差在最近 3 轮快速下降，可能存在过早趋同")

    # Check for speaker dominance
    if metrics.speaker_share:
        max_share = max(metrics.speaker_share.values())
        if max_share > 0.35:
            dominant = [k for k, v in metrics.speaker_share.items() if v == max_share]
            flags.append(f"发言支配警告：{dominant[0]} 发言占比 {max_share:.0%}，超过 35% 阈值")

    # Check for ungrounded discussion
    if metrics.grounding_rate < 0.3:
        flags.append(f"证据不足警告：Grounding 率仅 {metrics.grounding_rate:.0%}")

    # Check for unaddressed minority
    if metrics.minority_retention < 0.2:
        flags.append("少数意见遗漏警告：沉默群体意见被回应率过低")

    # Check for false consensus (high consensus but no actionable details)
    if metrics.consensus > 0.85:
        has_specifics = any(
            kw in " ".join(u.content for u in state.history)
            for kw in ["资金", "经费", "成本", "预算", "时间", "试点", "KPI"]
        )
        if not has_specifics:
            flags.append("疑似假共识：共识度很高但缺乏具体可执行约束")

    return flags


def _extract_minority_opinions(state: DeliberationState) -> list[dict]:
    """Extract opinions from minority/silent stakeholders that may not be resolved."""
    minority_opinions = []
    silent_agents = [
        a for a in state.agents
        if a.archetype in ("silent_stakeholder", "弱势群体", "间接影响者")
        or "环卫" in a.agent_name
        or "外来" in a.agent_name
    ]

    for agent in silent_agents:
        agent_utterances = [u for u in state.history if u.speaker_id == agent.agent_id]
        if agent_utterances:
            last_utt = agent_utterances[-1]
            was_responded = any(u.reply_to == agent.agent_name for u in state.history)
            opinion = {
                "agent": agent.agent_name,
                "opinion": last_utt.content[:200],
                "responded": was_responded,
                "included_in_final": False,
            }
            if not was_responded:
                opinion["reason_unresolved"] = "该意见未被其他角色直接回应"
            minority_opinions.append(opinion)

    return minority_opinions


def _find_unanswered(state: DeliberationState) -> list[str]:
    """Find questions raised but not addressed."""
    question_keywords = ["谁来", "如何保证", "费用从哪里", "怎么监督", "如果.*怎么办"]
    unanswered = []
    for u in state.history:
        for kw in question_keywords:
            if kw in u.content:
                # Check if any subsequent utterance addresses it
                addressed = False
                for later_u in state.history:
                    if later_u.turn > u.turn and u.speaker_name in later_u.content:
                        addressed = True
                        break
                if not addressed:
                    unanswered.append(f"[{u.speaker_name}] {u.content[:150]}...")
                break
    return unanswered[:5]

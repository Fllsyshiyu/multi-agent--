"""Boundary Checker: validates agent utterances against role constraints.

Detects:
  - Role drift: agent speaks outside its can_say / cannot_say boundaries
  - Evidence misuse: agent cites evidence assigned to other roles
  - Over-generalization: agent uses generic "expert" language instead of role-specific voice
"""

from __future__ import annotations

import re

from .schemas import AgentCard, Utterance


def check_utterance(utterance: Utterance, agent: AgentCard) -> tuple[bool, str]:
    """Check if an utterance violates the agent's role boundaries.

    Returns (is_valid, reason).
    """
    content = utterance.content

    # Check cannot_say violations
    for prohibited in agent.cannot_say:
        # Use simple keyword matching for the prohibited topics
        keywords = _extract_keywords(prohibited)
        for kw in keywords:
            if kw in content:
                return False, f"违反发言边界：{agent.agent_name} 不能 {prohibited}（检测到关键词: {kw}）"

    # Check evidence ownership
    for eid in utterance.evidence_ids:
        if eid not in agent.evidence_ids:
            return False, f"证据错配：{agent.agent_name} 引用了不属于自己的证据 {eid}"

    # Check for role voice drift (generic expert language)
    drift_signals = [
        "从宏观战略角度来看",
        "综合各方面因素",
        "经过全面分析",
        "我们应该以科学发展观为指导",
        "从城市总体规划层面",
    ]
    for signal in drift_signals:
        if signal in content:
            return True, f"角色漂移警告（非阻断）：{agent.agent_name} 使用了通用官方语言"

    # Check for stance consistency (major deviation only)
    # This is a soft check - small deviations are natural in deliberation

    return True, ""


def check_interaction_norms(content: str) -> tuple[bool, str]:
    """Reject clear relationship-conflict language while preserving disagreement.

    This intentionally catches only explicit harmful phrasing. Semantic
    disagreement and criticism of a proposal remain legitimate task conflict.
    """
    prohibited = ["闭嘴", "不配发言", "你们根本不懂", "你就是自私", "无知的人"]
    for phrase in prohibited:
        if phrase in content:
            return False, f"互动规范提醒：检测到“{phrase}”，请改为针对主张、证据或后果的表达"
    return True, ""


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a boundary description."""
    # Remove common negation prefixes
    text = re.sub(r'不能|不可以|不允许|不得', '', text)
    # Split into meaningful chunks
    keywords = []
    for chunk in re.split(r'[，。、；\s]+', text):
        chunk = chunk.strip()
        if len(chunk) >= 2:
            keywords.append(chunk)
    return keywords


def check_evidence_grounding(
    utterance: Utterance,
    evidence_quotes: list[str],
) -> float:
    """Compute a simple grounding score: what fraction of factual claims
    in the utterance can be traced to evidence quotes.

    Returns a score from 0.0 to 1.0.
    """
    if not evidence_quotes:
        return 0.0

    content = utterance.content
    matched = 0
    total_claims = 0

    # Split into sentences as rough claim boundaries
    sentences = re.split(r'[。！？]', content)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 5:
            continue
        total_claims += 1
        # Check if any evidence quote overlaps with this sentence
        for quote in evidence_quotes:
            # Simple overlap check: any 4-character substring from quote appears in sentence
            for i in range(len(quote) - 3):
                if quote[i:i+4] in sent:
                    matched += 1
                    break

    if total_claims == 0:
        return 0.0
    return matched / total_claims

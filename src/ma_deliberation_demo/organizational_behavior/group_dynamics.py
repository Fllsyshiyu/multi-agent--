"""Deterministic signals for common group-decision failure modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
import re


@dataclass
class BehaviorAssessment:
    speaker_dominance: float = 0.0
    participation_coverage: float = 0.0
    evidence_balance: float = 0.0
    groupthink_risk: float = 0.0
    psychological_safety_risk: float = 0.0
    information_sharing_risk: float = 0.0
    confirmation_bias_risk: float = 0.0
    flags: list[str] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)


def assess_group_dynamics(utterances: list[dict], expected_speakers: list[str] | None = None) -> BehaviorAssessment:
    """Assess only observable discussion patterns; never infer personal traits."""
    result = BehaviorAssessment()
    if not utterances:
        return result

    expected = set(expected_speakers or [])
    speakers = [u.get("speaker", u.get("agent_name", "")) for u in utterances]
    counts = Counter(s for s in speakers if s)
    result.participation_coverage = round(len(counts) / max(len(expected), len(counts), 1), 3)
    result.speaker_dominance = round(max(counts.values()) / len(speakers), 3) if counts else 0.0
    grounded = sum(bool(u.get("evidence_ids")) for u in utterances)
    result.evidence_balance = round(grounded / len(utterances), 3)

    text = " ".join(u.get("content", "") for u in utterances)
    consensus_markers = ["大家一致", "所有人都同意", "没有分歧", "完全赞同"]
    dissent_markers = ["不同意", "反对", "担忧", "风险", "条件", "例外"]
    attacks = ["你们根本不懂", "不配", "自私", "无知", "别说了", "闭嘴"]
    unique_numbers = set(re.findall(r"\d+(?:\.\d+)?(?:%|元|点|个月|小时)?", text))

    if any(marker in text for marker in consensus_markers) and not any(marker in text for marker in dissent_markers):
        result.groupthink_risk = 0.8
        result.flags.append("群体迷思风险：出现一致性表述，但未见明确异议或失败条件")
        result.interventions.append("请每位参与者提出一个方案失败条件或未被满足的底线。")
    elif result.speaker_dominance > 0.4:
        result.groupthink_risk = 0.5

    if result.speaker_dominance > 0.35:
        dominant = max(counts, key=counts.get)
        result.flags.append(f"发言支配风险：{dominant} 占 {result.speaker_dominance:.0%} 发言次数")
        result.interventions.append("暂停高频发言者，优先邀请尚未发言或发言较少的利益方。")
    if expected and set(expected) - set(counts):
        missing = "、".join(sorted(expected - set(counts)))
        result.flags.append(f"参与覆盖不足：{missing} 尚未获得正式发言机会")
        result.interventions.append("在进入下一程序阶段前，邀请未发言利益方表达其不可退让条件。")

    if any(marker in text for marker in attacks):
        result.psychological_safety_risk = 0.9
        result.flags.append("心理安全风险：检测到可能的人身贬损或压制性措辞")
        result.interventions.append("主持人应要求重述为针对主张、证据和后果的表达。")
    if result.evidence_balance < 0.3:
        result.information_sharing_risk = 0.7
        result.flags.append("信息共享风险：多数发言未携带可核验的证据引用")
        result.interventions.append("暂停收敛，明确列出每个关键主张所需的数据或证据来源。")
    if len(unique_numbers) <= 1 and any(k in text for k in ["预算", "费用", "时间", "补偿"]):
        result.confirmation_bias_risk = 0.5
        result.flags.append("锚定/确认偏误风险：关键参数缺少多个来源或替代方案比较")
        result.interventions.append("要求提出至少一个反向证据、替代参数或敏感性条件。")

    return result

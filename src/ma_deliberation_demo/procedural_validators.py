"""Validation gates for procedural readiness and respectful interaction."""

from __future__ import annotations

from .artifacts import GateCheckResult, MotionStatus, RoundSummary
from .protocols.protocol_runtime import ProtocolRuntime


def gate_procedural_readiness(
    runtime: ProtocolRuntime,
    summary: RoundSummary | None,
    stage_id: str = "S11",
) -> GateCheckResult:
    motion = runtime.current_motion
    issues: list[str] = []
    if not motion:
        issues.append("尚未登记待决议案")
    elif motion.status not in {MotionStatus.DEBATE_OPEN, MotionStatus.VOTING}:
        issues.append(f"当前议案状态为 {motion.status.value}，不具备收敛条件")
    if not summary or not summary.minority_views:
        issues.append("未保留少数意见，不能把文本趋同视为共识")
    if summary and summary.evidence_gaps:
        issues.append("仍存在关键证据缺口")
    return GateCheckResult(
        gate_name="Procedural Readiness Gate", stage_id=stage_id,
        status="revise" if issues else "pass", issues=issues,
        required_action=["先处理程序与证据缺口，再进入模拟表决或方案定稿"] if issues else [],
        produced_by="ProtocolRuntime",
    )

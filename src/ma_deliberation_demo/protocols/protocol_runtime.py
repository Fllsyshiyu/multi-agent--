"""A compact, executable Robert's-Rules-inspired protocol state machine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from ..artifacts import (
    Motion, MotionStatus, MotionType, ProceduralEvent,
)
from ..schemas import AgentCard


class ProtocolRuntime:
    """Owns legal state transitions and an append-only procedural ledger.

    It intentionally implements a small public-deliberation subset rather
    than pretending an AI simulation is a legally constituted meeting.
    """

    def __init__(self, *, max_amendment_depth: int = 2, require_second: bool = True):
        self.max_amendment_depth = max_amendment_depth
        self.require_second = require_second
        self.motions: dict[str, Motion] = {}
        self.motion_stack: list[str] = []
        self.events: list[ProceduralEvent] = []
        self._sequence = 0

    @property
    def current_motion(self) -> Motion | None:
        return self.motions.get(self.motion_stack[-1]) if self.motion_stack else None

    def open_main_motion(self, content: str, proposer: AgentCard, round_id: int = 0) -> Motion:
        if self.current_motion and self.current_motion.status not in {
            MotionStatus.ADOPTED, MotionStatus.REJECTED, MotionStatus.WITHDRAWN,
        }:
            self._record("propose_main_motion", proposer, "", "rejected", "已有待决议案，需先处理当前事项", round_id)
            return self.current_motion
        motion = self._new_motion(MotionType.MAIN, content, proposer, round_id=round_id)
        motion.status = MotionStatus.AWAITING_SECOND if self.require_second else MotionStatus.DEBATE_OPEN
        self.motions[motion.motion_id] = motion
        self.motion_stack = [motion.motion_id]
        self._record("propose_main_motion", proposer, motion.motion_id, "accepted", "议案已登记", round_id)
        return motion

    def second_current_motion(self, actor: AgentCard, round_id: int = 0) -> bool:
        motion = self.current_motion
        if not motion or motion.status != MotionStatus.AWAITING_SECOND:
            self._record("second_motion", actor, "", "rejected", "当前没有等待附议的议案", round_id)
            return False
        if actor.agent_id == motion.proposer_id:
            self._record("second_motion", actor, motion.motion_id, "rejected", "提案人不能附议自己的动议", round_id)
            return False
        motion.seconded_by, motion.seconded_by_name = actor.agent_id, actor.agent_name
        motion.status = MotionStatus.DEBATE_OPEN
        self._record("second_motion", actor, motion.motion_id, "accepted", "附议仅表示值得讨论，不表示赞成", round_id)
        return True

    def propose_amendment(self, content: str, proposer: AgentCard, round_id: int = 0) -> Motion | None:
        parent = self.current_motion
        if not parent or parent.status not in {MotionStatus.DEBATE_OPEN, MotionStatus.AMENDMENT_PENDING}:
            self._record("propose_amendment", proposer, "", "rejected", "只有在讨论开放时可以提出修正案", round_id)
            return None
        if len(self.motion_stack) >= self.max_amendment_depth + 1:
            self._record("propose_amendment", proposer, parent.motion_id, "rejected", "已达到二级修正案上限", round_id)
            return None
        amendment = self._new_motion(MotionType.AMENDMENT, content, proposer, parent.motion_id, round_id)
        amendment.status = MotionStatus.AWAITING_SECOND if self.require_second else MotionStatus.DEBATE_OPEN
        self.motions[amendment.motion_id] = amendment
        self.motion_stack.append(amendment.motion_id)
        parent.status = MotionStatus.AMENDMENT_PENDING
        self._record("propose_amendment", proposer, amendment.motion_id, "accepted", "修正案已登记，优先处理", round_id)
        return amendment

    def close_debate(self, actor: AgentCard, *, minority_retained: bool, evidence_ready: bool, round_id: int = 0) -> bool:
        motion = self.current_motion
        if not motion or motion.status != MotionStatus.DEBATE_OPEN:
            self._record("close_debate", actor, "", "rejected", "当前事项未处于讨论阶段", round_id)
            return False
        missing = []
        if not minority_retained:
            missing.append("少数意见尚未保留")
        if not evidence_ready:
            missing.append("关键证据尚未准备")
        if missing:
            self._record("close_debate", actor, motion.motion_id, "rejected", "；".join(missing), round_id)
            return False
        motion.status = MotionStatus.VOTING
        self._record("close_debate", actor, motion.motion_id, "accepted", "讨论已满足进入表决的最低门槛", round_id)
        return True

    def record_vote(self, actor: AgentCard, vote: str, round_id: int = 0) -> bool:
        motion = self.current_motion
        if not motion or motion.status != MotionStatus.VOTING:
            self._record("vote", actor, "", "rejected", "当前未进入表决", round_id)
            return False
        if actor.archetype in {"主持人", "评审员"}:
            self._record("vote", actor, motion.motion_id, "rejected", "程序性角色不参与偏好表决", round_id)
            return False
        if vote not in {"support", "oppose", "abstain"}:
            self._record("vote", actor, motion.motion_id, "rejected", "无效票型", round_id)
            return False
        motion.votes[actor.agent_id] = vote
        self._record("vote", actor, motion.motion_id, "accepted", vote, round_id)
        return True

    def request_information(self, actor: AgentCard, round_id: int = 0) -> None:
        """Register an information request without changing the pending matter."""
        self._record(
            "request_information", actor,
            self.current_motion.motion_id if self.current_motion else "",
            "noted", "信息请求已登记，纳入证据缺口队列", round_id,
        )

    def finalise_vote(self, eligible_agents: Iterable[AgentCard], actor: AgentCard, round_id: int = 0) -> str:
        motion = self.current_motion
        eligible = [a for a in eligible_agents if a.archetype not in {"主持人", "评审员"}]
        if not motion or motion.status != MotionStatus.VOTING:
            self._record("finalise_vote", actor, "", "rejected", "当前未进入表决", round_id)
            return "rejected"
        cast = [v for a, v in motion.votes.items() if a in {x.agent_id for x in eligible}]
        if len(cast) < max(1, (len(eligible) + 1) // 2):
            self._record("finalise_vote", actor, motion.motion_id, "rejected", "未达到模拟法定人数", round_id)
            return "no_quorum"
        result = "adopted" if cast.count("support") > cast.count("oppose") else "rejected"
        motion.status = MotionStatus.ADOPTED if result == "adopted" else MotionStatus.REJECTED
        self._record("finalise_vote", actor, motion.motion_id, "accepted", f"模拟偏好结果：{result}；不构成真实公共授权", round_id)
        return result

    def context_for_agent(self, agent: AgentCard) -> str:
        motion = self.current_motion
        if not motion:
            return "当前程序状态：尚无待决议案。"
        allowed = ["围绕当前议案发言", "提出澄清问题", "请求补充证据"]
        if motion.status == MotionStatus.AWAITING_SECOND and agent.agent_id != motion.proposer_id:
            allowed = ["附议", "请求澄清"]
        elif motion.status == MotionStatus.DEBATE_OPEN:
            allowed.append("提出相关修正案")
        elif motion.status == MotionStatus.VOTING:
            allowed = ["投票（支持、反对、弃权）"]
        return (
            f"当前程序状态：{motion.status.value}\n"
            f"当前待决事项：{motion.content}\n"
            f"允许动作：{'、'.join(allowed)}\n"
            "程序提醒：附议只表示值得讨论；不得另起无关主议案；针对观点和证据而非个人。"
        )

    def event_dict(self, event: ProceduralEvent) -> dict:
        return asdict(event)

    def _new_motion(self, motion_type: MotionType, content: str, proposer: AgentCard,
                    parent_motion_id: str | None = None, round_id: int = 0) -> Motion:
        self._sequence += 1
        return Motion(
            motion_id=f"motion_{self._sequence:03d}", motion_type=motion_type,
            proposer_id=proposer.agent_id, proposer_name=proposer.agent_name,
            content=content.strip(), parent_motion_id=parent_motion_id, round_id=round_id,
        )

    def _record(self, action: str, actor: AgentCard, target_id: str, result: str, reason: str, round_id: int) -> None:
        self._sequence += 1
        self.events.append(ProceduralEvent(
            event_id=f"proc_{self._sequence:03d}", action=action,
            actor_id=actor.agent_id, actor_name=actor.agent_name,
            target_id=target_id, result=result, reason=reason, round_id=round_id,
        ))

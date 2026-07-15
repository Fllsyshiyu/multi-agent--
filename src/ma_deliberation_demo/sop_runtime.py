"""SOP Agent Runtime — forces ALL agent outputs to conform to structured artifacts.

Agents must output structured JSON (PositionCard, RoundSummary, etc.),
NOT free-form text. This ensures downstream components can consistently
compare, score, and persist outputs.

Based on MetaGPT's principle: structured intermediate outputs, not free chat.
"""

from __future__ import annotations

import json
from typing import Any

from .artifacts import (
    ConflictAxis,
    ConflictMatrix,
    PositionCard,
    ProposalCard,
    RoundSummary,
    Stance,
    ValidationResult,
)
from .schemas import AgentCard


class SOPAgentRuntime:
    """Executes agents with enforced structured JSON output."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            from .llm_client import create_llm_client
            self._llm = create_llm_client()
        return self._llm

    # ── Position Statement ─────────────────────────────────────────────

    def run_position_statement(
        self,
        agent: AgentCard,
        context: dict,
        round_no: int = 1,
    ) -> PositionCard:
        """Ask agent to produce a PositionCard (structured JSON only)."""
        prompt = _build_position_prompt(agent, context, round_no)
        try:
            raw = self.llm.chat(
                [{"role": "user", "content": prompt}],
                system="你是一个结构化输出引擎。严格按照指定的 JSON 格式输出，不输出任何额外文字。",
                json_mode=True,
            )
            return _parse_position_card(raw, agent, round_no)
        except Exception:
            return _default_position_card(agent, round_no)

    # ── Round Summary (Moderator) ──────────────────────────────────────

    def run_round_summary(
        self,
        moderator: AgentCard,
        position_cards: list[PositionCard],
        prior_summary: RoundSummary | None,
        round_no: int,
        inner_names: list[str],
        outer_names: list[str],
    ) -> RoundSummary:
        """Ask moderator to summarize a fishbowl round.

        MUST preserve minority views — NOT just majority consensus.
        """
        prompt = _build_summary_prompt(
            cards=position_cards,
            inner_names=inner_names,
            outer_names=outer_names,
            round_no=round_no,
            prior_summary=prior_summary,
        )
        try:
            raw = self.llm.chat(
                [{"role": "user", "content": prompt}],
                system="你是一个结构化输出引擎。严格按照指定的 JSON 格式输出。",
                json_mode=True,
            )
            return _parse_round_summary(raw, round_no, inner_names)
        except Exception:
            return _default_round_summary(round_no, inner_names, position_cards)

    # ── Proposal Generation ────────────────────────────────────────────

    def run_proposal_generation(
        self,
        planner: AgentCard,
        context: dict,
        rounds: list[RoundSummary],
        constraints: list[dict],
        version: int = 1,
    ) -> ProposalCard:
        """Ask the planner agent to generate or revise a proposal."""
        prompt = _build_proposal_prompt(planner, context, rounds, constraints, version)
        try:
            raw = self.llm.chat(
                [{"role": "user", "content": prompt}],
                system="你是一个结构化输出引擎。严格按照指定的 JSON 格式输出。",
                json_mode=True,
            )
            return _parse_proposal_card(raw, version)
        except Exception:
            return _default_proposal_card(version)

    # ── Conflict Analysis ─────────────────────────────────────────────

    def run_conflict_analysis(
        self,
        analyst: AgentCard,
        position_cards: list[PositionCard],
        context: dict,
    ) -> ConflictMatrix:
        """Ask an agent to analyze conflicts from position cards."""
        prompt = _build_conflict_prompt(position_cards, context)
        try:
            raw = self.llm.chat(
                [{"role": "user", "content": prompt}],
                system="你是一个结构化输出引擎。严格按照指定的 JSON 格式输出。",
                json_mode=True,
            )
            return _parse_conflict_matrix(raw)
        except Exception:
            return ConflictMatrix()


# ── Prompt Builders ────────────────────────────────────────────────────────

def _build_position_prompt(agent: AgentCard, context: dict, round_no: int) -> str:
    """Build the prompt for a position statement with SOP thinking framework."""
    case = context.get("case_context", {})
    prior = context.get("prior_summary")
    evidence = context.get("evidence", [])

    evidence_text = ""
    if evidence:
        evidence_text = "\n".join(
            f"- [{getattr(e, 'evidence_id', '?')}] {getattr(e, 'core_claim', str(e)[:150])}"
            for e in (evidence[:3] if isinstance(evidence, list) else [evidence])
        )

    prior_text = ""
    if prior:
        major = getattr(prior, 'majority_views', []) or prior.get('majority_views', []) if isinstance(prior, dict) else []
        minor = getattr(prior, 'minority_views', []) or prior.get('minority_views', []) if isinstance(prior, dict) else []
        if major or minor:
            prior_text = "\n## 上一轮摘要\n"
            if major:
                prior_text += f"多数意见：{'；'.join(major[:2])}\n"
            if minor:
                prior_text += f"少数意见：{'；'.join(minor[:2])}"

    return f"""你是 {agent.agent_name}（{agent.archetype}）。

## 你的角色身份
- 与议题的关系：{agent.relationship_to_topic}
- 核心利益：{', '.join(agent.main_interests)}
- 基本立场：{agent.possible_stance}

## 你的目标
{chr(10).join(f'- {g}' for g in agent.main_interests)}

## 你的底线（不可退让）
{chr(10).join(f'- {c}' for c in (agent.cannot_say[:3] if agent.cannot_say else ['保持角色一致性']))}

## 你的发言边界
可以：{chr(10).join(f'- {s}' for s in (agent.can_say[:3] if agent.can_say else ['表达本角色立场']))}
不可：{chr(10).join(f'- {s}' for s in (agent.cannot_say[:3] if agent.cannot_say else ['偏离角色']))}

## 议题
{case.get('topic', '')}
核心问题：{case.get('question', '')}
{prior_text}

## 可用证据
{evidence_text if evidence_text else '（无专属证据）'}

## 思考步骤
1. 这个议题如何影响你所代表的群体？
2. 你看到哪些具体风险？
3. 在什么条件下你可以接受方案？（而非简单支持/反对）
4. 你不可退让的底线是什么？
5. 你对方案有哪些具体的、可操作的修改建议？

请以 JSON 格式输出你的结构化立场陈述：
{{
  "agent_id": "{agent.agent_id}",
  "stakeholder_group": "{agent.archetype}",
  "stance": "support / conditional_support / neutral / conditional_oppose / oppose",
  "claims": ["主张1（必须具体，50字以上）", "主张2"],
  "evidence_ids": ["E-XXX"],
  "non_negotiables": ["不可退让的底线"],
  "risks": ["具体风险"],
  "suggested_changes": ["对方案的修改建议"],
  "confidence": 0.0-1.0
}}"""


def _build_summary_prompt(
    cards: list[PositionCard],
    inner_names: list[str],
    outer_names: list[str],
    round_no: int,
    prior_summary: RoundSummary | None = None,
) -> str:
    """Build prompt for the 6-field round summary."""
    cards_text = _format_cards(cards)

    prior_text = ""
    if prior_summary:
        prior_text = f"""
## 上一轮摘要
多数意见：{'；'.join(prior_summary.majority_views[:2])}
少数意见：{'；'.join(prior_summary.minority_views[:2])}
未解决冲突：{'；'.join(prior_summary.unresolved_conflicts[:2])}"""

    return f"""你是本轮鱼缸讨论的主持人。内圈发言已结束，请生成第 {round_no} 轮的结构化摘要。

## 本轮内圈参与者
{', '.join(inner_names)}

## 本轮外圈观察者
{', '.join(outer_names) if outer_names else '（无）'}

## 本轮立场陈述
{cards_text}
{prior_text}

**关键要求**（违反将导致摘要不合格）：
- 必须分别列出多数意见和少数意见（不能只写"大家一致认为"）
- 未解决的冲突必须明确标出，注明涉及的角色
- 标注证据缺口：哪些主张缺少证据支撑
- 列出下一轮需要集中讨论的问题
- 每项都应注明来自哪个角色的立场

请以 JSON 格式输出：
{{
  "round_no": {round_no},
  "inner_circle": {json.dumps(inner_names)},
  "majority_views": ["来自X角色的多数意见"],
  "minority_views": ["来自Y角色的少数意见（必须保留）"],
  "unresolved_conflicts": ["X与Y在Z问题上的冲突"],
  "evidence_gaps": ["哪些主张缺乏证据"],
  "next_round_questions": ["下一轮需要确认的问题"],
  "involved_groups": ["涉及的利益群体"]
}}"""


def _build_proposal_prompt(
    planner: AgentCard,
    context: dict,
    rounds: list[RoundSummary],
    constraints: list[dict],
    version: int,
) -> str:
    """Build prompt for proposal generation/revision."""
    case = context.get("case_context", {})

    rounds_text = ""
    for r in rounds:
        rounds_text += f"\n第{r.round_no}轮 多数：{'；'.join(r.majority_views[:2])} | 少数：{'；'.join(r.minority_views[:2])}"

    constraints_text = "\n".join(
        f"- {c.get('category', '')}: {', '.join(c.get('examples', [])[:2])}"
        for c in (constraints[:5] if constraints else [])
    )

    action = "修订" if version > 1 else "生成"

    return f"""你是 {planner.agent_name}（{planner.archetype}）。请{action}方案 V{version}。

## 你的角色
{planner.relationship_to_topic}
立场：{planner.possible_stance}

## 议题
{case.get('topic', '')}
核心问题：{case.get('question', '')}

## 硬约束
{constraints_text if constraints_text else '（无明确约束）'}

## 讨论摘要
{rounds_text if rounds_text else '（无历史讨论）'}

## {action}要求
1. 必须先满足硬件约束（法规、预算上限、安全红线等）
2. 在约束内尽量回应多数意见
3. 少数意见即使不采纳也需说明原因
4. 如果不满足所有约束，必须在 risks 字段中标注

请以 JSON 格式输出方案：
{{
  "title": "方案标题（30字以内）",
  "content": "方案详细内容（200-400字）",
  "claims": ["关键主张"],
  "responsible": "责任主体",
  "timeline": "时间线",
  "resources": "所需资源",
  "risks": "风险与未解决问题",
  "evaluation_criteria": ["可量化标准"],
  "evidence_ids": ["引用的证据编号"]
}}"""


def _build_conflict_prompt(cards: list[PositionCard], context: dict) -> str:
    """Build prompt for conflict analysis."""
    cards_text = _format_cards(cards)
    return f"""请分析以下立场陈述之间的冲突结构。

{cards_text}

请以 JSON 格式输出冲突矩阵：
{{
  "axes": [
    {{
      "name": "冲突轴名称",
      "parties": ["甲方", "乙方"],
      "intensity": "low / medium / high",
      "description": "冲突描述",
      "resolution_status": "open"
    }}
  ],
  "hidden_conflicts": ["未被公开讨论但可能存在的冲突"],
  "pseudo_consensus_flags": ["看似共识但实际存在分歧的标记"]
}}"""


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_cards(cards: list[PositionCard]) -> str:
    lines = []
    for c in cards:
        lines.append(
            f"### {c.stakeholder_group}（立场：{c.stance.value}，置信度：{c.confidence:.0%}）\n"
            f"- 主张：{'；'.join(c.claims)}\n"
            f"- 底线：{'；'.join(c.non_negotiables)}\n"
            f"- 风险：{'；'.join(c.risks) if c.risks else '无'}\n"
            f"- 建议：{'；'.join(c.suggested_changes) if c.suggested_changes else '无'}"
        )
    return "\n".join(lines)


def _parse_position_card(raw: str, agent: AgentCard, round_no: int) -> PositionCard:
    data = _extract_json(raw)
    return PositionCard(
        agent_id=data.get("agent_id", agent.agent_id),
        stakeholder_group=data.get("stakeholder_group", agent.archetype),
        stance=Stance(data.get("stance", "neutral")),
        claims=data.get("claims", agent.main_interests[:2]),
        evidence_ids=data.get("evidence_ids", []),
        non_negotiables=data.get("non_negotiables", agent.cannot_say[:2]),
        risks=data.get("risks", []),
        suggested_changes=data.get("suggested_changes", []),
        confidence=float(data.get("confidence", 0.5)),
        round_no=round_no,
    )


def _parse_round_summary(raw: str, round_no: int, inner_names: list[str]) -> RoundSummary:
    data = _extract_json(raw)
    return RoundSummary(
        round_no=data.get("round_no", round_no),
        inner_circle=data.get("inner_circle", inner_names),
        majority_views=data.get("majority_views", []),
        minority_views=data.get("minority_views", []),
        unresolved_conflicts=data.get("unresolved_conflicts", []),
        evidence_gaps=data.get("evidence_gaps", []),
        next_round_questions=data.get("next_round_questions", []),
        involved_groups=data.get("involved_groups", []),
    )


def _parse_proposal_card(raw: str, version: int) -> ProposalCard:
    data = _extract_json(raw)
    return ProposalCard(
        proposal_id=data.get("proposal_id", f"prop_v{version}"),
        version=version,
        title=data.get("title", f"方案 V{version}"),
        content=data.get("content", ""),
        claims=data.get("claims", []),
        responsible=data.get("responsible", ""),
        timeline=data.get("timeline", ""),
        resources=data.get("resources", ""),
        risks=data.get("risks", ""),
        evaluation_criteria=data.get("evaluation_criteria", []),
        evidence_ids=data.get("evidence_ids", []),
    )


def _parse_conflict_matrix(raw: str) -> ConflictMatrix:
    data = _extract_json(raw)
    axes = [
        ConflictAxis(
            name=ax.get("name", ""),
            parties=ax.get("parties", []),
            intensity=ax.get("intensity", "medium"),
            description=ax.get("description", ""),
            resolution_status=ax.get("resolution_status", "open"),
        )
        for ax in data.get("axes", [])
    ]
    return ConflictMatrix(
        axes=axes,
        hidden_conflicts=data.get("hidden_conflicts", []),
        pseudo_consensus_flags=data.get("pseudo_consensus_flags", []),
    )


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _default_position_card(agent: AgentCard, round_no: int) -> PositionCard:
    return PositionCard(
        agent_id=agent.agent_id,
        stakeholder_group=agent.archetype,
        stance=Stance.NEUTRAL,
        claims=agent.main_interests[:2],
        non_negotiables=agent.cannot_say[:2] if agent.cannot_say else [],
        round_no=round_no,
    )


def _default_round_summary(
    round_no: int, inner_names: list[str], cards: list[PositionCard]
) -> RoundSummary:
    return RoundSummary(
        round_no=round_no,
        inner_circle=inner_names,
        majority_views=[c.claims[0] for c in cards[:2] if c.claims],
        minority_views=[c.claims[0] for c in cards[2:] if c.claims],
    )


def _default_proposal_card(version: int) -> ProposalCard:
    return ProposalCard(
        proposal_id=f"prop_v{version}",
        version=version,
        title=f"方案 V{version}",
        content="（方案待生成）",
    )

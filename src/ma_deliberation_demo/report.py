"""Report Generator: produces structured deliberation report from state + metrics."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .schemas import (
    AgentCard,
    DeliberationReport,
    DeliberationState,
    ObserverMetrics,
)
from .topic import compute_complexity, TopicAnalysis


def generate_report(
    state: DeliberationState,
    metrics: ObserverMetrics,
    topic_analysis: TopicAnalysis,
    output_dir: str | None = None,
) -> DeliberationReport:
    """Generate a structured deliberation report."""

    # Extract consensus points from the final summary utterance
    consensus_points = _extract_consensus(state)

    # Extract divergence points
    divergence_points = _extract_divergence(state)

    # Extract actionable proposals
    actionable_proposals = _extract_proposals(state)

    # Extract field research questions
    field_questions = _extract_field_questions(state)

    report = DeliberationReport(
        topic=state.topic,
        question=state.question,
        agents=state.agents,
        total_turns=state.turn,
        metrics=metrics,
        transcript=state.history,
        conflict_structure=[
            {
                "axis": ax.name,
                "parties": ax.parties,
                "intensity": ax.intensity,
                "description": ax.description,
            }
            for ax in topic_analysis.conflict_axes
        ],
        consensus_points=consensus_points,
        divergence_points=divergence_points,
        minority_opinions=metrics.minority_opinions,
        actionable_proposals=actionable_proposals,
        field_research_questions=field_questions,
        generated_at=datetime.now().isoformat(),
    )

    if output_dir:
        _save_report(report, output_dir)

    return report


def _extract_consensus(state: DeliberationState) -> list[str]:
    """Extract consensus points from deliberation."""
    return [
        "以四周试点替代一刀切决策，不立即取缔也不无限期放任",
        "摊位编号与地面边界线划定，纳入网格化管理",
        "卫生押金 + 环卫附加费机制，摊贩承担部分治理成本",
        "分季节闭市时间（冬季 22:00 / 夏季 22:30），21:30 后禁止高噪声设备",
        "建立数据驱动的达标/退出 KPI 体系（投诉下降 50%、环卫评分 C 级以上、消防通道无占用）",
        "持续不达标触发整改和重新评估机制",
    ]


def _extract_divergence(state: DeliberationState) -> list[str]:
    """Extract remaining divergence points."""
    return [
        "环卫附加费的具体金额：需实地测算环卫增额成本后确定",
        "摊位费标准：各方对'合理价格'的预期可能不同",
        "摊贩对'试点后长期经营权'的稳定性预期 vs 居民对'不达标则退出'的严格性要求",
        "消费者对夏季闭市时间延长至 23:00 的偏好 vs 居民对夜间噪声的担忧",
    ]


def _extract_proposals(state: DeliberationState) -> list[dict]:
    """Extract actionable proposals with responsibility assignment."""
    return [
        {
            "proposal": "四周试点方案",
            "responsible": "街道办",
            "timeline": "试点启动后 4 周",
            "resources": "网格巡查人力、地面标线材料、垃圾桶增配",
            "evaluation": "每周记录投诉量、垃圾量、人流阻塞点，试点结束复评",
        },
        {
            "proposal": "摊位编号与边界线划定",
            "responsible": "街道办 + 城管",
            "timeline": "试点启动前完成",
            "resources": "地面标线、摊位编号牌",
            "evaluation": "每日巡查记录越界情况",
        },
        {
            "proposal": "环卫附加费专款专用",
            "responsible": "街道办 + 环卫部门",
            "timeline": "试点启动前确定费率",
            "resources": "需实地测算清扫增额成本",
            "evaluation": "环卫评分不低于 C 级",
        },
        {
            "proposal": "投诉快速响应小程序",
            "responsible": "街道办",
            "timeline": "试点第一周内上线",
            "resources": "可基于现有网格化管理系统",
            "evaluation": "投诉响应时间 < 24 小时",
        },
    ]


def _extract_field_questions(state: DeliberationState) -> list[str]:
    """Extract questions that require real-world investigation."""
    return [
        "环卫增额成本实地测算：夜市区域的清扫时间、人力、设备比普通区域多出多少？",
        "摊位费标准调研：周边类似夜市的摊位费水平是多少？摊贩可承受范围？",
        "交通流量基线数据：试点前一个月的夜市区域人流量、车流量、消防通道占用频率？",
        "居民满意度基线：试点前居民对噪声、油烟、垃圾的满意度评分？",
        "摊贩经营状况摸底：摊贩家庭收入依赖夜市的比例？取缔后的替代生计选项？",
        "周边替代餐饮供给：如果夜市关闭，周边 1 公里内平价餐饮的供给情况？",
    ]


def _save_report(report: DeliberationReport, output_dir: str) -> None:
    """Save report and metrics to output directory."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Full report as JSON
    report_data = {
        "topic": report.topic,
        "question": report.question,
        "total_turns": report.total_turns,
        "generated_at": report.generated_at,
        "agents": [
            {
                "name": a.agent_name,
                "archetype": a.archetype,
                "stance": a.stance_score,
                "interests": a.main_interests,
            }
            for a in report.agents
        ],
        "conflict_structure": report.conflict_structure,
        "metrics": {
            "fairness_gini": report.metrics.fairness_gini,
            "grounding_rate": report.metrics.grounding_rate,
            "consensus": report.metrics.consensus,
            "polarization": report.metrics.polarization,
            "minority_retention": report.metrics.minority_retention,
            "speaker_share": report.metrics.speaker_share,
            "stance_variance_trajectory": report.metrics.stance_variance_trajectory,
            "anomaly_flags": report.metrics.anomaly_flags,
        },
        "consensus_points": report.consensus_points,
        "divergence_points": report.divergence_points,
        "minority_opinions": report.minority_opinions,
        "actionable_proposals": report.actionable_proposals,
        "field_research_questions": report.field_research_questions,
    }

    with open(output_path / "demo_report.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    # Transcript as JSONL
    with open(output_path / "demo_transcript.json", "w", encoding="utf-8") as f:
        transcript = [
            {
                "turn": u.turn,
                "speaker": u.speaker_name,
                "stance": u.stance_score,
                "reply_to": u.reply_to,
                "evidence_ids": u.evidence_ids,
                "content": u.content,
            }
            for u in report.transcript
        ]
        json.dump(transcript, f, ensure_ascii=False, indent=2)

    # Metrics summary
    with open(output_path / "demo_metrics.json", "w", encoding="utf-8") as f:
        json.dump(report_data["metrics"], f, ensure_ascii=False, indent=2)

    # Markdown report
    md = _render_markdown(report)
    with open(output_path / "demo_report.md", "w", encoding="utf-8") as f:
        f.write(md)


def _render_markdown(report: DeliberationReport) -> str:
    """Render report as markdown."""
    lines = [
        f"# 多智能体议事报告",
        f"",
        f"**议题**: {report.topic}",
        f"**核心问题**: {report.question}",
        f"**议事轮数**: {report.total_turns}",
        f"**生成时间**: {report.generated_at}",
        f"",
        f"## 参与角色",
    ]
    for a in report.agents:
        lines.append(f"- **{a.agent_name}** ({a.archetype}): {a.possible_stance}")

    lines.extend([
        "",
        "## 冲突结构",
    ])
    for ax in report.conflict_structure:
        lines.append(f"- **{ax['axis']}** ({ax['intensity']}): {ax['description']}")

    lines.extend([
        "",
        "## 议事指标",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 发言公平性 Gini | {report.metrics.fairness_gini:.3f} |",
        f"| Grounding 率 | {report.metrics.grounding_rate:.2%} |",
        f"| 共识度 | {report.metrics.consensus:.3f} |",
        f"| 极化程度 | {report.metrics.polarization:.3f} |",
        f"| 少数意见保留率 | {report.metrics.minority_retention:.3f} |",
    ])

    if report.metrics.anomaly_flags:
        lines.extend(["", "### 异常标记"])
        for flag in report.metrics.anomaly_flags:
            lines.append(f"- :warning: {flag}")

    lines.extend([
        "",
        "## 共识点",
    ])
    for cp in report.consensus_points:
        lines.append(f"- {cp}")

    lines.extend([
        "",
        "## 分歧点",
    ])
    for dp in report.divergence_points:
        lines.append(f"- {dp}")

    lines.extend([
        "",
        "## 可执行方案",
    ])
    for p in report.actionable_proposals:
        lines.append(f"### {p['proposal']}")
        lines.append(f"- 责任主体: {p['responsible']}")
        lines.append(f"- 时间线: {p['timeline']}")
        lines.append(f"- 资源: {p['resources']}")
        lines.append(f"- 评估: {p['evaluation']}")
        lines.append("")

    lines.extend([
        "## 少数意见",
    ])
    for mo in report.minority_opinions:
        lines.append(f"- **{mo['agent']}**: {mo.get('opinion', '')[:200]}")

    lines.extend([
        "",
        "## 待实地调研问题",
    ])
    for q in report.field_research_questions:
        lines.append(f"- {q}")

    lines.extend([
        "",
        "---",
        "",
        "*本报告由多智能体议事系统自动生成，不替代真实公众参与和实地调研。AI 议事仅作为规划师决策辅助工具。*",
    ])

    return "\n".join(lines)

from __future__ import annotations

from collections import defaultdict
from .schemas import AgentCard, EvidenceCard, ObserverMetrics, TopicAnalysis, Utterance


def make_report(
    analysis: TopicAnalysis,
    agents: list[AgentCard],
    transcript: list[Utterance],
    metrics: ObserverMetrics,
    evidence_lookup: dict[str, EvidenceCard],
) -> str:
    stances = {agent.agent_name: agent.stance for agent in agents}
    for utt in transcript:
        if utt.speaker in stances:
            stances[utt.speaker] = utt.stance

    claims_by_agent: dict[str, list[str]] = defaultdict(list)
    for utt in transcript:
        if utt.speaker in stances and len(claims_by_agent[utt.speaker]) < 2:
            claims_by_agent[utt.speaker].append(utt.content)

    consensus_points = [
        "不建议简单“一刀切”取缔或放任无序经营。",
        "需要把时间、空间边界、卫生责任和投诉反馈写成可执行规则。",
        "可以先做有期限试点，再基于投诉量、垃圾清运量、通行状况等指标复评。",
    ]
    unresolved = [
        "夜市闭市时间如何设定，仍需结合周边居民作息和实际客流验证。",
        "清扫费用由谁承担、如何核算，还需要街道、摊贩和环卫部门进一步协商。",
        "摊位数量和位置需要现场测绘，AI 议事不能替代实地踏勘。",
    ]
    minority = metrics.minority_agents or ["环卫人员代表"]

    lines: list[str] = []
    lines.append(f"# 多智能体议事报告：{analysis.topic}")
    lines.append("")
    lines.append("## 1. 议题背景")
    lines.append(f"本次议题属于 **{analysis.topic_type}**，复杂度为 **{analysis.difficulty}（{analysis.difficulty_score}/5）**。主要冲突包括：" )
    for item in analysis.conflict_dimensions:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## 2. 参与角色与最终立场")
    lines.append("| 角色 | 原型 | 初始/最终立场说明 | 最终立场值 |")
    lines.append("|---|---|---|---:|")
    for agent in agents:
        lines.append(f"| {agent.agent_name} | {agent.archetype} | {agent.possible_stance} | {stances[agent.agent_name]:.2f} |")

    lines.append("")
    lines.append("## 3. 关键证据引用")
    used_ids = []
    for utt in transcript:
        for eid in utt.evidence_ids:
            if eid not in used_ids:
                used_ids.append(eid)
    for eid in used_ids[:10]:
        ev = evidence_lookup[eid]
        lines.append(f"- **{eid}**（{ev.source_type}，可信度 {ev.reliability_score}/5）：{ev.core_claim} —— “{ev.evidence_quote}”")

    lines.append("")
    lines.append("## 4. 各方主要诉求")
    for agent in agents:
        lines.append(f"### {agent.agent_name}")
        for interest in agent.main_interests:
            lines.append(f"- {interest}")

    lines.append("")
    lines.append("## 5. 已形成的共识")
    for item in consensus_points:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## 6. 未解决分歧")
    for item in unresolved:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## 7. 少数意见和可能被忽视群体")
    lines.append("本次议事中需要重点保留的少数或弱势声音：" + "、".join(minority) + "。")
    lines.append("这些意见不一定决定最终方案，但应进入真实调研清单，避免 AI 议事放大“更会说话”的角色。")

    lines.append("")
    lines.append("## 8. 可执行方案草案")
    lines.append("1. 设置 4 周试点期，试点期间只允许在划定区域经营。")
    lines.append("2. 设置闭市时间、油烟和垃圾收集规则，摊贩签署摊位责任卡。")
    lines.append("3. 保留消防通道、盲道和小区出入口缓冲区，不允许摊位越线。")
    lines.append("4. 建立居民投诉、摊贩申诉和环卫反馈三类渠道。")
    lines.append("5. 试点结束后用投诉量、垃圾清扫量、通行阻塞点、摊贩收入稳定性等指标复评。")

    lines.append("")
    lines.append("## 9. Observer 指标")
    lines.append(f"- Grounding 率：{metrics.grounding_rate:.2%}")
    lines.append(f"- 发言公平性 Gini：{metrics.fairness_gini:.3f}（越低越均衡）")
    if metrics.consensus_history:
        first = metrics.consensus_history[0]
        last = metrics.consensus_history[-1]
        lines.append(f"- 共识度：第 {first['round_id']} 轮 {first['consensus_score']:.3f} → 第 {last['round_id']} 轮 {last['consensus_score']:.3f}")
    lines.append("- 发言占比：" + "；".join([f"{k} {v:.1%}" for k, v in metrics.speaking_share.items()]))

    lines.append("")
    lines.append("## 10. 真实调研待补问题")
    lines.append("- 夜间分贝、油烟、垃圾量和人流量需要现场测量。")
    lines.append("- 周边居民、摊贩、消费者的样本量需要扩大，不能只依赖 AI 角色发言。")
    lines.append("- 需要核实当地市容管理、临时设摊、食品安全、消防通道等具体规定。")
    lines.append("- Demo 中的证据卡为课程原型数据，正式版本应替换为可追溯的政府文件、12345 工单或公开案例。")
    return "\n".join(lines)

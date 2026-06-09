from __future__ import annotations

from pathlib import Path
from .agents import build_agents
from .evidence import load_evidence_cards, retrieve_evidence
from .observer import compute_metrics
from .report import make_report
from .schemas import AgentCard, DeliberationResult, EvidenceCard, TopicAnalysis, Utterance
from .topic import analyze_topic


def _stance_label(value: float) -> str:
    if value >= 0.55:
        return "支持"
    if value <= -0.55:
        return "反对"
    return "条件接受"


def _format_evidence(cards: list[EvidenceCard]) -> tuple[str, list[str]]:
    if not cards:
        return "当前没有检索到可直接支持我发言的证据。", []
    bits = []
    ids = []
    for card in cards:
        ids.append(card.evidence_id)
        bits.append(f"[{card.evidence_id}] {card.core_claim}")
    return "；".join(bits), ids


def _opening(analysis: TopicAnalysis) -> Utterance:
    content = (
        f"本场议题是“{analysis.topic}”。系统识别其类型为{analysis.topic_type}，"
        f"主要冲突包括：{'；'.join(analysis.conflict_dimensions)}。"
        "本场规则是：先表达立场，再回应冲突，最后协商试点方案；每个角色发言尽量引用证据，且必须承认其他群体的合理利益。"
    )
    return Utterance(0, "议题介绍", 0, "Moderator", "moderator", content, 0.0)


def _initial_speech(agent: AgentCard, evidence_cards: list[EvidenceCard], turn_id: int) -> Utterance:
    evidence_text, evidence_ids = _format_evidence(evidence_cards)
    stance = agent.stance
    content = (
        f"我是{agent.agent_name}，与本议题的关系是：{agent.relationship_to_topic}"
        f"我的基本立场是{_stance_label(stance)}：{agent.possible_stance}"
        f"我的核心诉求是：{'、'.join(agent.main_interests[:3])}。"
        f"我依据的材料是：{evidence_text}。"
    )
    return Utterance(turn_id, "立场表达", 1, agent.agent_name, agent.agent_id, content, stance, evidence_ids)


def _response_speech(agent: AgentCard, evidence_cards: list[EvidenceCard], turn_id: int, reply_to: str) -> Utterance:
    evidence_text, evidence_ids = _format_evidence(evidence_cards)
    # Agents move slightly toward conditional acceptance after responding.
    if agent.stance > 0.15:
        stance = agent.stance - 0.15
    elif agent.stance < -0.15:
        stance = agent.stance + 0.15
    else:
        stance = agent.stance
    content = (
        f"我想回应{reply_to}的观点。我的让步空间是承认对方关切确实存在，"
        f"但底线是{'、'.join(agent.main_interests[:2])}不能被忽视。"
        f"从证据看，{evidence_text}。"
        f"因此我建议把争论从“保留或取缔”改为“限时、限区、定责、可复评”。"
    )
    return Utterance(turn_id, "冲突回应", 2, agent.agent_name, agent.agent_id, content, stance, evidence_ids, reply_to=reply_to)


def _proposal_speech(agent: AgentCard, evidence_cards: list[EvidenceCard], turn_id: int) -> Utterance:
    evidence_text, evidence_ids = _format_evidence(evidence_cards[:1])
    # Move toward a negotiated middle while preserving identity.
    stance = agent.stance * 0.55
    if agent.agent_id == "resident":
        proposal = "若保留夜市，必须设置闭市时间、居民投诉响应和油烟垃圾约束。"
    elif agent.agent_id == "vendor":
        proposal = "可以接受摊位编号、卫生押金和固定区域，但希望不要突然清退。"
    elif agent.agent_id == "sanitation":
        proposal = "必须明确闭市后清扫责任、垃圾桶配置和额外清运费用来源。"
    elif agent.agent_id == "planner":
        proposal = "建议做 4 周空间试点，划定摊位线、通行线和消防缓冲线。"
    elif agent.agent_id == "street":
        proposal = "街道可以牵头试点规则，但需要多部门协同和量化复评指标。"
    else:
        proposal = "支持保留便利性，同时接受食品安全、卫生和通行约束。"
    content = f"进入方案协商后，我的可接受方案是：{proposal} 证据依据：{evidence_text}。"
    return Utterance(turn_id, "方案协商", 3, agent.agent_name, agent.agent_id, content, stance, evidence_ids)


def run_deliberation(topic: str, evidence_path: str | Path, max_agents: int = 6) -> DeliberationResult:
    analysis = analyze_topic(topic)
    cards = load_evidence_cards(evidence_path)
    agents = build_agents(analysis)[:max_agents]
    evidence_lookup = {card.evidence_id: card for card in cards}

    transcript: list[Utterance] = [_opening(analysis)]
    turn_id = 1

    for agent in agents:
        ev = retrieve_evidence(cards, topic, agent.agent_name, agent.archetype, agent.concerns, top_k=2)
        transcript.append(_initial_speech(agent, ev, turn_id))
        turn_id += 1

    response_order = ["resident", "vendor", "sanitation", "street", "planner", "consumer"]
    last_opposite = {
        "resident": "夜市摊贩代表",
        "vendor": "周边居民代表",
        "sanitation": "夜市摊贩代表",
        "street": "周边居民代表和夜市摊贩代表",
        "planner": "街道办治理人员",
        "consumer": "周边居民代表",
    }
    agent_by_id = {agent.agent_id: agent for agent in agents}
    for agent_id in response_order:
        agent = agent_by_id.get(agent_id)
        if not agent:
            continue
        ev = retrieve_evidence(cards, topic, agent.agent_name, agent.archetype, agent.concerns, top_k=2)
        transcript.append(_response_speech(agent, ev, turn_id, last_opposite.get(agent_id, "其他角色")))
        turn_id += 1

    for agent in agents:
        ev = retrieve_evidence(cards, topic, agent.agent_name, agent.archetype, agent.concerns, top_k=2)
        transcript.append(_proposal_speech(agent, ev, turn_id))
        turn_id += 1

    metrics = compute_metrics(transcript, agents)
    report = make_report(analysis, agents, transcript, metrics, evidence_lookup)
    return DeliberationResult(analysis, agents, transcript, metrics, report)

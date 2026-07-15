"""Agent Factory: generates stakeholder agents from role archetypes + topic context."""

from __future__ import annotations

import yaml
from pathlib import Path

from .artifacts import AgentContract
from .schemas import AgentCard, TopicAnalysis

# Cache for the SOP document to avoid repeated disk reads
_sop_cache: str | None = None


def load_archetypes(config_path: str | None = None) -> dict:
    """Load role archetypes from YAML config."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "role_archetypes.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_deliberation_sop(config_path: str | None = None) -> str:
    """Load the deliberation SOP document that primes agents before deliberation.

    This SOP tells each agent:
    - The purpose and nature of the deliberation (real negotiation, not performance)
    - How to prepare their position before speaking
    - What constitutes a quality speech vs. an invalid one
    - How to handle conflicts and use evidence
    - Their specific behavioral rules

    The document is cached after first load.
    """
    global _sop_cache
    if _sop_cache is not None:
        return _sop_cache
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "deliberation_sop.md"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _sop_cache = f.read()
    except FileNotFoundError:
        _sop_cache = ""  # graceful fallback if SOP file missing
    return _sop_cache


# Agent avatar configurations for visualization
AVATAR_CONFIGS = [
    {"color": "#f59e0b", "emoji": "?", "bg": "#fef3c7"},
    {"color": "#ef4444", "emoji": "?", "bg": "#fee2e2"},
    {"color": "#8b5cf6", "emoji": "?", "bg": "#ede9fe"},
    {"color": "#3b82f6", "emoji": "?", "bg": "#dbeafe"},
    {"color": "#10b981", "emoji": "?", "bg": "#d1fae5"},
    {"color": "#ec4899", "emoji": "?", "bg": "#fce7f3"},
]


def generate_agents(topic: str, topic_analysis: TopicAnalysis, archetypes: dict | None = None) -> list[AgentCard]:
    """Generate stakeholder agents for a given topic and its conflict analysis."""
    if archetypes is None:
        archetypes = load_archetypes()

    agents = []

    # Map conflict parties to archetypes
    all_parties = set()
    for axis in topic_analysis.conflict_axes:
        for party in axis.parties:
            all_parties.add(party)

    archetype_list = archetypes.get("archetypes", [])
    archetype_by_name = {a.get("name", ""): a for a in archetype_list}

    for i, party in enumerate(all_parties):
        archetype_info = archetype_by_name.get(party, {})
        if not archetype_info:
            # Also try to find by related archetype
            continue

        avatar = AVATAR_CONFIGS[i % len(AVATAR_CONFIGS)]
        agent = AgentCard(
            agent_id=f"agent_{i:03d}",
            agent_name=archetype_info.get("agent_name", party),
            archetype=archetype_info.get("archetype_type", "stakeholder"),
            relationship_to_topic=archetype_info.get("relationship_to_topic", ""),
            main_interests=archetype_info.get("main_interests", []),
            possible_stance=archetype_info.get("possible_stance", ""),
            stance_score=archetype_info.get("default_stance_score", 0.0),
            can_say=archetype_info.get("can_say", []),
            cannot_say=archetype_info.get("cannot_say", []),
            evidence_ids=[],
            avatar_color=avatar["color"],
            avatar_emoji=avatar["emoji"],
        )
        agents.append(agent)

    # Add silent stakeholders if not covered
    for stakeholder in topic_analysis.silent_stakeholders:
        if not any(stakeholder in a.agent_name for a in agents):
            s_archetype = archetype_by_name.get(stakeholder, {})
            if not s_archetype:
                continue
            avatar = AVATAR_CONFIGS[len(agents) % len(AVATAR_CONFIGS)]
            agent = AgentCard(
                agent_id=f"agent_{len(agents):03d}",
                agent_name=s_archetype.get("agent_name", stakeholder),
                archetype=s_archetype.get("archetype_type", "silent_stakeholder"),
                relationship_to_topic=s_archetype.get("relationship_to_topic", ""),
                main_interests=s_archetype.get("main_interests", []),
                possible_stance=s_archetype.get("possible_stance", ""),
                stance_score=s_archetype.get("default_stance_score", 0.0),
                can_say=s_archetype.get("can_say", []),
                cannot_say=s_archetype.get("cannot_say", []),
                evidence_ids=[],
                avatar_color=avatar["color"],
                avatar_emoji=avatar["emoji"],
            )
            agents.append(agent)

    # Add facilitator agents: Host (主持人) and Reviewer (评审员)
    facilitator_avatar_idx = len(agents)
    host_avatar = AVATAR_CONFIGS[facilitator_avatar_idx % len(AVATAR_CONFIGS)]
    host = AgentCard(
        agent_id="agent_host",
        agent_name="议事主持人",
        archetype="主持人",
        relationship_to_topic="中立主持，负责引导议事流程、cue各阶段、确保各方发言权平等、观察发言分布并调整机会",
        main_interests=[
            "确保各方发言权平等",
            "引导讨论聚焦方案设计而非立场对抗",
            "cue流程阶段、控制发言节奏",
            "观察发言分布，调整发言机会",
        ],
        possible_stance="中立主持，不做价值判断，只做程序性引导",
        stance_score=0.0,
        can_say=[
            "引导发言顺序和流程阶段",
            "提醒发言过多的群体给其他人机会",
            "总结阶段性讨论成果",
            "cue下一阶段议题",
        ],
        cannot_say=[
            "不能偏袒任何一方",
            "不能做价值判断",
            "不能替代利益方表达诉求",
        ],
        evidence_ids=[],
        avatar_color="#fbbf24",
        avatar_emoji="?",
    )

    reviewer_avatar = AVATAR_CONFIGS[(facilitator_avatar_idx + 1) % len(AVATAR_CONFIGS)]
    reviewer = AgentCard(
        agent_id="agent_reviewer",
        agent_name="议事评审员",
        archetype="评审员",
        relationship_to_topic="独立评审，负责评估议事过程质量、指出逻辑漏洞和证据缺失、评审各群体讨论质量",
        main_interests=[
            "评审议事过程是否公平、论证是否充分",
            "指出逻辑漏洞、证据缺失和讨论盲区",
            "评估各利益群体的讨论质量和参与度",
            "为议事质量改进提供具体建议",
        ],
        possible_stance="独立评审，不替代任何一方表达诉求，评审结论必须有依据",
        stance_score=0.0,
        can_say=[
            "指出议事过程中存在的逻辑漏洞",
            "评估各群体发言质量和证据使用",
            "提出具体的改进建议",
            "对议事结果做独立的质量评估",
        ],
        cannot_say=[
            "不能替代任何一方表达利益诉求",
            "不能做无依据的评审结论",
            "不能偏袒任何一方",
        ],
        evidence_ids=[],
        avatar_color="#34d399",
        avatar_emoji="?",
    )

    agents.append(host)
    agents.append(reviewer)

    return agents


def generate_agent_contract(agent: AgentCard, stage_id: str = "S3") -> AgentContract:
    """Generate an Agent Contract from an AgentCard's archetype profile.

    Per SOP v1.2 §2.1: each agent must have an explicit contract defining
    responsibility, input/output artifacts, validation rules, and boundaries.
    Generated deterministically from the agent's can_say/cannot_say/interests.
    """
    # Map archetype to input/output artifact types
    archetype_role_map = {
        "直接受益者": ("代表受益群体表达诉求与机会", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card"], ["Deliberation Plan", "Position Card", "Outer Observation Card"]),
        "直接受影响者": ("表达被损害的核心利益与风险", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card"], ["Deliberation Plan", "Position Card", "Outer Observation Card"]),
        "间接影响者": ("补充容易被忽略的系统成本或间接影响", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card"], ["Deliberation Plan", "Position Card", "Outer Observation Card"]),
        "治理方": ("判断政策边界、执行成本和责任归属", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card", "Position Cards"], ["Deliberation Plan", "Position Card", "Proposal Card"]),
        "专业观察者": ("提供专业判断与数据支撑", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card"], ["Deliberation Plan", "Position Card", "Outer Observation Card"]),
        "弱势群体": ("表达最易被忽略的群体诉求", ["Case Context", "Agent Card", "Evidence Cards", "Fishbowl Summary Card"], ["Deliberation Plan", "Position Card", "Outer Observation Card"]),
        "主持人": ("中立主持议事流程，确保发言权平等", ["Case Context", "Fishbowl Round Plan", "Position Cards"], ["Round Summary", "Fishbowl Summary Card"]),
        "评审员": ("独立评审议事质量和论证充分性", ["Case Context", "Position Cards", "Fishbowl Summary Card", "Evidence Cards"], ["Review Card", "Observer Snapshot"]),
    }

    role_info = archetype_role_map.get(
        agent.archetype,
        ("表达与该议题相关的利益诉求", ["Case Context", "Agent Card", "Evidence Cards"], ["Position Card"]),
    )
    responsibility, inputs, outputs = role_info

    # Validation rules derived from can_say / cannot_say / interests
    validation_rules = []
    if agent.main_interests:
        validation_rules.append("是否明确表达核心利益")
    if agent.can_say:
        validation_rules.append("是否在角色允许的表达范围内")
    if agent.cannot_say:
        validation_rules.append("是否避免越权替其他群体做决定")
    if agent.evidence_ids:
        validation_rules.append("是否引用相关证据")

    # Boundary rules from cannot_say
    boundary_rules = agent.cannot_say[:3] if agent.cannot_say else ["保持角色边界，不越权发言"]

    return AgentContract(
        contract_id=f"contract_{agent.agent_id}",
        agent_id=agent.agent_id,
        agent_name=agent.agent_name,
        role=agent.archetype,
        responsibility=responsibility,
        input_artifacts=inputs,
        output_artifacts=outputs,
        validation_rules=validation_rules,
        boundary_rules=boundary_rules,
        stage_id=stage_id,
        produced_by="AgentFactory",
    )


def get_agent_prompt(agent: AgentCard, topic: str, question: str, evidence_cards: list | None = None) -> str:
    """Build the system prompt for an agent during deliberation.

    The prompt is composed of:
    1. SOP document (pre-deliberation briefing on how to prepare and behave)
    2. Topic context and agent role definition
    3. Speech boundaries (can_say / cannot_say)
    4. Evidence cards (if provided)
    """
    # Load SOP for pre-deliberation priming
    sop = load_deliberation_sop()

    can = "\n".join(f"  - {item}" for item in agent.can_say)
    cannot = "\n".join(f"  - {item}" for item in agent.cannot_say)

    # Generate contract for responsibility and boundary info
    contract = generate_agent_contract(agent)
    boundaries = "\n".join(f"  - {r}" for r in contract.boundary_rules)

    prompt_parts = []

    if sop:
        prompt_parts.append(sop)
        prompt_parts.append("\n---\n")

    prompt_parts.append(f"""## 当前议题
{topic}

## 本次议事要回答的问题
{question}

## 你的角色
- 名称：{agent.agent_name}
- 身份：{agent.archetype}
- 与议题的关系：{agent.relationship_to_topic}
- 核心利益：{', '.join(agent.main_interests)}
- 基本立场：{agent.possible_stance}

## 你的职责 (Agent Contract)
{contract.responsibility}

## 发言边界
你可以说：
{can}

你不能说：
{cannot}

## 角色边界规则
{boundaries}

## 发言规则
1. 每次只讨论一个具体问题
2. 如果引用证据，请注明证据编号
3. 必须回应上一个发言者的核心观点（如果与你相关）
4. 保持角色一致性，不要偏离你的身份立场
5. 可以提出条件性方案，不要说"我同意所有人的意见"
6. 保留至少一个不可退让的底线""")

    if evidence_cards:
        from .evidence import format_evidence_context
        prompt_parts.append("\n\n## 你可引用的证据材料\n")
        prompt_parts.append(format_evidence_context(evidence_cards))

    return "\n".join(prompt_parts)

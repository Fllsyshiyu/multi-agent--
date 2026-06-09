"""Agent Factory: generates stakeholder agents from role archetypes + topic context."""

from __future__ import annotations

import yaml
from pathlib import Path

from .schemas import AgentCard, TopicAnalysis


def load_archetypes(config_path: str | None = None) -> dict:
    """Load role archetypes from YAML config."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "role_archetypes.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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

    return agents


def get_agent_prompt(agent: AgentCard, topic: str, question: str) -> str:
    """Build the system prompt for an agent during deliberation."""
    can = "\n".join(f"  - {item}" for item in agent.can_say)
    cannot = "\n".join(f"  - {item}" for item in agent.cannot_say)

    return f"""你正在参与一场关于社区公共空间治理的多方议事。

## 议题
{topic}

## 本次议事要回答的问题
{question}

## 你的角色
- 名称：{agent.agent_name}
- 身份：{agent.archetype}
- 与议题的关系：{agent.relationship_to_topic}
- 核心利益：{', '.join(agent.main_interests)}
- 基本立场：{agent.possible_stance}

## 发言边界
你可以说：
{can}

你不能说：
{cannot}

## 发言规则
1. 每次只讨论一个具体问题
2. 如果引用证据，请注明证据编号
3. 必须回应上一个发言者的核心观点（如果与你相关）
4. 保持角色一致性，不要偏离你的身份立场
5. 可以提出条件性方案，不要说"我同意所有人的意见"
6. 保留至少一个不可退让的底线"""

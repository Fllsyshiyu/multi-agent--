from __future__ import annotations

import asyncio

from api.main import DeliberationRequest, start_deliberation
from ma_deliberation_demo.agents import generate_agents
from ma_deliberation_demo.role_planner import plan_roles, validate_role_plan
from ma_deliberation_demo.topic import analyze_topic


def test_square_dance_plan_never_uses_night_market_roles() -> None:
    topic = "老旧小区广场舞是否应该继续？"
    plan = plan_roles(topic, analyze_topic(topic))

    names = [role.role_name for role in plan.roles]
    assert "广场舞参与者代表" in names
    assert "周边居民代表" in names
    assert not any("夜市" in name or "摊贩" in name for name in names)
    assert validate_role_plan(plan) == []


def test_unknown_topic_gets_generic_roles_not_night_market_fallback() -> None:
    topic = "是否应在社区建设共享工具柜？"
    plan = plan_roles(topic, analyze_topic(topic))
    agents = generate_agents(topic, analyze_topic(topic), role_plan=plan)

    assert {role.role_kind for role in plan.roles} >= {"beneficiary", "affected", "governance"}
    assert not any("夜市" in agent.agent_name or "摊贩" in agent.agent_name for agent in agents)
    assert all(agent.role_kind for agent in agents if agent.agent_id not in {"agent_host", "agent_reviewer"})


def test_api_returns_role_plan_and_dynamic_agents() -> None:
    topic = "老旧小区广场舞是否应该继续？"
    result = asyncio.run(start_deliberation(DeliberationRequest(topic=topic)))

    assert result["role_plan"]["planner"] == "deterministic_role_planner"
    assert any(role["role_name"] == "广场舞参与者代表" for role in result["role_plan"]["roles"])
    assert not any("夜市" in agent["name"] or "摊贩" in agent["name"] for agent in result["agents"])

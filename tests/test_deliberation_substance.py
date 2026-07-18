from __future__ import annotations

import json

from ma_deliberation_demo.artifacts import PositionCard, RoundSummary, Stance
from ma_deliberation_demo.llm_client import SimulationClient
from ma_deliberation_demo.validators import validate_deliberation_substance


def test_simulation_dynamic_role_opening_is_not_identity_template() -> None:
    client = SimulationClient()
    raw = client.chat(
        [{"role": "user", "content": "请以 JSON 格式输出本轮发言"}],
        system="""## 你的角色
- 名称：广场舞参与者代表
- 身份：直接受益方
- 核心利益：持续锻炼机会、合理使用公共空间
- 基本立场：根据角色利益与证据形成条件性立场
""",
        json_mode=True,
    )

    content = json.loads(raw)["content"]
    assert "我是广场舞参与者代表。根据角色利益与证据形成条件性立场。" not in content
    assert "持续锻炼机会" in content
    assert len(content) >= 35


def test_simulation_review_is_explicitly_non_passing() -> None:
    client = SimulationClient()
    raw = client.chat(
        [{"role": "user", "content": "请输出 issues、required_revisions、recommendation 和 review_detail"}],
        json_mode=True,
    )

    review = json.loads(raw)
    assert review["recommendation"] == "revise"
    assert review["issues"]
    assert len(review["review_detail"]) >= 20


def test_identity_only_discussion_cannot_pass_substance_gate() -> None:
    cards = [
        PositionCard(
            agent_id="dance", stakeholder_group="直接受益方", stance=Stance.NEUTRAL,
            claims=["我是广场舞参与者代表。根据角色利益与证据形成条件性立场。"],
        ),
        PositionCard(
            agent_id="resident", stakeholder_group="直接受影响方", stance=Stance.NEUTRAL,
            claims=["我是周边居民代表。根据角色利益与证据形成条件性立场。"],
        ),
    ]

    result = validate_deliberation_substance(cards, [RoundSummary(round_no=1)], None, ["RAG:C-001:0"])

    assert result.consistency_errors
    assert any("具体主张" in error or "有效主张" in error for error in result.consistency_errors)
    assert any("证据" in error for error in result.consistency_errors)

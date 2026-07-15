"""Topic Analyzer: parses input topic → topic type, conflict axes, complexity score."""

from __future__ import annotations

from .schemas import ConflictAxis, TopicAnalysis, TopicType


# Staged complexity rubric per dimension (0–2 each, total 0–10)
COMPLEXITY_RUBRIC = {
    "stakeholder_diversity": {
        0: "1–2 类利益群体",
        1: "3–4 类利益群体",
        2: "5+ 类利益群体，包含沉默群体",
    },
    "conflict_dimensions": {
        0: "单一争议维度（如仅经济）",
        1: "2–3 个交叉维度",
        2: "4+ 个维度，涉及权利/制度/文化交叉",
    },
    "evidence_requirements": {
        0: "常识即可覆盖",
        1: "需要政策或工单等 1–2 类来源",
        2: "需要多来源交叉验证（政策+工单+案例）",
    },
    "tool_call_requirements": {
        0: "无需外部工具",
        1: "需要检索或计算工具",
        2: "需要多工具链式调用",
    },
    "implementation_complexity": {
        0: "方案可直接执行",
        1: "需要跨部门协调",
        2: "涉及法规修订或长期试点",
    },
}

# Pre-built topic library for common urban governance issues
TOPIC_LIBRARY = {
    "夜市": TopicAnalysis(
        topic_type=TopicType.PUBLIC_SPACE,
        conflict_axes=[
            ConflictAxis(
                name="经济生存权 vs 居住环境权",
                parties=["摊贩", "居民"],
                intensity="high",
                description="摊贩依赖夜市收入维持生计，居民受噪声油烟垃圾直接影响",
            ),
            ConflictAxis(
                name="消费便利 vs 公共秩序",
                parties=["消费者", "街道办"],
                intensity="medium",
                description="夜市提供便利低价消费，但无序经营影响交通和市容",
            ),
            ConflictAxis(
                name="治理成本分摊",
                parties=["环卫人员", "摊贩", "街道办"],
                intensity="medium",
                description="闭市后垃圾清运成本由谁承担未明确",
            ),
        ],
        silent_stakeholders=["城市设计师", "周边非投诉老年居民", "外来务工租房者"],
        power_asymmetry="居民有 12345 投诉渠道和业主委员会，摊贩和环卫缺乏制度性代表",
        complexity_score=7,
        complexity_breakdown={
            "stakeholder_diversity": 2,
            "conflict_dimensions": 2,
            "evidence_requirements": 1,
            "tool_call_requirements": 1,
            "implementation_complexity": 1,
        },
    ),
    "广场舞": TopicAnalysis(
        topic_type=TopicType.PUBLIC_SPACE,
        conflict_axes=[
            ConflictAxis(
                name="健身需求 vs 噪声扰民",
                parties=["跳舞老人", "周边居民"],
                intensity="high",
                description="老年人健身需求与居民安静休息权冲突",
            ),
            ConflictAxis(
                name="公共空间使用权分配",
                parties=["跳舞老人", "其他空间使用者", "物业"],
                intensity="medium",
                description="有限的公共空间如何在不同群体间公平分配",
            ),
        ],
        silent_stakeholders=["需要安静环境的居家工作者", "婴幼儿家庭"],
        power_asymmetry="老年人常被视为'弱势群体'，投诉处理更谨慎",
        complexity_score=5,
        complexity_breakdown={
            "stakeholder_diversity": 1,
            "conflict_dimensions": 1,
            "evidence_requirements": 1,
            "tool_call_requirements": 1,
            "implementation_complexity": 1,
        },
    ),
    "老旧小区加装电梯": TopicAnalysis(
        topic_type=TopicType.INFRASTRUCTURE,
        conflict_axes=[
            ConflictAxis(
                name="高层便利 vs 低层采光与成本",
                parties=["高楼层住户", "低楼层住户"],
                intensity="high",
                description="高楼层老人出行困难，低楼层担心采光、噪音和房产贬值",
            ),
            ConflictAxis(
                name="费用分摊公平性",
                parties=["各楼层住户", "物业"],
                intensity="medium",
                description="谁出多少钱才合理缺乏统一标准",
            ),
        ],
        silent_stakeholders=["租户", "短期不打算使用的年轻住户"],
        power_asymmetry="高楼层老人有更强的道德话语权，低楼层有法律上的相邻权",
        complexity_score=6,
        complexity_breakdown={
            "stakeholder_diversity": 2,
            "conflict_dimensions": 1,
            "evidence_requirements": 1,
            "tool_call_requirements": 1,
            "implementation_complexity": 1,
        },
    ),
}


def analyze_topic(topic: str) -> TopicAnalysis:
    """Match input topic against known library; fall back to heuristic analysis."""
    for keyword, analysis in TOPIC_LIBRARY.items():
        if keyword in topic:
            return analysis

    return TopicAnalysis(
        topic_type=TopicType.PUBLIC_SPACE,
        conflict_axes=[
            ConflictAxis(
                name="待分析冲突维度",
                parties=["支持方", "反对方"],
                intensity="medium",
                description="",
            ),
        ],
        silent_stakeholders=["需进一步调研确定"],
        power_asymmetry="待实地调研",
        complexity_score=3,
        complexity_breakdown={
            "stakeholder_diversity": 1,
            "conflict_dimensions": 0,
            "evidence_requirements": 1,
            "tool_call_requirements": 0,
            "implementation_complexity": 1,
        },
    )


def compute_complexity(analysis: TopicAnalysis) -> dict:
    """Return human-readable complexity breakdown."""
    return {
        "total": analysis.complexity_score,
        "level": "low" if analysis.complexity_score <= 3 else ("medium" if analysis.complexity_score <= 6 else "high"),
        "dimensions": {
            k: {"score": v, "description": COMPLEXITY_RUBRIC[k][v]}
            for k, v in analysis.complexity_breakdown.items()
        },
    }

from __future__ import annotations

from .schemas import TopicAnalysis


TOPIC_PRESETS = {
    "夜市": {
        "topic_type": "公共空间治理 / 夜间经济治理",
        "conflict_dimensions": [
            "摊贩生计 vs 居民休息",
            "城市活力 vs 市容秩序",
            "消费便利 vs 环境卫生",
            "公共空间开放 vs 执法与维护成本",
        ],
        "potential_stakeholders": ["夜市摊贩", "周边居民", "消费者", "街道办", "城管", "环卫人员", "城市设计师"],
        "required_archetypes": ["直接受益者", "直接受损者", "执行管理者", "弱势 / 沉默群体", "专业技术者", "公共利益代表"],
        "suggested_agents": ["夜市摊贩代表", "周边居民代表", "夜间消费者代表", "街道办治理人员", "环卫人员代表", "城市设计师"],
        "difficulty_score": 4,
    },
    "电梯": {
        "topic_type": "社区更新 / 既有住宅改造",
        "conflict_dimensions": [
            "高楼层出行便利 vs 低楼层采光噪声影响",
            "公共收益 vs 个体损害",
            "费用分摊 vs 后期维护责任",
            "多数同意 vs 少数权利保护",
        ],
        "potential_stakeholders": ["高楼层老人", "低楼层居民", "业委会", "街道办", "设计单位", "物业"],
        "required_archetypes": ["直接受益者", "直接受损者", "执行管理者", "专业技术者", "公共利益代表"],
        "suggested_agents": ["高楼层老人代表", "低楼层居民代表", "业委会代表", "街道办人员", "电梯设计工程师", "物业代表"],
        "difficulty_score": 5,
    },
}


def analyze_topic(topic: str) -> TopicAnalysis:
    matched = None
    for keyword, preset in TOPIC_PRESETS.items():
        if keyword in topic:
            matched = preset
            break
    if matched is None:
        matched = {
            "topic_type": "社区公共空间治理",
            "conflict_dimensions": ["公共利益 vs 个体利益", "便利性 vs 秩序维护", "短期诉求 vs 长期治理成本"],
            "potential_stakeholders": ["受益居民", "受影响居民", "街道办", "物业", "规划师"],
            "required_archetypes": ["直接受益者", "直接受损者", "执行管理者", "专业技术者", "公共利益代表"],
            "suggested_agents": ["受益居民代表", "受影响居民代表", "街道办人员", "物业代表", "社区规划师"],
            "difficulty_score": 3,
        }
    score = matched["difficulty_score"]
    difficulty = "低" if score <= 2 else "中" if score <= 4 else "高"
    return TopicAnalysis(
        topic=topic,
        topic_type=matched["topic_type"],
        difficulty=difficulty,
        difficulty_score=score,
        conflict_dimensions=matched["conflict_dimensions"],
        potential_stakeholders=matched["potential_stakeholders"],
        required_archetypes=matched["required_archetypes"],
        suggested_agents=matched["suggested_agents"],
    )

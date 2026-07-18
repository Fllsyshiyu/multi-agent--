"""Role Assigner Agent: LLM-driven topic analysis → stakeholder role generation.

This module provides the "角色分配agent" that analyzes a user's topic text
and dynamically generates the most relevant stakeholder roles (minimum 4 groups).
It can work with LLM clients or fall back to simulation-based assignment.
"""

from __future__ import annotations

import json
import re

# Pre-built role assignment profiles for common topics (simulation fallback)
ROLE_PROFILES = {
    "夜市": [
        {"name": "夜市摊贩代表", "role": "直接受益者", "emoji": "🍜", "color": "#f59e0b",
         "stance": 0.8, "archetypeKey": "直接受益者",
         "interests": ["保留经营机会", "获得稳定摊位", "避免一刀切取缔", "参与规则制定"]},
        {"name": "周边居民代表", "role": "直接受影响者", "emoji": "🏠", "color": "#ef4444",
         "stance": -0.7, "archetypeKey": "直接受影响者",
         "interests": ["保障居住环境质量", "明确闭市时间和噪声管控", "建立投诉响应机制", "确保消防和通行安全"]},
        {"name": "夜间消费者代表", "role": "间接受益者", "emoji": "🛍️", "color": "#8b5cf6",
         "stance": 0.5, "archetypeKey": "间接受益者",
         "interests": ["保留便利低价消费选择", "合理的营业时间", "食品安全和卫生", "多样化业态"]},
        {"name": "街道办治理人员", "role": "治理方", "emoji": "🏛️", "color": "#3b82f6",
         "stance": 0.1, "archetypeKey": "治理方",
         "interests": ["减少居民投诉", "维护公共秩序", "落实上级政策", "避免极端事件"]},
        {"name": "环卫人员代表", "role": "间接影响者", "emoji": "🧹", "color": "#10b981",
         "stance": -0.3, "archetypeKey": "间接影响者",
         "interests": ["获得额外清扫经费", "合理配置垃圾桶和清运频次", "不被转嫁治理成本", "劳动条件和安全保障"]},
        {"name": "城市设计师", "role": "专业观察者", "emoji": "📐", "color": "#ec4899",
         "stance": 0.2, "archetypeKey": "专业观察者",
         "interests": ["提出可量化可验证的试点方案", "引入国内外空间治理经验", "从保留vs取缔转向条件化治理", "确保方案可执行可复评"]},
    ],
    "广场舞": [
        {"name": "广场舞队伍代表", "role": "直接受益者", "emoji": "💃", "color": "#f59e0b",
         "stance": 0.8, "archetypeKey": "直接受益者",
         "interests": ["保留就近的健身活动空间", "获得明确的使用时间安排", "不被驱逐或强制迁往远距离场地", "参与制定使用规则"]},
        {"name": "受噪音影响居民代表", "role": "直接受影响者", "emoji": "🏠", "color": "#ef4444",
         "stance": -0.7, "archetypeKey": "直接受影响者",
         "interests": ["保障居住环境的安静", "明确活动时间和音量限制", "建立投诉和调解机制", "确保休息时段不受干扰"]},
        {"name": "其他空间使用者代表", "role": "直接受影响者", "emoji": "🚶", "color": "#8b5cf6",
         "stance": -0.5, "archetypeKey": "直接受影响者",
         "interests": ["确保公共空间的多样化使用", "获得安静休息和散步的空间", "明确各时段的空间使用分配", "儿童和家庭活动场地的保障"]},
        {"name": "物业管理人员", "role": "治理方", "emoji": "🏛️", "color": "#3b82f6",
         "stance": 0.1, "archetypeKey": "治理方",
         "interests": ["减少居民投诉", "维护公共空间秩序", "探索公平的使用规则", "避免矛盾升级"]},
        {"name": "居家工作者代表", "role": "间接影响者", "emoji": "💻", "color": "#10b981",
         "stance": -0.4, "archetypeKey": "间接影响者",
         "interests": ["保障日常工作和生活的安静环境", "获得明确的活动时间和音量限制", "不被忽视作为少数群体的诉求"]},
        {"name": "婴幼儿家庭代表", "role": "间接影响者", "emoji": "👶", "color": "#ec4899",
         "stance": -0.5, "archetypeKey": "间接影响者",
         "interests": ["保障婴幼儿的安静睡眠环境", "活动时间避开晚间婴幼儿入睡时段", "音量控制在合理范围"]},
    ],
    "电梯": [
        {"name": "高楼层住户代表", "role": "直接受益者", "emoji": "🏢", "color": "#f59e0b",
         "stance": 0.9, "archetypeKey": "直接受益者",
         "interests": ["加装电梯以解决出行困难", "公平合理的费用分摊方案", "施工期间尽量减少对生活的影响", "电梯后续维护费用的合理分配"]},
        {"name": "低楼层住户代表", "role": "直接受影响者", "emoji": "🏘️", "color": "#ef4444",
         "stance": -0.6, "archetypeKey": "直接受影响者",
         "interests": ["评估电梯对采光和通风的实际影响", "获得合理的经济补偿", "施工期间的居住保障", "电梯维护费用的合理分配"]},
        {"name": "社区居委会代表", "role": "治理方", "emoji": "🏛️", "color": "#3b82f6",
         "stance": 0.1, "archetypeKey": "治理方",
         "interests": ["协调高低楼层住户的矛盾", "确保政策合规落地", "组织费用分摊方案协商", "监督施工质量和安全"]},
        {"name": "建筑设计专家", "role": "专业观察者", "emoji": "📐", "color": "#ec4899",
         "stance": 0.2, "archetypeKey": "专业观察者",
         "interests": ["评估建筑结构可行性与安全性", "提供电梯加装技术方案", "量化采光和通风影响", "建议最优加装位置"]},
    ],
}

# Fixed facilitator agents (主持人 + 评审员)
FACILITATOR_AGENTS = [
    {"id": "mod", "name": "议事主持人", "role": "流程引导", "emoji": "🎤", "color": "#fbbf24",
     "stance": 0.0, "isFacilitator": True, "archetypeKey": None,
     "interests": ["确保各方发言权平等", "引导讨论聚焦方案设计而非立场对抗", "cue流程阶段控制发言节奏", "观察发言分布调整发言机会"]},
    {"id": "rev", "name": "议事评审员", "role": "质量诊断", "emoji": "🔍", "color": "#34d399",
     "stance": 0.0, "isFacilitator": True, "archetypeKey": None,
     "interests": ["评审议事过程是否公平论证是否充分", "指出逻辑漏洞证据缺失和讨论盲区", "评估各利益群体的讨论质量和参与度", "为议事质量改进提供具体建议"]},
]


def assign_agents_for_topic(topic: str, llm_client=None) -> dict:
    """Analyze a topic and assign appropriate stakeholder agents.

    Uses LLM when available, falls back to keyword-based matching from ROLE_PROFILES.
    Returns a dict with 'agents' list and 'analysis' metadata.
    """
    # Try LLM-driven assignment first
    if llm_client:
        result = _llm_assign(topic, llm_client)
        if result:
            return result

    # Fallback: keyword-based matching
    return _simulation_assign(topic)


def _llm_assign(topic: str, llm_client) -> dict | None:
    """Use LLM to analyze topic and generate stakeholder roles."""
    prompt = f"""你是一位专业的"角色分配agent"，负责分析社区公共空间治理议题并分配最相关的利益群体角色。

## 议题
{topic}

## 任务
1. 分析该议题中涉及的利益群体
2. 确定至少4个最核心的利益相关群体
3. 为每个群体分配角色

## 输出格式（JSON）
{{
  "analysis": "对该议题的简短分析（100字以内）",
  "agents": [
    {{
      "name": "角色名称（如：广场舞队伍代表）",
      "role": "角色定位（直接受益者/直接受影响者/间接受益者/治理方/间接影响者/专业观察者）",
      "emoji": "一个合适的emoji",
      "color": "代表色（hex如#f59e0b）",
      "stance": 立场分数(-1.0到1.0),
      "interests": ["核心利益1", "核心利益2", "核心利益3", "核心利益4"]
    }}
  ]
}}

## 角色类型说明
- 直接受益者：从议题涉及的改变中直接获益的群体（stance通常>0.5）
- 直接受影响者：受到议题改变的负面影响的群体（stance通常<-0.3）
- 间接受益者：间接获利的群体（stance通常0.3-0.6）
- 治理方：负责管理和协调的官方/准官方角色（stance接近0）
- 间接影响者：受到间接影响或被忽视的群体（stance通常-0.3到0）
- 专业观察者：提供专业分析和建议的第三方（stance接近0-0.2）

## 颜色建议
- 直接受益者用暖色如 #f59e0b #f97316
- 直接受影响者用冷色如 #ef4444 #dc2626
- 间接受益者用紫色如 #8b5cf6 #a855f7
- 治理方用蓝色如 #3b82f6 #2563eb
- 间接影响者用绿色如 #10b981 #059669
- 专业观察者用粉色如 #ec4899 #db2777

请直接输出JSON，不要包含markdown代码块。"""

    try:
        raw = llm_client.chat(
            [{"role": "user", "content": prompt}],
            system="你是一个社区治理领域的角色分配专家agent。你擅长分析公共议题中的利益相关方，并为其分配合理的角色定位。",
            json_mode=True,
        )

        # Parse JSON from response
        json_str = raw.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start != -1 and end != -1:
            json_str = json_str[start:end + 1]

        result = json.loads(json_str)

        # Validate and clean agents
        agents = result.get("agents", [])
        if not agents or len(agents) < 4:
            return None  # Fall back to simulation

        # Assign IDs and fill defaults
        valid_roles = {"直接受益者", "直接受影响者", "间接受益者", "治理方", "间接影响者", "专业观察者"}
        colors = ["#f59e0b", "#ef4444", "#8b5cf6", "#3b82f6", "#10b981", "#ec4899"]
        for i, agent in enumerate(agents):
            agent["id"] = f"a{i}"
            agent["isFacilitator"] = False
            if agent.get("role") not in valid_roles:
                agent["role"] = "直接受影响者"
            if not agent.get("archetypeKey"):
                agent["archetypeKey"] = agent.get("role", "")
            if not agent.get("color"):
                agent["color"] = colors[i % len(colors)]
            if not agent.get("emoji"):
                agent["emoji"] = ["👤", "🏠", "🛒", "🏛️", "🔧", "📊"][i % 6]
            if not agent.get("stance"):
                agent["stance"] = 0.0
            if not agent.get("interests"):
                agent["interests"] = ["表达与该议题相关的利益诉求"]

        return {
            "analysis": result.get("analysis", f"针对「{topic}」的角色分配分析"),
            "agents": agents,
        }

    except Exception as e:
        print(f"[RoleAssigner] LLM assignment failed: {e}, falling back to simulation", flush=True)
        return None


def _simulation_assign(topic: str) -> dict:
    """Fallback: keyword-based role assignment from ROLE_PROFILES."""
    for keyword, agents in ROLE_PROFILES.items():
        if keyword in topic:
            # Deep copy agents with IDs
            assigned = []
            for i, a in enumerate(agents):
                assigned.append(dict(a, id=f"a{i}", isFacilitator=False,
                                     archetypeKey=a.get("archetypeKey", a.get("role", ""))))
            return {
                "analysis": f"基于关键词「{keyword}」匹配到{len(assigned)}个相关利益群体",
                "agents": assigned,
            }

    # Generic fallback: create basic agents
    generic = [
        {"name": "议题相关受益方", "role": "直接受益者", "emoji": "👤", "color": "#f59e0b",
         "stance": 0.5, "archetypeKey": "直接受益者",
         "interests": ["从议题相关的改变中获益", "推动有利于自身的方案"]},
        {"name": "议题相关受影响方", "role": "直接受影响者", "emoji": "🏠", "color": "#ef4444",
         "stance": -0.5, "archetypeKey": "直接受影响者",
         "interests": ["避免议题改变带来的负面影响", "保护自身既有权益"]},
        {"name": "治理协调方", "role": "治理方", "emoji": "🏛️", "color": "#3b82f6",
         "stance": 0.0, "archetypeKey": "治理方",
         "interests": ["寻求各方可接受的方案", "减少冲突和投诉", "落实相关政策"]},
        {"name": "第三方观察者", "role": "专业观察者", "emoji": "📊", "color": "#ec4899",
         "stance": 0.1, "archetypeKey": "专业观察者",
         "interests": ["提供客观分析和建议", "引入专业知识和经验", "确保方案可执行"]},
    ]
    assigned = []
    for i, a in enumerate(generic):
        assigned.append(dict(a, id=f"a{i}", isFacilitator=False,
                             archetypeKey=a.get("archetypeKey", a.get("role", ""))))
    return {
        "analysis": f"未匹配到特定议题模板，为「{topic}」生成了{len(assigned)}个通用角色",
        "agents": assigned,
    }

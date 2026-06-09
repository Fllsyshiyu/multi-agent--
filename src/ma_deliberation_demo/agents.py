from __future__ import annotations

from .schemas import AgentCard, TopicAnalysis


def build_agents(analysis: TopicAnalysis) -> list[AgentCard]:
    topic = analysis.topic
    if "夜市" in topic:
        return [
            AgentCard(
                agent_id="vendor",
                agent_name="夜市摊贩代表",
                archetype="直接受益者 / 市场运营主体",
                topic=topic,
                relationship_to_topic="夜市是其主要收入来源，也受摊位规则、执法方式影响最大。",
                main_interests=["保留经营机会", "获得稳定摊位", "避免一刀切取缔", "接受合理规范"],
                stance=0.85,
                possible_stance="支持保留夜市，但接受规范化管理。",
                concerns=["生计", "摊位", "执法", "费用"],
                can_say=["表达经营困难", "提出规范化经营建议", "回应卫生和噪声问题"],
                cannot_say=["不能否认居民噪声困扰", "不能编造收入数据", "不能要求无限制占道"],
            ),
            AgentCard(
                agent_id="resident",
                agent_name="周边居民代表",
                archetype="直接受损者",
                topic=topic,
                relationship_to_topic="居住在夜市周边，直接承受夜间噪声、油烟、人流和卫生影响。",
                main_interests=["保障夜间休息", "控制油烟和垃圾", "保持通行和安全", "投诉能得到回应"],
                stance=-0.75,
                possible_stance="反对无序夜市，条件接受限时限区经营。",
                concerns=["噪声", "油烟", "垃圾", "通行", "安全"],
                can_say=["表达居住影响", "提出时间和区域限制", "要求投诉反馈机制"],
                cannot_say=["不能把所有摊贩都描述为违规者", "不能忽视消费便利和生计问题"],
            ),
            AgentCard(
                agent_id="consumer",
                agent_name="夜间消费者代表",
                archetype="直接受益者 / 公共利益代表",
                topic=topic,
                relationship_to_topic="夜市提供低价、近距离、夜间可达的消费选择。",
                main_interests=["保留便利消费", "提升食品安全", "保持公共空间体验", "支持规范化"],
                stance=0.55,
                possible_stance="支持保留，但希望提升卫生、食品安全和通行秩序。",
                concerns=["便利", "食品安全", "价格", "通行"],
                can_say=["说明消费便利", "支持分区管理", "提出食品安全和投诉渠道"],
                cannot_say=["不能忽视周边居民夜间休息", "不能把热闹等同于治理成功"],
            ),
            AgentCard(
                agent_id="street",
                agent_name="街道办治理人员",
                archetype="执行管理者",
                topic=topic,
                relationship_to_topic="负责协调市容、民生、居民投诉和多部门治理。",
                main_interests=["降低投诉", "避免运动式治理", "形成可执行规则", "控制治理成本"],
                stance=0.05,
                possible_stance="中立，倾向试点规范化而非简单取缔。",
                concerns=["投诉", "执法", "治理成本", "规则"],
                can_say=["提出试点和规则", "平衡多方利益", "说明治理能力边界"],
                cannot_say=["不能承诺超出街道权限的事项", "不能用模糊口号代替执行规则"],
            ),
            AgentCard(
                agent_id="sanitation",
                agent_name="环卫人员代表",
                archetype="弱势 / 沉默群体",
                topic=topic,
                relationship_to_topic="夜市结束后承担清扫压力，但在正式议事中常被忽视。",
                main_interests=["减少额外清扫负担", "明确垃圾投放责任", "获得必要设备和费用支持"],
                stance=-0.25,
                possible_stance="不反对夜市，但要求摊贩、街道和运营方承担清洁责任。",
                concerns=["垃圾", "清扫", "责任", "费用"],
                can_say=["指出末端维护压力", "要求垃圾分类与清扫经费", "提出闭市后清场机制"],
                cannot_say=["不能代表居民或摊贩做最终决定", "不能只提出取缔而不说明维护需求"],
            ),
            AgentCard(
                agent_id="planner",
                agent_name="城市设计师",
                archetype="专业技术者",
                topic=topic,
                relationship_to_topic="从空间组织、动线、设施配置和试点评估角度提出方案。",
                main_interests=["降低空间冲突", "保障无障碍通行", "通过设计和规则提升治理", "设置可评估试点"],
                stance=0.15,
                possible_stance="条件支持，重点是时段、边界、设施和评估指标。",
                concerns=["空间", "动线", "设施", "评估"],
                can_say=["提出空间分区", "设计试点指标", "识别风险点"],
                cannot_say=["不能替代真实民意调查", "不能只给美化方案而不回应治理成本"],
            ),
        ]
    # Default simple agents for elevator topic or other community renewal cases.
    return [
        AgentCard("beneficiary", "直接受益居民代表", "直接受益者", topic, "该方案能显著改善其日常使用体验。", ["便利", "安全", "公平"], 0.8, "支持推进，但接受协商补偿。", ["便利", "安全", "费用"], ["说明需求", "提出折中方案"], ["不能否认受损方影响"]),
        AgentCard("affected", "受影响居民代表", "直接受损者", topic, "该方案可能带来采光、噪声、成本或通行影响。", ["减少损害", "获得补偿", "保障知情权"], -0.7, "反对强推，条件接受减损和补偿。", ["噪声", "成本", "公平"], ["说明损害", "提出约束条件"], ["不能一概否认公共收益"]),
        AgentCard("manager", "街道办人员", "执行管理者", topic, "负责协调居民意见与程序执行。", ["程序合规", "减少纠纷", "形成可执行方案"], 0.05, "中立协调。", ["规则", "程序", "成本"], ["说明流程", "提出协商机制"], ["不能承诺越权事项"]),
        AgentCard("expert", "社区规划师", "专业技术者", topic, "负责从空间、技术和实施角度提出建议。", ["技术可行", "公共安全", "长期维护"], 0.2, "条件支持。", ["技术", "维护", "评估"], ["提出技术约束", "说明风险"], ["不能替代民意"]),
    ]

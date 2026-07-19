"""Plan topic-specific stakeholder roles before creating deliberation agents.

The planner is deliberately a system orchestration step rather than a debating
persona.  It produces a bounded, reviewable plan which the Agent Factory can
materialize without inventing real people or local facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .schemas import TopicAnalysis


@dataclass(frozen=True)
class RoleSpec:
    role_id: str
    role_name: str
    role_kind: str
    relationship_to_topic: str
    main_interests: tuple[str, ...]
    stance_score: float
    evidence_focus: tuple[str, ...]
    is_silent_stakeholder: bool = False


@dataclass(frozen=True)
class RolePlan:
    topic: str
    roles: tuple[RoleSpec, ...]
    silent_stakeholders: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    planner: str = "deterministic_role_planner"
    requires_user_review: bool = True

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "roles": [asdict(role) for role in self.roles],
            "silent_stakeholders": list(self.silent_stakeholders),
            "rationale": list(self.rationale),
            "planner": self.planner,
            "requires_user_review": self.requires_user_review,
        }


ROLE_KIND_DEFAULTS = {
    "beneficiary": {
        "archetype": "直接受益方",
        "can_say": ("表达自身收益、成本和可接受条件", "提出可执行的自律或补偿方案"),
        "cannot_say": ("不能否认其他群体的合理损害", "不能虚构收入、人数或当地事实"),
    },
    "affected": {
        "archetype": "直接受影响方",
        "can_say": ("表达可观察的影响、风险和底线", "提出可核验的治理要求"),
        "cannot_say": ("不能替代全体居民下结论", "不能编造投诉、健康或安全数据"),
    },
    "governance": {
        "archetype": "治理与执行方",
        "can_say": ("说明职责边界、执行成本和可操作机制", "协调不同群体的条件化方案"),
        "cannot_say": ("不能作出未经授权的承诺", "不能忽视任何一方的合理诉求"),
    },
    "implementation": {
        "archetype": "一线实施与运维方",
        "can_say": ("说明实施负荷、资源缺口和安全条件", "提出成本与责任分配要求"),
        "cannot_say": ("不能代表主管部门作政策决定", "不能把成本或风险转嫁为既成事实"),
    },
    "expert": {
        "archetype": "专业与证据角色",
        "can_say": ("说明适用条件、证据边界和可评估指标", "提出试点与复盘方案"),
        "cannot_say": ("不能替代公众作价值选择", "不能把外部案例说成当前社区事实"),
    },
}


def _role(
    role_id: str,
    role_name: str,
    role_kind: str,
    relationship: str,
    interests: tuple[str, ...],
    stance: float,
    evidence_focus: tuple[str, ...],
) -> RoleSpec:
    return RoleSpec(role_id, role_name, role_kind, relationship, interests, stance, evidence_focus)


def _night_market_plan(topic: str) -> RolePlan:
    roles = (
        _role("beneficiary", "夜市经营者代表", "beneficiary", "夜间经营直接关系其收入和稳定预期", ("经营机会", "规则稳定性", "合规成本"), 0.7, ("经营影响", "规范经营", "替代生计")),
        _role("affected", "周边居民代表", "affected", "夜间噪声、油烟、垃圾和通行秩序直接影响居住体验", ("安宁", "卫生", "通行安全"), -0.7, ("投诉", "噪声", "油烟", "安全")),
        _role("governance", "社区与街道治理代表", "governance", "负责协调投诉、公共秩序与可执行规则", ("可执行性", "公共秩序", "协商机制"), 0.0, ("政策依据", "执行机制", "责任分配")),
        _role("implementation", "环卫与现场运维代表", "implementation", "承担清扫、秩序维护等一线执行负荷", ("人力负荷", "经费", "设施条件"), -0.2, ("运维成本", "垃圾", "现场安全")),
        _role("expert", "公共空间治理专家", "expert", "提供公共空间使用、试点和评估方面的专业意见", ("证据质量", "试点评估", "替代方案"), 0.1, ("相似案例", "评估指标", "迁移条件")),
    )
    return RolePlan(topic, roles, rationale=("覆盖经营受益、居住影响、治理、实施与专业证据五类视角",))


def _square_dance_plan(topic: str) -> RolePlan:
    roles = (
        _role("beneficiary", "广场舞参与者代表", "beneficiary", "需要便利、低成本的日常健身与社交空间", ("健身与社交", "活动连续性", "可达场地"), 0.6, ("健康收益", "替代场地", "活动规则")),
        _role("affected", "周边居民代表", "affected", "夜间声响和空间占用可能影响休息、育儿和居家工作", ("安宁", "可预期休息", "共享空间公平"), -0.6, ("噪声", "投诉", "时间边界")),
        _role("governance", "社区与物业协调代表", "governance", "负责公共空间规则、协商及日常执行协调", ("规则可执行性", "协商", "冲突响应"), 0.0, ("社区规则", "协商机制", "执行记录")),
        _role("expert", "公共空间与健康治理专家", "expert", "评估替代空间、时间分配和可复盘的试点条件", ("空间调度", "证据质量", "效果评估"), 0.1, ("相似案例", "噪声治理", "迁移条件")),
    )
    return RolePlan(topic, roles, silent_stakeholders=("婴幼儿家庭", "居家办公者"), rationale=("覆盖活动参与者、受影响居民、协调执行方与专业评估方",))


def _elevator_plan(topic: str) -> RolePlan:
    roles = (
        _role("beneficiary", "高楼层住户代表", "beneficiary", "加装电梯可能改善出行与居住便利", ("无障碍出行", "使用便利", "费用可承受性"), 0.7, ("出行需求", "费用", "受益范围")),
        _role("affected", "低楼层住户代表", "affected", "施工、采光、噪声及费用安排可能带来直接影响", ("相邻权利", "施工影响", "费用公平"), -0.5, ("采光", "施工", "补偿", "费用分摊")),
        _role("governance", "社区与物业协调代表", "governance", "负责程序协商、施工协调和后续管理衔接", ("程序合法性", "协商", "维护责任"), 0.0, ("审批规则", "协商程序", "维护机制")),
        _role("expert", "无障碍与建筑安全专家", "expert", "评估技术可行性、安全约束及费用方案", ("安全", "技术可行性", "评估指标"), 0.1, ("技术规范", "相似案例", "风险边界")),
    )
    return RolePlan(topic, roles, silent_stakeholders=("租户", "行动不便者"), rationale=("覆盖主要受益和受影响住户、协调方与技术风险视角",))


def _generic_plan(topic: str, analysis: TopicAnalysis) -> RolePlan:
    subject = topic.strip() or "该公共事务议题"
    roles = (
        _role("beneficiary", "议题相关使用者/受益方代表", "beneficiary", f"{subject}可能带来直接使用价值或收益", ("使用需求", "方案连续性", "合理成本"), 0.4, ("需求规模", "受益条件", "替代方案")),
        _role("affected", "可能受影响居民/群体代表", "affected", f"{subject}可能带来环境、权益或生活安排方面的影响", ("风险控制", "公平", "可申诉机制"), -0.4, ("影响证据", "风险", "投诉与反馈")),
        _role("governance", "社区或主管执行方代表", "governance", f"负责将{subject}转化为可执行、可监督的公共规则", ("程序公平", "执行成本", "责任边界"), 0.0, ("政策规则", "执行资源", "责任分工")),
        _role("expert", "议题相关专业与证据代表", "expert", f"提供与{subject}相关的专业解释、案例边界和评估框架", ("证据质量", "可行性", "试点评估"), 0.0, ("相似案例", "评估指标", "迁移条件")),
    )
    return RolePlan(
        topic,
        roles,
        silent_stakeholders=tuple(analysis.silent_stakeholders),
        rationale=("议题不在预设专题中，使用通用利益相关方覆盖并要求会前人工确认",),
        requires_user_review=True,
    )


def validate_role_plan(plan: RolePlan) -> list[str]:
    """Return audit messages rather than silently accepting unsafe role plans."""
    issues: list[str] = []
    if not 3 <= len(plan.roles) <= 8:
        issues.append("参与型角色数量必须在 3 到 8 个之间")
    ids = [role.role_id for role in plan.roles]
    if len(ids) != len(set(ids)):
        issues.append("角色 ID 不可重复")
    kinds = {role.role_kind for role in plan.roles}
    for required in ("beneficiary", "affected", "governance"):
        if required not in kinds:
            issues.append(f"角色计划缺少必要视角：{required}")
    for role in plan.roles:
        if role.role_kind not in ROLE_KIND_DEFAULTS:
            issues.append(f"未知角色类型：{role.role_kind}")
        if not role.role_name.strip() or not role.main_interests:
            issues.append(f"角色信息不完整：{role.role_id}")
    return issues


def plan_roles(topic: str, analysis: TopicAnalysis) -> RolePlan:
    """Create a bounded plan; known topics get tailored roles, others stay neutral."""
    if "夜市" in topic:
        plan = _night_market_plan(topic)
    elif "广场舞" in topic:
        plan = _square_dance_plan(topic)
    elif "电梯" in topic:
        plan = _elevator_plan(topic)
    else:
        plan = _generic_plan(topic, analysis)
    issues = validate_role_plan(plan)
    if issues:
        raise ValueError("Invalid role plan: " + "；".join(issues))
    return plan

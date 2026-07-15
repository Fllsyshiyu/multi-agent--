# 多智能体议事厅 Agent 流程 SOP v1.2（职责-工件-校验版）

## 0. 文件定位

本文件定义多智能体议事厅从“用户输入议题”到“输出议事报告与社会过程状态包”的标准作业流程。

本版本在 v1.1 的基础上，进一步明确 SOP 如何实现以下目标：

> 让每个 Agent 在明确职责、输入、输出和校验条件下协作，形成可复现、可追踪、可评估的城市公共议事过程。

本 SOP 不把 Agent 视为自由聊天角色，而是将其视为在固定流程中生产结构化工件的协作单元。

---

## 0.1 本次更新重点

本版本新增五层执行机制：

```text
Agent Contract：规定每个 Agent 的职责边界。
Stage Contract：规定每个阶段的输入、输出和通过条件。
Artifact Chain：用结构化工件串联议事过程。
Validation Gate：在关键阶段设置校验门。
Observer Metrics：用指标记录议事质量。
```

因此，本 SOP 的核心不是“让 Agent 依次发言”，而是：

```text
职责明确
→ 输入明确
→ 输出明确
→ 校验明确
→ 过程可追踪
→ 结果可评估
```

---

# 1. 总体原则

## 1.1 Agent 不是自由聊天，而是结构化协作

每个 Agent 必须根据自己的职责、输入工件和输出格式行动。Agent 的发言只有被转化为结构化工件后，才能进入下一阶段。

常用工件包括：

```text
Agent Card
Evidence Card
Deliberation Plan
Position Card
Outer Observation Card
Fishbowl Summary Card
Objection / Revision Card
Proposal Card
Review Card
Vote Record
Social Process State Package
```

## 1.2 观点不直接进入方案

任何观点进入最终方案前，必须经过以下检查：

```text
角色边界检查
证据支撑检查
冲突覆盖检查
少数意见保留检查
公共资源检查
Universalization 检查
可执行性检查
```

## 1.3 每轮只继承摘要和工件

下一轮 Agent 不读取完整历史聊天记录，只读取：

```text
Case Context
自己的 Agent Card
相关 Evidence Cards
上一轮 Fishbowl Summary Card
与自己相关的 Observation / Objection / Revision Cards
```

这可以降低上下文噪声，避免观点过快坍缩，也方便追踪每一轮到底继承了什么。

## 1.4 少数意见必须保留

只要某个 Agent 提出有证据支持的反对意见，即使它没有进入内圈，也必须被记录在 Fishbowl Summary Card 和最终报告的“少数意见 / 未解决问题”部分。

## 1.5 AI 议事不替代真实决策

最终报告必须标注：

```text
哪些结论由证据支持；
哪些是 Agent 偏好；
哪些是系统推断；
哪些需要真实调研验证。
```

---

# 2. Agent Contract：明确每个 Agent 的职责

每个 Agent 必须用 Agent Contract 定义其职责、输入、输出和边界。Agent Contract 是角色生成后的基本工作协议。

## 2.1 Agent Contract 字段

```json
{
  "agent_id": "nearby_resident",
  "role": "周边居民代表",
  "responsibility": "表达夜市对居住安宁、噪声、油烟、垃圾和通行的影响",
  "input": [
    "Case Context",
    "Agent Card",
    "Evidence Cards",
    "Fishbowl Summary Card"
  ],
  "output": [
    "Deliberation Plan",
    "Position Card",
    "Objection / Revision Card"
  ],
  "validation": [
    "是否只代表居民视角",
    "是否引用相关证据",
    "是否说明不可接受条件",
    "是否避免替其他主体做决定"
  ],
  "boundary": [
    "不能代表政府作行政决定",
    "不能否认摊贩生计诉求",
    "不能编造投诉数据"
  ]
}
```

## 2.2 Agent 角色边界

每个 Agent 必须包含：

```text
Profile：它是谁；
Goal：它想保护什么；
Constraints：它受到哪些限制；
Can Say：它可以表达什么；
Cannot Say：它不能越权表达什么；
Evidence Need：它需要哪些证据；
Output Format：它必须输出什么工件。
```

## 2.3 Agent Contract 的作用

Agent Contract 用来解决三类问题：

```text
1. 角色漂移：避免环卫代表突然变成城市战略专家。
2. 证据错配：避免 Agent 引用不属于自身视角的证据。
3. 发言不可追踪：确保每个观点都能追溯到角色、输入和证据。
```

---

# 3. 角色池与鱼缸分层

## 3.1 Agent Pool 的四类角色

Agent Factory 根据议题生成 Agent Pool。所有 Agent 先进入外圈候选池，再由 Orchestrator 根据轮次目标选择内圈。

Agent Pool 至少覆盖四类角色：

| 类别 | 作用 | 例子 |
|---|---|---|
| 直接受益者 | 表达方案带来的收益与机会 | 摊贩、商户、高楼层住户 |
| 直接受影响者 | 表达被损害或被打扰的核心利益 | 居民、低楼层住户、儿童家庭 |
| 治理 / 执行主体 | 判断政策边界、执行成本和责任归属 | 街道办、居委会、物业、城管 |
| 专业 / 维护 / 弱势视角 | 补充容易被忽略的系统成本或专业判断 | 环卫、规划师、交通专家、文保专家、老人、租户 |

外圈不是“不重要角色”，而是“本轮不主发言但持续观察的角色”。

---

# 4. 内圈 / 外圈选择原理

## 4.1 选择目标

内圈选择不是随机抽样，也不是选择最强势角色，而是服务于当前轮次的议事目标。

```text
Round 1：暴露核心冲突。
Round 2：回应遗漏问题，进行质询、反驳和修正。
Round 3：仅在需要时启用，用于方案收敛和处理未解决分歧。
```

## 4.2 两步选择法

每轮内圈选择采用两步法：

```text
第一步：满足席位约束。
第二步：在每类席位内计算优先级。
```

## 4.3 席位约束

每轮内圈默认 4 个 Agent：

```text
1 个直接受益者
1 个直接受影响者
1 个治理 / 执行主体
1 个专业、维护或弱势视角
```

如果议题简单，可压缩为 3 个；如果冲突复杂，可扩展到 5–6 个。第一版 Demo 建议固定 4 个。

## 4.4 优先级评分

Orchestrator 对候选 Agent 计算 Fishbowl Priority：

```text
Fishbowl Priority =
冲突相关度
+ 影响强度
+ 证据需求
+ 弱势 / 沉默主体加权
+ 上轮未充分表达程度
+ 外圈观察申请
- 已发言占比
```

| 因子 | 说明 |
|---|---|
| 冲突相关度 | 该角色是否处在本轮核心冲突中 |
| 影响强度 | 该角色是否直接承担收益、损失或执行成本 |
| 证据需求 | 本轮是否需要该角色补充事实、数据或经验 |
| 弱势 / 沉默主体加权 | 该角色是否容易被多数观点淹没 |
| 上轮未充分表达程度 | 该角色的意见是否在上一轮没有被回应 |
| 外圈观察申请 | 外圈 Agent 是否提交了进入内圈请求 |
| 已发言占比 | 已发言越多，优先级越低 |

## 4.5 轮换规则

每轮结束后，至少替换 2 个内圈 Agent。

默认规则：

```text
Round 1 内圈：核心冲突双方 + 治理方 + 维护 / 专业方
Round 2 内圈：保留 1–2 个核心冲突方 + 替换进入上一轮遗漏问题相关角色
Round 3 内圈：若启用，选择方案制定方 + 主要反对方 + 执行方 + 关键专业方
```

## 4.6 外圈职责

外圈 Agent 不发主发言，但必须提交 Outer Observation Card。

```json
{
  "round_id": 1,
  "agent_id": "elderly_resident",
  "missed_issue": "夜间噪声对老年人睡眠影响没有被充分讨论",
  "objection": "如果只设置闭市时间但没有投诉响应机制，居民仍然缺少救济渠道",
  "evidence_needed": ["夜间投诉时间分布", "噪声记录"],
  "request_to_enter_inner_circle": true
}
```

如果外圈观察提出了有证据支持的强反对意见，Orchestrator 必须在下一轮满足至少一项：

```text
邀请该 Agent 进入内圈；
将其问题写入下一轮必答问题；
在 Summary Card 中记录为少数意见或未解决冲突。
```

---

# 5. Stage Contract：每个阶段的输入、输出和校验

每个阶段都必须按照同一格式执行：

```text
阶段编号：
阶段目标：
负责 Agent：
输入工件：
输出工件：
校验条件：
失败处理：
进入下一阶段条件：
```

这可以保证整个过程可复现、可追踪、可评估。

---

# 6. SOP 总流程

```text
S0 议题输入
S1 议题与冲突分析
S2 证据收集与证据卡生成
S3 Agent Pool 生成
S4 鱼缸轮次规划
S5 内圈 Agent 生成议事行动计划
S6 Round 1：立场陈述
S7 外圈观察 + Round 1 摘要
S8 Round 2：质询、反驳、修正
S9 生成工作草案
S10 方案审查：约束校验 + Universalization + 公共资源评估
S11 最终修正与投票
S12 输出议事报告 + 社会过程状态包
```

---

# 7. 阶段表

| 阶段 | 目标 | 主要输入 | 主要输出 | 校验重点 |
|---|---|---|---|---|
| S0 | 明确议题与边界 | 用户输入 | Case Context | problem/question 是否清楚 |
| S1 | 拆解冲突与约束 | Case Context | Issue Analysis Card | 是否覆盖核心冲突和硬约束 |
| S2 | 收集和匹配证据 | 议题、冲突、角色需求 | Evidence Cards | 证据是否标注来源和适用角色 |
| S3 | 生成利益相关方 | Issue Analysis + Evidence | Agent Cards | 角色是否覆盖支持方、反对方、治理方、专业/弱势方 |
| S4 | 规划内圈 / 外圈 | Agent Pool + 冲突结构 | Fishbowl Round Plan | 是否满足席位约束和轮换规则 |
| S5 | 明确本轮发言策略 | Agent Card + Evidence + Summary | Deliberation Plan | 是否说明底线、让步、质询对象和证据 |
| S6 | 暴露核心立场 | 内圈 Agent | Position Cards | 是否有角色边界和证据支撑 |
| S7 | 记录遗漏与继承信息 | 内圈发言 + 外圈观察 | Fishbowl Summary Card | 是否保留少数意见和未回答问题 |
| S8 | 质询、反驳和修正 | Summary + Observation Cards | Objection / Revision Cards | 是否回应上一轮遗漏问题 |
| S9 | 形成候选方案 | 冲突、诉求、修正意见 | Proposal Cards | 是否回应主要冲突和约束 |
| S10 | 审查方案可持续性 | Proposal Cards | Review Cards | 是否通过约束、公共资源、Universalization 检查 |
| S11 | 形成条件性共识 | Review Cards + 修订方案 | Vote Record | 是否记录支持、反对和保留意见 |
| S12 | 输出结果和状态 | 全部工件 | Report + State Package | 是否区分共识、分歧、风险和调研需求 |

---

# 8. 关键阶段 Contract 示例

## S5 Agent 议事行动计划

### 阶段目标

让内圈 Agent 在发言前明确自己的本轮目标、底线、可让步点、质询对象和证据引用。

### 负责 Agent

当前轮内圈 Stakeholder Agents。

### 输入工件

```text
Case Context
Agent Card
Evidence Cards
Fishbowl Round Plan
上一轮 Fishbowl Summary Card（Round 2 起）
```

### 输出工件：Deliberation Plan

```json
{
  "agent": "周边居民代表",
  "round_goal": "说明现状不可接受之处",
  "core_interest": "夜间安宁和环境卫生",
  "non_negotiables": ["必须有闭市时间", "必须有投诉响应机制"],
  "possible_concessions": ["接受有限时、有限点位的试点保留"],
  "question_to_others": ["摊贩是否接受卫生押金？", "街道是否能承诺执法频次？"],
  "evidence_to_use": ["E-NM-002", "E-NM-003"]
}
```

### 校验条件

```text
是否说明核心诉求；
是否说明不可让步条件；
是否说明可让步条件；
是否指定至少一个质询对象或回应对象；
是否引用相关证据。
```

### 失败处理

```text
缺少证据：返回 Evidence Agent 补充或标记 evidence_gap。
角色越界：Boundary Checker 标记并要求重写。
过于空泛：Moderator 要求补充底线和让步条件。
```

---

## S6 鱼缸 Round 1：立场陈述

### 阶段目标

让内圈 Agent 基于自身角色、证据和行动计划表达初始立场。

### 负责 Agent

当前轮内圈 Stakeholder Agents。

### 输入工件

```text
Case Context
Agent Card
Evidence Cards
Deliberation Plan
Fishbowl Round Plan
```

### 输出工件：Position Card

```json
{
  "agent": "夜市摊贩代表",
  "stance": "支持保留，但接受规范化管理",
  "core_claim": "一刀切取缔会影响摊贩基本生计",
  "evidence_refs": ["E-NM-001", "E-NM-011"],
  "non_negotiables": ["不能无替代方案直接清退"],
  "possible_concessions": ["接受摊位编号", "接受限时经营", "接受卫生押金"],
  "questions_to_others": ["居民能否接受试点期？", "街道能否提供稳定摊位规则？"]
}
```

### 校验条件

```text
是否说明本角色核心诉求；
是否引用至少一条相关 Evidence Card；
是否说明不可让步条件或可让步条件；
是否没有越权代表其他群体发言；
是否没有直接跳到最终方案。
```

### 失败处理

```text
如果证据不足，标记 evidence_gap。
如果角色越界，交给 Boundary Checker 标记。
如果发言过空泛，Moderator 要求重写为结构化 Position Card。
```

### 进入下一阶段条件

```text
所有内圈 Agent 至少提交一张有效 Position Card。
```

---

## S7 外圈观察 + Round 1 摘要

### 阶段目标

记录内圈讨论的多数意见、少数意见、未解决冲突和外圈遗漏问题，为下一轮轮换提供依据。

### 负责 Agent

Outer Circle Agents、Moderator、Observer。

### 输入工件

```text
Position Cards
Outer Observation Cards
Round 1 发言记录
Observer Snapshot
```

### 输出工件：Fishbowl Summary Card

```json
{
  "round_id": 1,
  "majority_views": ["多数 Agent 认为夜市不宜简单取缔，应转向规范化管理"],
  "minority_views": ["部分居民认为即使规范化，也可能无法解决夜间噪声问题"],
  "core_conflicts": [
    "摊贩经营机会 vs 居民夜间安宁",
    "夜间经济活力 vs 环卫与治理成本"
  ],
  "outer_observations": [
    "老年居民担心夜间噪声对睡眠影响未被充分讨论"
  ],
  "unanswered_questions": [
    "闭市时间设定为几点才可接受？",
    "额外清扫经费由谁承担？",
    "投诉响应机制由谁负责？"
  ],
  "agents_to_invite_next_round": ["老年居民代表", "城市设计师"]
}
```

### 校验条件

```text
是否包含多数意见；
是否包含少数意见；
是否记录外圈观察；
是否保留未回答问题；
是否给出下一轮内圈建议；
是否避免把“文本共识”写成真实共识。
```

### 失败处理

```text
少数意见遗漏：Summary Card 必须补录。
未回答问题为空：Moderator 必须追问执行、资金、责任或时序问题。
摘要过度和谐：Observer 标记 possible_false_consensus。
```

---

## S10 方案审查

### 阶段目标

检查候选方案是否满足硬约束、公共资源可持续性、Universalization 四问和可执行性条件。

### 负责 Agent

Rule Checker、Urban Evaluator、Universalization Agent、Observer。

### 输入工件

```text
Proposal Cards
Issue Analysis Card
Evidence Cards
Fishbowl Summary Cards
Objection / Revision Cards
```

### 输出工件：Review Card

```json
{
  "proposal_id": "proposal_01",
  "hard_constraint_passed": true,
  "public_resource_score": {
    "居民权益": 1,
    "公共财政": -1,
    "空间品质": 1,
    "交通承载": 0,
    "长期韧性": 1,
    "社区信任": 1
  },
  "universalization_result": {
    "普遍性": "如果所有社区夜市都保留，必须配套时间、卫生和投诉机制，否则治理负担会扩散",
    "公平性": "角色互换后，居民仍需获得可执行的安宁保障",
    "延续性": "方案需明确试点周期和退出机制",
    "先例性": "可作为规范化夜市试点，但不能成为无限扩张先例"
  },
  "required_revisions": [
    "补充闭市时间",
    "明确卫生经费来源",
    "设置投诉响应机制"
  ],
  "recommendation": "revise"
}
```

### 校验条件

```text
是否违反硬约束；
是否回应主要冲突；
是否过度消耗公共资源；
是否通过 Universalization 四问；
是否明确责任主体、执行条件和后续调研问题。
```

### 结果

```text
pass：进入投票。
revise：返回 Proposal Agent 修改。
reject：标记为不可采纳方案。
```

---

# 9. Artifact Chain：过程可追踪

每个工件必须带有追踪字段。

```json
{
  "artifact_id": "position_round1_resident_001",
  "stage_id": "S6",
  "round_id": 1,
  "produced_by": "nearby_resident",
  "input_refs": [
    "case_night_market_001",
    "agent_nearby_resident",
    "evidence_E_NM_002",
    "deliberation_plan_resident_r1"
  ],
  "output_type": "Position Card",
  "evidence_refs": ["E-NM-002", "E-NM-003"],
  "validation_status": "passed",
  "reviewer": "Observer"
}
```

通过 Artifact Chain，系统可以回答：

```text
某个结论来自哪一轮？
由哪个 Agent 提出？
依据了哪条证据？
有没有被反驳？
有没有进入最终方案？
有没有被保留为少数意见？
```

---

# 10. Validation Gate：阶段校验门

每个阶段结束后必须经过 Gate Check。只有通过 Gate Check，才能进入下一阶段；未通过则返回对应阶段修正。

## 10.1 五类校验门

| 校验门 | 检查什么 | 对应阶段 |
|---|---|---|
| Role Boundary Gate | Agent 是否越权、角色漂移 | S5–S8 |
| Evidence Gate | 主张是否有证据支撑 | S2、S6、S8、S10 |
| Conflict Coverage Gate | 核心冲突是否被覆盖 | S1、S7、S8 |
| Minority Retention Gate | 少数意见是否被保留 | S7、S12 |
| Proposal Review Gate | 方案是否通过约束、公共资源和 Universalization 检查 | S10 |

## 10.2 Gate Check 输出

```json
{
  "stage_id": "S7",
  "gate": "Minority Retention Gate",
  "status": "revise",
  "issues": [
    "外圈老年居民代表提出的睡眠影响未进入 Summary Card",
    "环卫经费问题没有进入下一轮必答问题"
  ],
  "required_action": [
    "补录少数意见",
    "将环卫经费问题写入 Round 2 required_questions"
  ]
}
```

---

# 11. Observer Metrics：过程可评估

每轮结束后，Observer 必须生成 Observer Snapshot。

## 11.1 Observer Snapshot 字段

```json
{
  "round_id": 1,
  "speaker_share": {
    "夜市摊贩代表": 0.25,
    "周边居民代表": 0.25,
    "街道办治理人员": 0.25,
    "环卫人员代表": 0.25
  },
  "grounding_rate": 0.83,
  "minority_retention": 0.75,
  "role_boundary_violations": [],
  "unanswered_questions": [
    "额外清扫经费由谁承担？",
    "居民投诉响应机制如何设计？"
  ],
  "anomaly_flags": [
    "部分方案仍未说明资金来源"
  ]
}
```

## 11.2 核心指标

```text
发言公平性：谁说得太多，谁说得太少。
Grounding 率：多少发言引用了证据。
角色保真度：Agent 是否越权。
回应率：是否回应其他 Agent 的质询。
少数意见保留率：少数意见是否进入 Summary 和 Report。
共识度：立场是否逐渐靠近。
极化程度：冲突是否扩大。
假共识警报：是否过早形成空泛共识。
```

---

# 12. 输出报告结构

最终报告不复述全部对话，只输出经过整理的议事结果。

```text
1. 议题背景
2. Agent Pool 与内外圈轮换表
3. 核心冲突矩阵
4. 主要共识
5. 少数意见与未解决问题
6. 方案草案与修正路径
7. Universalization 四问结果
8. 公共资源评估
9. 条件性建议
10. 社会过程状态包
11. 需要真实调研验证的问题
```

## 12.1 社会过程状态包

```text
城市状态：城市指标如何变化。
主体状态：谁让步、谁仍反对、信任如何变化。
制度状态：形成了哪些规则或程序。
经验状态：本轮议事暴露了什么经验和风险。
迁移原则：该治理逻辑能否复制到其他城市背景。
```

---

# 13. 异常处理

| 问题 | 处理 |
|---|---|
| 角色漂移 | Boundary Checker 标记，必要时要求重发 |
| 观点坍缩 | 主持人追问“你仍然不能接受什么？” |
| 假共识 | 要求补充责任主体、资金来源、执行成本 |
| 证据错配 | Evidence Agent / Grounding Judge 标记 |
| 少数意见丢失 | Summary Card 和 Report 必须补录 |
| 强势角色支配 | 下一轮降低其优先级，提高沉默角色优先级 |
| 外圈意见无效 | 要求外圈补充证据或将其标记为待调研意见 |
| 方案审查失败 | 返回 S9 重新修订，最多修订 2 次 |

---

# 14. 最小开发实现

第一版只实现以下内容：

```text
1. Agent Pool 自动生成；
2. 每轮 4 个内圈 Agent；
3. 每轮至少轮换 2 个 Agent；
4. 外圈生成 Observation Card；
5. 每轮生成 Fishbowl Summary Card；
6. 每个阶段输出 artifact_id / stage_id / produced_by；
7. 至少实现 Role Boundary Gate、Evidence Gate、Minority Retention Gate；
8. 报告输出内外圈轮换表、少数意见和未解决问题。
```

暂不强制实现复杂打分模型。可以先使用规则选择：

```text
Round 1 = 直接受益者 + 直接受影响者 + 治理方 + 维护 / 专业方
Round 2 = 保留主要冲突方 1–2 个 + 替换进入外圈观察中优先级最高的角色
Round 3 = 仅在未收敛时启用
```

---

# 15. 一句话总结

SOP v1.2 的核心是：

> 通过 Agent Contract、Stage Contract、Artifact Chain、Validation Gate 和 Observer Metrics，把多智能体发言变成有职责边界、有输入输出、有校验条件、可复现、可追踪、可评估的城市公共议事过程。

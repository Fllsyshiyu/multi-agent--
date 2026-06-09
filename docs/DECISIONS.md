# 多智能体议事厅 Demo — 设计决策日志

## 架构决策

### ADR-001: 手写 Orchestrator 而非使用 AutoGen / CrewAI
- **决策**: 第一版使用手写 Python Orchestrator 控制议事流程
- **原因**: 
  1. Anthropic 的 Building Effective Agents 强调简单可组合模式优于复杂框架
  2. 复杂框架可能遮蔽 prompt 和中间响应，导致调试困难
  3. 作业需要展示对编排逻辑的完整控制
- **后果**: 后续如需更复杂调度，可迁移到框架，但当前架构已证明可行

### ADR-002: 模板发言 + 结构化字段，而非纯 LLM 自由生成
- **决策**: 当前 Demo 使用预写模板发言，但每条发言必须包含结构化字段（speaker, stance, reply_to, evidence_ids, content）
- **原因**: 
  1. 保证 Observer 的量化分析有结构化输入
  2. 模板发言已可演示完整链路，LLM 替换只影响发言生成层
  3. 便于对照实验：模板 vs LLM 发言质量对比
- **后果**: 正式版替换 LLM 时，prompt 必须要求输出相同结构化字段

### ADR-003: 证据检索采用两级匹配（L1 语义 + L2 规则）
- **决策**: 当前 Demo 使用关键词匹配，架构预留了 embedding 检索接口
- **原因**: Demo 阶段证据库小（16 条），关键词足够；正式版 50+ 条需要语义检索
- **后果**: `evidence.py` 的 `retrieve_for_agent` 函数签名已支持替换检索后端

### ADR-004: Observer 作为独立模块，可插拔
- **决策**: Observer 不嵌入 Orchestrator，作为独立后处理步骤
- **原因**: 
  1. 实时 Observer（议事中）和事后 Observer（议事后的深度分析）需要复用
  2. 便于在答辩中展示"可观测性"的模块化设计
- **后果**: Observer 计算全部基于 DeliberationState 快照，可以离线重算

### ADR-005: 三层角色设计（原型 → 实例化 → 证据约束）
- **决策**: 不做固定角色列表，而是角色原型 + 议题实例化 + 证据边界
- **原因**: 体现"可配置、可迁移"的系统设计，而非为单一议题写死角色
- **后果**: Agent Factory 需要 Topic Analysis 的输出作为输入

## 技术选择

| 选择 | 理由 |
|------|------|
| FastAPI | 作业要求 API 化，FastAPI 自带 OpenAPI 文档 |
| 纯 HTML/CSS/JS 前端 | 零依赖，一键打开，适合答辩演示 |
| YAML 配置 | 角色原型需要人类可读可编辑 |
| CSV 证据库 | 便于非技术人员（规划师）用 Excel 编辑 |
| 单文件输出（JSON + MD） | 报告可直接被其他工具消费 |

## 已知限制

1. 模板发言无法体现 LLM 的角色保真度差异 → 正式版替换
2. 证据检索用关键词匹配，长文本可能漏检 → 正式版用 embedding
3. 前端为静态单页，无后端时用内置数据运行

## 下一版计划

- [ ] LLM 发言替换模板发言
- [ ] Embedding 证据检索
- [ ] 议事协议可切换（RoundRobin / Priority / Consensus）
- [ ] 实时 Boundary Checker
- [ ] Langfuse 追踪集成
- [ ] 单智能体 baseline 对照实验

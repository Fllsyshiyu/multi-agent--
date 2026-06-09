# 期中 Demo 展示脚本

## Demo 目标

证明系统不是固定剧本，而是具备“可配置多智能体议事厅”的基本链路：

```text
议题输入 → 议题分析 → 自动生成角色 → 证据匹配 → 多轮议事 → Observer 指标 → 结构化报告
```

## 展示顺序

1. 输入议题：小区门口夜市是否应该保留？
2. 展示系统识别出的冲突维度：生计 vs 休息、活力 vs 秩序、便利 vs 卫生。
3. 展示 Agent Factory 生成的 6 个角色。
4. 展示一轮立场表达，强调每个角色都引用 evidence_id。
5. 展示冲突回应，说明 Orchestrator 让被点名者和弱势群体发言。
6. 展示方案协商，说明系统从“支持/反对”转向“限时、限区、定责、可复评”。
7. 展示 Observer 指标：发言占比、Grounding 率、共识度变化、少数声音。
8. 展示 `outputs/demo_report.md`。

## 老师可能追问

### Q1：这和普通 ChatGPT 角色扮演有什么区别？

普通角色扮演只生成对话；本系统显式包含 Topic Analyzer、Agent Factory、Evidence Retriever、Orchestrator、Observer 和 Report Writer。每条发言保留 evidence_ids，可以评价 grounding 和引用正确率。

### Q2：为什么现在证据是 Demo 证据？

这版目标是跑通端到端工程链路。正式版本会把 `evidence_cards.csv` 替换为真实材料，包括 12345 工单、政府答复、政策文件、案例报道。

### Q3：如何证明多智能体比单智能体好？

设计对照实验：同一议题下，单智能体直接输出报告 vs 多智能体议事后输出报告。比较议题覆盖度、少数意见保留率、观点多样性、可执行建议数量、Grounding 率。

### Q4：bad case 怎么看？

关注角色漂移、观点坍缩、证据错配、强势角色支配、过快达成共识、少数意见没有进入报告。

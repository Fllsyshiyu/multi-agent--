# 多智能体议事厅 Demo：面向社区公共空间治理

这是一个用于课程期中/前期展示的最小可运行 Demo。它展示：

1. Topic Analyzer：识别议题类型、冲突维度、利益相关者。
2. Agent Factory：根据议题生成多类角色。
3. Evidence Retriever：从 evidence_cards.csv 中为角色匹配证据。
4. Orchestrator：按“立场表达 → 冲突回应 → 方案协商”组织多轮发言。
5. Observer：计算发言公平性、Grounding 率、立场方差、共识度。
6. Report Writer：输出结构化议事报告。

> 注意：`data/evidence_cards.csv` 目前是课程原型证据，用来跑通系统链路。正式作业应替换成真实政府政策、12345 工单、领导留言板、人大建议/政协提案答复、法院案例或主流媒体案例。

## 快速运行

不安装前端依赖时，可以直接运行纯 Python Demo：

```bash
python scripts/run_demo.py --topic "小区门口夜市是否应该保留？"
```

输出文件：

```text
outputs/demo_report.md
outputs/demo_transcript.json
outputs/demo_metrics.json
```

## 用 uv 安装并启动 API / UI

```bash
uv sync
make api
make ui
```

API 示例：

```bash
curl -X POST http://127.0.0.1:8000/deliberate \
  -H "Content-Type: application/json" \
  -d '{"topic":"小区门口夜市是否应该保留？"}'
```

## 评测

```bash
make eval
```

输出：

```text
outputs/eval_summary.json
```

当前评测只是 smoke test + 指标产出。正式版本需要扩展为：

- 至少 50 条人工标注样本；
- 对比固定轮转 / 动态调度；
- 对比无 grounding / 有 grounding；
- 同配置重复 5 次统计均值和方差；
- 记录 bad cases。

## 下一步接入真实 LLM

当前发言是模板生成，优点是可复现、无 API 成本。接入 LLM 时建议只替换发言生成器，不改系统架构：

```text
AgentCard + EvidenceCards + DiscussionState
↓
LLM speech generator
↓
BoundaryChecker
↓
Observer
```

务必保留 `evidence_ids`，否则后续无法评估 Grounding 和引用正确率。

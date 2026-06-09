# Demo 开发计划

## 当前版本: v0.2.0

### 已完成
- [x] 议题分析器（Topic Analyzer）
- [x] 冲突结构分析（Conflict Structure Analysis）
- [x] Agent 工厂（Agent Factory）
- [x] 证据检索器（Evidence Retriever）
- [x] 多轮议事编排（Orchestrator）
- [x] Observer 指标体系
- [x] 报告生成器（Report Generator）
- [x] FastAPI 后端
- [x] 可视化前端（含角色动画和发言气泡）
- [x] 评测脚本
- [x] 示例证据库（16 条）
- [x] 角色原型配置

### 进行中
- [ ] 真实证据库扩充（目标 30-50 条）
- [ ] 单智能体 baseline 对照实验

### 计划中
- [ ] LLM 发言替换模板发言
- [ ] 议事协议可切换
- [ ] Boundary Checker 实时检测
- [ ] Langfuse 追踪
- [ ] CI/CD

## 运行方式

### 1. 命令行运行
```bash
cd ma_deliberation_demo
python scripts/run_demo.py --topic "小区门口夜市是否应该保留？"
python evals/run_eval.py
```

### 2. API 服务器
```bash
cd ma_deliberation_demo
pip install -r requirements.txt
python api/main.py
# 访问 http://localhost:8765
```

### 3. 纯前端演示（无需后端）
直接在浏览器中打开 `frontend/index.html`

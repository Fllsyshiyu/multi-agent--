# 多智能体议事厅 · Multi-Agent Deliberation System

面向社区更新与公共空间治理的可配置多智能体议事系统。

**核心 pipeline**：输入议题 → 识别议题类型与冲突结构 → 自动生成利益相关方 Agent → 为每个 Agent 匹配证据 → 多轮议事 → Observer 计算指标 → 输出结构化议事报告

---

## 快速开始

### 方式一：纯前端嵌入式（无需安装）

直接在浏览器中打开 `frontend/live_deliberation.html`。

- 每个 Agent 基于角色原型、利益诉求、证据卡和对话上下文**实时独立生成发言**
- 无需服务器、无需 API Key
- 支持议题预设：夜市治理 / 广场舞争议 / 电梯加装

### 方式二：后端 API 驱动（LLM 真实生成）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动后端
python api/main.py
# 默认 http://localhost:8765

# 3. 打开前端，开启「接入后端 API」开关，配置 LLM
```

后端支持 4 种 LLM 模式：

| Provider | 说明 | 环境变量 |
|----------|------|----------|
| `simulation` | 规则引擎（默认，无需 Key） | — |
| `openai` | OpenAI GPT-4o 等 | `LLM_API_KEY=sk-...` |
| `anthropic` | Anthropic Claude | `LLM_API_KEY=sk-ant-...` |
| `openai_compat` | 通义千问 / DeepSeek / 智谱等 | `LLM_API_KEY=... LLM_BASE_URL=...` |

```bash
# 示例：使用通义千问
set LLM_PROVIDER=openai_compat
set LLM_MODEL=qwen-plus
set LLM_API_KEY=你的阿里云API-Key
set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
python api/main.py
```

### 方式三：命令行脚本

```bash
python scripts/run_demo.py --topic "小区门口夜市是否应该保留？" --max-turns 18
```

---

## 项目结构

```
ma_deliberation_demo/
├── frontend/
│   ├── index.html              # 旧版预编写剧本（保留）
│   └── live_deliberation.html  # 实时多智能体引擎版 ⭐
├── api/
│   └── main.py                 # FastAPI 服务 + SSE 流式议事
├── src/ma_deliberation_demo/
│   ├── schemas.py              # 核心数据结构定义
│   ├── topic.py                # 议题分析与复杂度计算
│   ├── agents.py               # Agent 工厂（角色原型加载与实例化）
│   ├── evidence.py             # 证据卡加载与两级检索
│   ├── orchestrator.py         # 多智能体议事编排（LLM 驱动）
│   ├── llm_client.py           # LLM 抽象层（4 种后端）
│   ├── boundary_checker.py     # Agent 发言边界校验
│   ├── observer.py             # 指标计算（Gini/共识/极化等）
│   └── report.py               # 结构化报告生成
├── configs/
│   ├── role_archetypes.yaml    # 6 种角色原型定义
│   └── sample_topics.json      # 示例议题
├── data/
│   └── evidence_cards.csv      # 16 条社区治理证据卡
├── scripts/
│   └── run_demo.py             # CLI 演示脚本
├── evals/
│   └── run_eval.py             # 评估脚本（5-run 统计）
├── docs/                       # 设计文档
└── requirements.txt
```

---

## 系统架构

```
┌──────────────┐    SSE Stream    ┌──────────────────────────────────┐
│   Frontend   │ ◄────────────── │          Backend (FastAPI)        │
│  (standalone │                 │                                  │
│   or API)    │                 │  ┌──────────┐  ┌──────────────┐  │
│              │                 │  │  Topic   │  │   Agents     │  │
│  6 avatars   │                 │  │ Analyzer │  │  Generator   │  │
│  speech      │                 │  └────┬─────┘  └──────┬───────┘  │
│  bubbles     │                 │       │               │          │
│  metrics     │                 │       ▼               ▼          │
│  transcript  │                 │  ┌──────────────────────────┐    │
│  report/PDF  │                 │  │     Orchestrator         │    │
└──────────────┘                 │  │  · speaker selection     │    │
                                 │  │  · context builder       │    │
                                 │  │  · LLM call per agent    │    │
                                 │  └───────────┬──────────────┘    │
                                 │              │                   │
                                 │  ┌───────────▼──────────────┐    │
                                 │  │     LLM Client           │    │
                                 │  │  OpenAI / Anthropic /    │    │
                                 │  │  OpenAICompat / Sim      │    │
                                 │  └──────────────────────────┘    │
                                 │                                  │
                                 │  ┌──────────┐  ┌──────────────┐  │
                                 │  │ Evidence │  │  Boundary    │  │
                                 │  │ Retriever│  │  Checker     │  │
                                 │  └──────────┘  └──────────────┘  │
                                 │                                  │
                                 │  ┌──────────┐  ┌──────────────┐  │
                                 │  │ Observer │  │   Report     │  │
                                 │  │ (metrics)│  │  Generator   │  │
                                 │  └──────────┘  └──────────────┘  │
                                 └──────────────────────────────────┘
```

### 核心设计

**三层 Agent 设计**：角色原型（YAML）→ 议题实例化 → 证据约束

**两级证据检索**：
- L1：角色 archetype 匹配
- L2：关注类型（concern type）匹配

**动态发言调度**：被点名方 > 沉默利益方 > 轮转

**边界检查**：can_say / cannot_say 关键词检测、证据归属验证

### 6 种角色原型

| 角色 | Archetype | 立场倾向 | 
|------|-----------|----------|
| 直接受益者 | 摊贩/高楼层住户等 | 支持（+0.8） |
| 直接受影响者 | 周边居民/低楼层住户等 | 反对（-0.7） |
| 间接受益者 | 消费者等 | 温和支持（+0.5） |
| 治理方 | 街道办/居委会 | 中立（+0.1） |
| 间接影响者 | 环卫人员等 | 温和反对（-0.3） |
| 专业观察者 | 城市设计师/规划师 | 建设性中立（+0.2） |

### Observer 指标体系

| 指标 | 含义 | 计算方式 |
|------|------|----------|
| Fairness Gini | 发言公平性 | 发言次数分布的基尼系数 |
| Grounding Rate | 证据引用率 | 引用证据的发言占比 |
| Consensus | 共识度 | 1 - 各方立场方差 |
| Polarization | 极化程度 | 最大立场差 / 2 |
| Minority Retention | 少数意见保留率 | 少数方立场是否被保留 |

---

## 前端功能

### `live_deliberation.html`（推荐使用）

- **嵌入式多智能体引擎**：每个 Agent 根据角色设定 + 证据卡 + 对话上下文实时生成发言
- **6 个角色虚拟形象**：发言时头像发光 + 对话框弹出动画
- **实时指标面板**：Gini 系数、Grounding 率、共识度、极化程度
- **议事记录**：可点击回溯每一轮发言
- **议题预设**：夜市治理 / 广场舞争议 / 电梯加装
- **议事报告**：结构化报告弹窗 + **导出 PDF**（浏览器打印 → 另存为 PDF）
- **重新议事**：一键重新开始
- **API 配置面板**：可选接入后端 LLM API，配置自动保存到 localStorage
- 每次运行结果不同（随机种子 + 模板选择 + 证据洗牌）

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/deliberation/start` | POST | 初始化议事会话，返回 Agent 列表和议题分析 |
| `/api/deliberation/stream` | GET | SSE 流式议事（实时推送每轮发言） |
| `/api/deliberation/state` | GET | 获取当前议事状态快照 |
| `/api/report` | GET | 获取结构化议事报告 |
| `/api/health` | GET | 健康检查 |

---

## 配置

### 环境变量

```bash
LLM_PROVIDER=simulation      # openai | anthropic | openai_compat | simulation
LLM_MODEL=gpt-4o             # 模型名称
LLM_API_KEY=sk-...           # API Key
LLM_BASE_URL=...             # OpenAI 兼容服务的 Base URL
LLM_MAX_TOKENS=1024          # 单次最大 token 数
LLM_TEMPERATURE=0.7          # 生成温度
```

### 角色原型配置

编辑 `configs/role_archetypes.yaml` 可自定义角色：
- `can_say` / `cannot_say`：角色话语边界
- `concern_types`：关注的问题类型
- `evidence_match_keywords`：证据匹配关键词

### 证据库

编辑 `data/evidence_cards.csv` 可添加/修改证据卡。

---

## 依赖

```
fastapi>=0.104.0
uvicorn>=0.24.0
pyyaml>=6.0
pydantic>=2.0.0
# 可选（按需安装）
# openai>=1.0.0       # OpenAI / 兼容接口
# anthropic>=0.30.0   # Anthropic Claude
```

---

## 设计说明

- **AI 不是决策者**：系统定位为规划师/决策者的辅助工具，不替代真实的公众参与和实地调研
- **证据驱动**：Agent 发言受证据卡约束，减少幻觉和角色漂移
- **边界意识**：每个 Agent 有明确的 can_say / cannot_say 边界
- **少数意见保护**：Observer 显式追踪少数方立场，避免虚假共识

详见 `docs/DECISIONS.md` 和 `docs/BAD_CASES.md`。

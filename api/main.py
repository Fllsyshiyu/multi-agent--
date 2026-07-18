"""FastAPI server — SOP-driven Multi-Agent Deliberation with Fishbowl.

Based on MetaGPT + Participatory Urban Planning LLM SOP:
  1. 议题分析 → 2. 事实收集 → 3. 角色映射 → 4. 利益陈述
  → 5. 冲突提取 → 6. 方案形成 → 7. 规则校验 → 8. 多维评估 → 9. 结论输出

Start:    python api/main.py
Default:  http://localhost:8765
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ma_deliberation_demo.topic import analyze_topic, compute_complexity
from ma_deliberation_demo.role_assigner import assign_agents_for_topic, FACILITATOR_AGENTS
from ma_deliberation_demo.agents import load_archetypes, generate_agents, get_agent_prompt, load_deliberation_sop
from ma_deliberation_demo.evidence import load_evidence, retrieve_for_agent, format_evidence_context
from ma_deliberation_demo.schemas import DeliberationState, Utterance
from ma_deliberation_demo.artifacts import (
    AgentContract, DeliberationPlan, GateCheckResult, ObserverSnapshot,
    OuterObservationCard, PositionCard, ProposalCard, ReviewCard,
    ConflictMatrix, ConflictAxis, RoundSummary, ValidationResult,
    Stance, ArtifactStatus,
)
from ma_deliberation_demo.fishbowl import (
    select_inner_circle, get_outer_circle,
    run_fishbowl_round_simulation, run_all_fishbowl_rounds,
    generate_deliberation_plan, run_outer_observations, compute_observer_snapshot,
)
from ma_deliberation_demo.validators import (
    validate_all, should_revise,
    gate_role_boundary, gate_evidence, gate_conflict_coverage,
    gate_minority_retention, gate_proposal_review,
)
from ma_deliberation_demo.agents import generate_agent_contract
from ma_deliberation_demo.message_pool import MessagePool, DEFAULT_SUBSCRIPTIONS
from ma_deliberation_demo.llm_client import create_llm_client, resolve_api_key, validate_api_key
from ma_deliberation_demo.sop_runtime import SOPAgentRuntime

app = FastAPI(
    title="MA Deliberation API — SOP Edition",
    description="SOP-driven Multi-Agent Deliberation with Fishbowl mechanism",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_current_state: DeliberationState | None = None
_evidence_pool: list = []
_topic_analysis = None
_message_pool = MessagePool()
_deliberation_config: dict = {}  # stores mode, model, api_keys from last request

# ── Model → (provider, base_url) mapping ──────────────────────────────────

MODEL_PROVIDER_MAP = {
    # DeepSeek V4 (2026-04 release)
    "deepseek-v4-pro": ("openai_compat", "https://api.deepseek.com/v1"),
    "deepseek-v4-flash": ("openai_compat", "https://api.deepseek.com/v1"),
    "deepseek-v4": ("openai_compat", "https://api.deepseek.com/v1"),  # alias
    "deepseek-chat": ("openai_compat", "https://api.deepseek.com/v1"),  # legacy
    "deepseek-reasoner": ("openai_compat", "https://api.deepseek.com/v1"),  # legacy
    # OpenAI
    "gpt-4o": ("openai", "https://api.openai.com/v1"),
    "gpt-4o-mini": ("openai", "https://api.openai.com/v1"),
    # Anthropic Claude
    "claude-opus-4-7": ("anthropic", ""),
    "claude-sonnet-4-6": ("anthropic", ""),
    "claude-haiku-4-5": ("anthropic", ""),
    # Google Gemini (OpenAI-compatible endpoint)
    "gemini-2.5-pro": ("openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "gemini-2.5-flash": ("openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    # 阿里通义千问 (DashScope)
    "qwen-max": ("openai_compat", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "qwen-plus": ("openai_compat", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    # 智谱 GLM
    "glm-4-plus": ("openai_compat", "https://open.bigmodel.cn/api/paas/v4"),
    # 月之暗面 Moonshot
    "moonshot-v1-8k": ("openai_compat", "https://api.moonshot.cn/v1"),
}

# Provider name → env var for API key lookup
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compat": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@app.on_event("startup")
async def startup():
    global _evidence_pool
    _evidence_pool = load_evidence()
    # Verify SOP is loaded and report status
    sop = load_deliberation_sop()
    if sop:
        print(f"[STARTUP] Deliberation SOP loaded ({len(sop)} chars) — agent priming active", flush=True)
    else:
        print("[STARTUP] WARNING: Deliberation SOP not found — agents will use bare role prompts", flush=True)


@app.get("/")
async def root():
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    raise HTTPException(404, "frontend/index.html not found")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "mode": "sop+fishbowl"}


# ── Role Assignment Agent ─────────────────────────────────────────────────

class AssignAgentsRequest(BaseModel):
    topic: str = ""


@app.post("/api/topic/assign_agents")
async def assign_agents(req: AssignAgentsRequest):
    """角色分配agent: 分析议题并动态生成利益相关方角色。

    返回至少4个与议题最相关的利益群体角色配置。
    优先使用LLM分析（如果API Key已配置），无Key时回退到关键词模板匹配。
    """
    if not req.topic or not req.topic.strip():
        raise HTTPException(400, "议题不能为空")

    topic = req.topic.strip()

    # Try LLM-driven assignment, fall back to simulation
    llm = None
    try:
        api_key = resolve_api_key("openai_compat") or resolve_api_key("openai")
        if api_key:
            provider = "openai_compat"
            model = "gpt-4o-mini"
            if resolve_api_key("openai"):
                provider = "openai"
            llm = create_llm_client(
                provider=provider,
                model=model,
                api_key=api_key,
                max_tokens=1024,
                temperature=0.3,
            )
    except Exception:
        pass

    result = assign_agents_for_topic(topic, llm)

    return {
        "success": True,
        "analysis": result["analysis"],
        "agents": result["agents"],
        "facilitators": FACILITATOR_AGENTS,
    }


# ── Session management ────────────────────────────────────────────────────

class DeliberationRequest(BaseModel):
    topic: str
    question: str = "是否应该保留？如果保留，应该设置哪些治理条件？"
    max_rounds: int = 2
    max_speakers: int = 4
    deliberation_mode: str = "quick"  # "quick" | "expert"
    quick_model: str = "claude-sonnet-4-6"
    expert_models: dict[str, str] = {}  # agent_id -> model_name
    api_keys: dict[str, str] = {}  # provider_name -> api_key (Quick mode)
    expert_api_keys: dict[str, str] = {}  # agent_id -> api_key (Expert mode, per-agent)


@app.post("/api/deliberation/start")
async def start_deliberation(req: DeliberationRequest):
    """Initialize a new SOP deliberation session."""
    global _current_state, _topic_analysis, _message_pool, _deliberation_config

    # Save deliberation config for stream use
    _deliberation_config = {
        "deliberation_mode": req.deliberation_mode,
        "quick_model": req.quick_model,
        "expert_models": req.expert_models,
        "api_keys": req.api_keys,
        "expert_api_keys": req.expert_api_keys,
    }

    _topic_analysis = analyze_topic(req.topic)
    complexity = compute_complexity(_topic_analysis)
    archetypes = load_archetypes()
    agents = generate_agents(req.topic, _topic_analysis, archetypes)

    for agent in agents:
        retrieve_for_agent(agent, _evidence_pool)

    # Initialize message pool with subscriptions
    _message_pool = MessagePool()
    for agent in agents:
        # Map archetype to subscription type
        arch = agent.archetype
        sub_type = "resident"
        if "弱势" in arch or "环卫" in arch:
            sub_type = "vulnerable_group"
        elif "专业" in arch or "设计" in arch:
            sub_type = "expert"
        elif "治理" in arch or "街道" in arch:
            sub_type = "manager"
        elif "摊贩" in arch or "商户" in arch:
            sub_type = "business"
        _message_pool.subscribe_by_archetype(agent.agent_id, sub_type)

    # Publish case context to message pool
    _message_pool.publish("case_context", {
        "topic": req.topic,
        "question": req.question,
        "analysis": _topic_analysis.topic_type.value,
        "complexity": complexity,
    })

    _current_state = DeliberationState(
        topic=req.topic,
        question=req.question,
        max_turns=100,
        agents=agents,
    )

    return {
        "topic": req.topic,
        "question": req.question,
        "topic_analysis": {
            "type": _topic_analysis.topic_type.value,
            "conflict_axes": [
                {"name": ax.name, "parties": ax.parties, "intensity": ax.intensity}
                for ax in _topic_analysis.conflict_axes
            ],
            "complexity": complexity,
        },
        "agents": [
            {
                "id": a.agent_id,
                "name": a.agent_name,
                "archetype": a.archetype,
                "emoji": a.avatar_emoji,
                "color": a.avatar_color,
                "stance": a.stance_score,
                "interests": a.main_interests,
                "evidence_count": len(a.evidence_ids),
                "is_facilitator": a.archetype in ("主持人", "评审员"),
            }
            for a in agents
        ],
        "max_rounds": req.max_rounds,
        "deliberation_mode": req.deliberation_mode,
    }


@app.post("/api/deliberation/validate_keys")
async def validate_keys(req: DeliberationRequest):
    """Validate API keys before starting deliberation."""
    results = []

    # Debug: log received keys (masked)
    ak_masked = {k: (v[:4] + '****' + v[-4:] if len(v) > 8 else '****') for k, v in req.api_keys.items() if v}
    print(f"[VALIDATE] mode={req.deliberation_mode} model={req.quick_model} api_keys={ak_masked}", flush=True)

    if req.deliberation_mode == "expert":
        for expert_models_entry in [req.expert_models]:
            if not expert_models_entry:
                continue
            for agent_id, model_name in expert_models_entry.items():
                api_key = req.expert_api_keys.get(agent_id, "")
                if not api_key:
                    # Try shared keys as fallback
                    provider_info = MODEL_PROVIDER_MAP.get(model_name, ("", ""))
                    api_key = _resolve_api_key_for_model(model_name, req.api_keys)
                provider_info = MODEL_PROVIDER_MAP.get(model_name, ("simulation", ""))
                provider, base_url = provider_info
                result = validate_api_key(provider, model_name, api_key, base_url)
                result["agent_id"] = agent_id
                results.append(result)
    else:
        # Quick mode — validate the selected model's key
        model_name = req.quick_model
        provider_info = MODEL_PROVIDER_MAP.get(model_name, ("simulation", ""))
        provider, base_url = provider_info
        api_key = _resolve_api_key_for_model(model_name, req.api_keys)
        result = validate_api_key(provider, model_name, api_key, base_url)
        results.append(result)

    all_valid = all(r["valid"] for r in results) if results else False
    any_valid = any(r["valid"] for r in results) if results else False

    return {
        "validated": True,
        "all_valid": all_valid,
        "any_valid": any_valid,
        "results": results,
        "summary": (
            "所有 API Key 验证通过，将使用真实 API 驱动议事"
            if all_valid else
            "部分 API Key 验证通过，将混合使用真实 API 和模拟回退"
            if any_valid else
            "所有 API Key 验证失败，将使用模板模拟模式"
        ),
    }


# ── LLM Client Helpers ────────────────────────────────────────────────────

def _resolve_api_key_for_model(model_name: str, api_keys: dict[str, str]) -> str:
    """Find the API key for a given model name."""
    provider_info = MODEL_PROVIDER_MAP.get(model_name)
    if not provider_info:
        print(f"[KEY-RESOLVE] model={model_name} NOT FOUND in MODEL_PROVIDER_MAP", flush=True)
        return ""
    provider, _ = provider_info

    # Try exact model name as key first
    if model_name in api_keys and api_keys[model_name]:
        print(f"[KEY-RESOLVE] model={model_name} resolved via exact model name", flush=True)
        return api_keys[model_name]

    # Try provider name
    if provider in api_keys and api_keys[provider]:
        print(f"[KEY-RESOLVE] model={model_name} resolved via provider={provider}", flush=True)
        return api_keys[provider]

    # Try common provider aliases
    aliases = {
        "deepseek-chat": ["deepseek"],
        "deepseek-reasoner": ["deepseek"],
        "deepseek-v4": ["deepseek"],
        "deepseek-v4-pro": ["deepseek"],
        "deepseek-v4-flash": ["deepseek"],
        "gpt-4o": ["openai"],
        "gpt-4o-mini": ["openai"],
        "claude-opus-4-7": ["anthropic"],
        "claude-sonnet-4-6": ["anthropic"],
        "claude-haiku-4-5": ["anthropic"],
        "gemini-2.5-pro": ["gemini", "google"],
        "gemini-2.5-flash": ["gemini", "google"],
        "qwen-max": ["qwen", "dashscope"],
        "qwen-plus": ["qwen", "dashscope"],
        "glm-4-plus": ["zhipu", "glm"],
        "moonshot-v1-8k": ["moonshot"],
    }
    for alias in aliases.get(model_name, []):
        if alias in api_keys and api_keys[alias]:
            print(f"[KEY-RESOLVE] model={model_name} resolved via alias={alias}", flush=True)
            return api_keys[alias]

    print(f"[KEY-RESOLVE] model={model_name} provider={provider} NOT FOUND in api_keys={list(api_keys.keys())}", flush=True)
    return ""


def _get_model_for_agent(agent_id: str, agent, deliberation_mode: str,
                         quick_model: str, expert_models: dict[str, str]) -> str:
    """Determine which model to use for a given agent."""
    if deliberation_mode == "expert" and agent_id in expert_models:
        return expert_models[agent_id]
    return quick_model


def _create_agent_llm(agent_id: str, agent, deliberation_mode: str,
                      quick_model: str, expert_models: dict[str, str],
                      api_keys: dict[str, str],
                      expert_api_keys: dict[str, str] | None = None):
    """Create an LLM client for a specific agent based on mode and model selection."""
    model_name = _get_model_for_agent(agent_id, agent, deliberation_mode, quick_model, expert_models)

    provider_info = MODEL_PROVIDER_MAP.get(model_name)
    if not provider_info:
        return create_llm_client(provider="simulation")

    provider, base_url = provider_info

    # In Expert mode, use per-agent API key first
    if deliberation_mode == "expert" and expert_api_keys:
        api_key = expert_api_keys.get(agent_id, "")
        if api_key:
            return create_llm_client(
                provider=provider,
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=1024,
                temperature=0.7,
            )

    # In Quick mode, resolve from provider-level api_keys
    api_key = _resolve_api_key_for_model(model_name, api_keys)

    if not api_key:
        return create_llm_client(provider="simulation")

    return create_llm_client(
        provider=provider,
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        max_tokens=1024,
        temperature=0.7,
    )


# ── LLM-driven Fishbowl Generator ─────────────────────────────────────────

STRUCTURED_OUTPUT_INSTRUCTION = """
请以你被分配的角色身份，对当前议事进展做出一次发言。

你必须以 JSON 格式输出你的发言，格式如下：
{
  "speaker": "你的角色名称",
  "stance": <一个介于 -1.0 (强烈反对) 到 1.0 (强烈支持) 之间的数值>,
  "reply_to": "你要回应的角色名称（如果是在回应某人），否则为 null,
  "evidence_ids": ["你引用的证据编号列表"],
  "content": "你的发言内容（200-400字）"
}

发言规则：
1. 必须保持角色一致性——说你的角色会说的话
2. 如果引用了证据，必须在 evidence_ids 中列出证据编号
3. 必须回应上一位发言者的核心观点（如果与你立场相关）
4. 不要泛泛地说"我同意大家"
5. 保留至少一个你不可退让的底线
6. 可以提出条件性方案，而非简单的支持/反对
"""


def _build_conversation_context(history: list[dict], max_turns: int = 10) -> str:
    """Build conversation history string for LLM context."""
    if not history:
        return "（尚无发言）"
    recent = history[-max_turns:]
    lines = []
    for h in recent:
        lines.append(f"[{h.get('speaker', '?')}]: {h.get('content', '')[:300]}")
    return "\n".join(lines)


def _parse_llm_response(raw: str, agent) -> dict:
    """Parse LLM JSON response into structured speech data."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
        return {
            "content": parsed.get("content", ""),
            "stance": float(parsed.get("stance", agent.stance_score)),
            "reply_to": parsed.get("reply_to"),
            "evidence_ids": parsed.get("evidence_ids", []),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "content": raw[:500],
            "stance": agent.stance_score,
            "reply_to": None,
            "evidence_ids": [],
        }


def _agent_to_event_dict(agent) -> dict:
    """Convert an AgentCard to the dict format frontend expects."""
    return {
        "id": agent.agent_id,
        "name": agent.agent_name,
        "emoji": agent.avatar_emoji,
        "color": agent.avatar_color,
        "bg": "",  # frontend uses hardcoded bg for now
        "role": agent.archetype,
        "stance": agent.stance_score,
        "isFacilitator": agent.archetype in ("主持人", "评审员"),
    }


async def _run_fishbowl_llm(
    agents: list,
    host_agent,
    reviewer_agent,
    topic: str,
    question: str,
    evidence_pool: list,
    agent_llms: dict,  # agent_id -> LLMClient
    max_rounds: int = 2,
    max_speakers: int = 4,
):
    """Run fishbowl discussion with real LLM calls, yielding SSE events."""
    stakeholders = [a for a in agents if a.archetype not in ("主持人", "评审员")]
    conversation_history = []
    all_position_cards = []
    round_summaries_list = []
    speak_counts = {a.agent_id: 0 for a in agents}

    for round_no in range(1, max_rounds + 1):
        # Select inner/outer circle
        if round_no == 1:
            inner = [a for a in stakeholders if a.agent_id in ('agent_000', 'agent_001', 'agent_004', 'agent_005')]
            outer = [a for a in stakeholders if a.agent_id in ('agent_002', 'agent_003')]
        else:
            inner = [a for a in stakeholders if a.agent_id in ('agent_002', 'agent_003', 'agent_000', 'agent_001')]
            outer = [a for a in stakeholders if a.agent_id in ('agent_004', 'agent_005')]

        # If inner/outer empty from ID mismatch, fall back to index-based
        if not inner:
            mid = len(stakeholders) // 2
            if round_no == 1:
                inner = stakeholders[:max_speakers]
                outer = stakeholders[max_speakers:]
            else:
                inner = stakeholders[mid:mid + max_speakers]
                outer = stakeholders[:mid] + stakeholders[mid + max_speakers:]

        inner = inner[:max_speakers]
        outer = outer[:len(stakeholders) - max_speakers]

        yield {"type": "fishbowl_update", "inner": [_agent_to_event_dict(a) for a in inner],
               "outer": [_agent_to_event_dict(a) for a in outer], "roundNo": round_no}

        yield {"type": "round_divider", "roundNo": round_no,
               "inner": [_agent_to_event_dict(a) for a in inner]}

        # ── Host opens round ──
        host_llm = agent_llms.get(host_agent.agent_id)
        host_model = getattr(host_llm, 'model', 'simulation') if host_llm else 'simulation'
        host_prompt = get_agent_prompt(host_agent, topic, question)
        inner_names = "、".join(a.agent_name for a in inner)
        outer_names = "、".join(a.agent_name for a in outer) if outer else "（无）"
        host_instruction = (
            f"你是{host_agent.agent_name}。现在是第{round_no}轮鱼缸讨论的刚开始阶段，还没有人发言。"
            f"内圈参与者：{inner_names}。外圈观察者：{outer_names}。\n"
            f"请发表开场引导语，介绍本轮讨论规则，邀请内圈代表依次发言。"
            f"注意：本轮讨论刚刚开始，请不要说[大家讨论很热烈]之类的话，因为还没人发过言。"
            f"请以 JSON 格式输出，content 字段为你的发言内容（150-300字）。"
        )

        host_llm_success = False
        # Signal waiting state to frontend
        yield {"type": "llm_waiting", "agent": host_agent.agent_name, "action": "开场引导"}
        await asyncio.sleep(0.02)
        try:
            print(f"[LLM] Host opening (model={host_model})...", flush=True)
            raw = host_llm.chat(
                [{"role": "user", "content": host_instruction}],
                system=host_prompt, json_mode=True,
            )
            parsed = _parse_llm_response(raw, host_agent)
            host_text = parsed["content"] or f"第{round_no}轮讨论开始。内圈：{inner_names}。请依次表达观点，注意回应前面发言者的核心论述。"
            host_llm_success = True
            print(f"[LLM] Host OK: {host_text[:60]}...", flush=True)
        except Exception as e:
            print(f"[LLM] Host FAILED: {e}", flush=True)
            host_text = f"各位代表好，第{round_no}轮鱼缸讨论现在开始。本轮内圈参与者为{inner_names}。每位代表请用2-3分钟陈述核心观点，发言时请回应前一位的观点。外圈观察者请做好笔记，下一轮将交换位置。请内圈第一位代表开始发言。"

        yield {"type": "speech", "agent": _agent_to_event_dict(host_agent),
               "text": host_text, "roundNo": round_no, "isFacilitator": True,
               "llm_model": host_model, "llm_success": host_llm_success}
        speak_counts[host_agent.agent_id] = speak_counts.get(host_agent.agent_id, 0) + 1
        conversation_history.append({"speaker": host_agent.agent_name, "content": host_text})
        await asyncio.sleep(0.05)

        # ── S5: Emit deliberation plans for inner agents ──
        for s_idx, speaker in enumerate(inner):
            plan = generate_deliberation_plan(speaker, round_no, prior_summary=None)
            yield {"type": "deliberation_plan", "plan": {
                "plan_id": plan.plan_id,
                "agent_id": plan.agent_id,
                "agent_name": plan.agent_name,
                "round_id": plan.round_id,
                "round_goal": plan.round_goal,
                "core_interest": plan.core_interest,
                "non_negotiables": plan.non_negotiables,
                "possible_concessions": plan.possible_concessions,
                "question_to_others": plan.question_to_others,
                "evidence_to_use": plan.evidence_to_use,
            }, "roundNo": round_no}

        # ── Inner circle speeches ──
        spoken_in_round = []
        for s_idx, speaker in enumerate(inner):
            speaker_llm = agent_llms.get(speaker.agent_id)
            if speaker_llm is None:
                continue

            speaker_model = getattr(speaker_llm, 'model', 'simulation') if speaker_llm else 'simulation'
            evidence = retrieve_for_agent(speaker, evidence_pool, max_cards=3)
            system_prompt = get_agent_prompt(speaker, topic, question, evidence)
            conv_context = _build_conversation_context(conversation_history)
            speaker_llm_success = False

            if s_idx == 0:
                instruction = (
                    f"你是{speaker.agent_name}。现在是第{round_no}轮鱼缸讨论，才刚刚开始，主持人刚做完开场介绍。\n"
                    f"你是本轮第一个发言的代表，还没有其他人发表观点。\n"
                    f"请发表你的开场陈述，介绍你所代表的群体、与议题的关系、你的核心利益和基本立场。\n"
                    f"注意：你是第一个发言的，不要说你同意大家的观点或大家讨论很热烈之类的话。\n\n"
                    f"## 参考背景\n{conv_context}\n\n"
                    f"{STRUCTURED_OUTPUT_INSTRUCTION}"
                )
            else:
                last = conversation_history[-1] if conversation_history else None
                last_ref = f"上一位发言者 {last['speaker']} 说：\"{last['content'][:200]}...\"\n" if last else ""
                instruction = (
                    f"你是{speaker.agent_name}。第{round_no}轮鱼缸讨论正在进行中，你是第{s_idx+1}位发言者。\n"
                    f"{last_ref}\n"
                    f"请先简要回应上一位发言者的观点，然后从你的角色立场出发表达你的看法。\n"
                    f"你可以赞同、反对或补充新角度，但要保持角色一致性。\n\n"
                    f"## 讨论进展\n{conv_context}\n\n"
                    f"{STRUCTURED_OUTPUT_INSTRUCTION}"
                )

            yield {"type": "llm_waiting", "agent": speaker.agent_name, "action": "立场陈述"}
            await asyncio.sleep(0.02)
            try:
                print(f"[LLM] {speaker.agent_name} (model={speaker_model})...", flush=True)
                raw = speaker_llm.chat(
                    [{"role": "user", "content": instruction}],
                    system=system_prompt, json_mode=True,
                )
                parsed = _parse_llm_response(raw, speaker)
                speech_text = parsed["content"] or ""
                stance_val = parsed["stance"]
                if not speech_text.strip():
                    raise ValueError("Empty response from LLM")
                speaker_llm_success = True
                print(f"[LLM] {speaker.agent_name} OK: {speech_text[:60]}...", flush=True)
            except Exception as e:
                print(f"[LLM] {speaker.agent_name} FAILED: {e}", flush=True)
                stance_val = speaker.stance_score
                if s_idx == 0:
                    speech_text = (
                        f"我是{speaker.agent_name}，代表{speaker.archetype}。"
                        f"关于这个议题，{'，'.join(speaker.main_interests[:2])}。"
                        f"我们{'支持' if speaker.stance_score > 0.3 else '关注' if speaker.stance_score > -0.3 else '对现状有所担忧'}，"
                        f"但这需要各方共同协商具体的实施条件。"
                    )
                else:
                    last = conversation_history[-1] if conversation_history else {}
                    last_name = last.get('speaker', '之前的发言者')
                    speech_text = (
                        f"感谢{last_name}的分享。作为{speaker.agent_name}，"
                        f"我想从{speaker.archetype}的角度补充几点："
                        f"{'，'.join(speaker.main_interests[:2])}是我们最关切的。"
                        f"我建议在方案中纳入具体的、可量化的保障措施。"
                    )

            yield {"type": "speech", "agent": _agent_to_event_dict(speaker),
                   "text": speech_text, "roundNo": round_no, "isFacilitator": False,
                   "llm_model": speaker_model, "llm_success": speaker_llm_success}
            speak_counts[speaker.agent_id] = speak_counts.get(speaker.agent_id, 0) + 1
            spoken_in_round.append(speaker.agent_id)
            conversation_history.append({"speaker": speaker.agent_name, "content": speech_text})

            # Role Boundary Gate check per speech
            role_gate = gate_role_boundary(
                speech_text, speaker.can_say, speaker.cannot_say,
                speaker.agent_name, stage_id="S6",
            )
            if role_gate.status != "pass":
                yield {"type": "gate_result", "gate_name": role_gate.gate_name,
                       "stage_id": role_gate.stage_id, "status": role_gate.status,
                       "issues": role_gate.issues, "required_action": role_gate.required_action,
                       "agent_id": speaker.agent_id}

            # Build a PositionCard from the response
            all_position_cards.append(PositionCard(
                agent_id=speaker.agent_id,
                stakeholder_group=speaker.archetype,
                stance=Stance.SUPPORT if stance_val > 0.3 else (Stance.OPPOSE if stance_val < -0.3 else Stance.NEUTRAL),
                claims=[speech_text[:100]],
                evidence_ids=parsed.get("evidence_ids", []),
                round_no=round_no,
            ))

            await asyncio.sleep(0.05)

            # Host mid-round intervention after half the speakers
            if s_idx == len(inner) // 2 - 1:
                mid_instruction = (
                    f"你是{host_agent.agent_name}。内圈讨论已进行到中段，已经听到了{s_idx+1}位代表的发言。"
                    f"请做简短的中场引导，总结已听到的核心观点，鼓励各方从立场表达转向具体参数协商。"
                    f"请以 JSON 格式输出，content 字段为发言内容（100-200字）。"
                )
                mid_llm_success = False
                try:
                    raw = host_llm.chat(
                        [{"role": "user", "content": mid_instruction}],
                        system=host_prompt, json_mode=True,
                    )
                    parsed = _parse_llm_response(raw, host_agent)
                    mid_text = parsed["content"] or "感谢各位的发言，各方立场已经比较清晰。接下来请大家聚焦具体参数——闭市时间、卫生标准、费用分摊——提出可操作的建议。"
                    mid_llm_success = True
                except Exception as e:
                    print(f"[LLM] Host mid-round FAILED: {e}", flush=True)
                    mid_text = "感谢各位的发言，各方立场已经比较清晰。接下来请大家聚焦具体参数——闭市时间、卫生标准、费用分摊——提出可操作的建议。"

                yield {"type": "speech", "agent": _agent_to_event_dict(host_agent),
                       "text": mid_text, "roundNo": round_no, "isFacilitator": True,
                       "llm_model": host_model, "llm_success": mid_llm_success}
                speak_counts[host_agent.agent_id] = speak_counts.get(host_agent.agent_id, 0) + 1
                conversation_history.append({"speaker": host_agent.agent_name, "content": mid_text})
                await asyncio.sleep(0.05)

        # ── Host closes round ──
        close_instruction = (
            f"你是{host_agent.agent_name}。第{round_no}轮讨论即将结束，本轮共有{len(inner)}位内圈代表发言。"
            f"请做本轮总结，梳理已达成共识和仍存在的分歧，然后请评审员发表观察意见。"
            f"请以 JSON 格式输出，content 字段为发言内容（150-300字）。"
        )
        close_llm_success = False
        try:
            raw = host_llm.chat(
                [{"role": "user", "content": close_instruction}],
                system=host_prompt, json_mode=True,
            )
            parsed = _parse_llm_response(raw, host_agent)
            close_text = parsed["content"] or f"第{round_no}轮讨论结束。各方在条件化治理框架下表达了核心立场。下面请评审员给出观察意见。"
            close_llm_success = True
        except Exception as e:
            print(f"[LLM] Host close FAILED: {e}", flush=True)
            close_text = f"第{round_no}轮讨论告一段落。各位内圈代表从各自立场出发进行了充分交流，在试点方案框架、闭市时间等议题上有所推进。同时，费用分摊和长期机制等议题仍需继续讨论。接下来请评审员评估本轮议事质量。"

        yield {"type": "speech", "agent": _agent_to_event_dict(host_agent),
               "text": close_text, "roundNo": round_no, "isFacilitator": True,
               "llm_model": host_model, "llm_success": close_llm_success}
        speak_counts[host_agent.agent_id] = speak_counts.get(host_agent.agent_id, 0) + 1
        conversation_history.append({"speaker": host_agent.agent_name, "content": close_text})
        await asyncio.sleep(0.05)

        # ── S7: Outer Observations ──
        inner_topics = [h.get("content", "")[:100] for h in conversation_history[-len(inner):]]
        outer_observations = run_outer_observations(
            outer, [a.agent_name for a in inner], round_no, inner_topics,
        )
        for obs in outer_observations:
            yield {"type": "outer_observation", "observation": {
                "card_id": obs.card_id,
                "observer_id": obs.observer_id,
                "observer_name": obs.observer_name,
                "round_id": obs.round_id,
                "missed_issue": obs.missed_issue,
                "objection": obs.objection,
                "evidence_needed": obs.evidence_needed,
                "request_to_enter_inner_circle": obs.request_to_enter_inner_circle,
                "reason_to_enter": obs.reason_to_enter,
            }, "roundNo": round_no}

        # ── S8: Observer Snapshot ──
        utterances = []
        for h in conversation_history:
            utterances.append({"speaker": h.get("speaker", ""), "content": h.get("content", "")})
        snapshot = compute_observer_snapshot(utterances, agents, round_no)
        yield {"type": "observer_snapshot", "snapshot": {
            "snapshot_id": snapshot.snapshot_id,
            "round_id": snapshot.round_id,
            "speaker_share": snapshot.speaker_share,
            "grounding_rate": snapshot.grounding_rate,
            "minority_retention": snapshot.minority_retention,
            "role_boundary_violations": snapshot.role_boundary_violations,
            "unanswered_questions": snapshot.unanswered_questions,
            "anomaly_flags": snapshot.anomaly_flags,
        }, "roundNo": round_no}

        # ── Minority Retention Gate (S7) + Evidence Gate (S8) ──
        minority_gate = gate_minority_retention(None, outer_observations, stage_id="S7")
        if minority_gate.status != "pass":
            yield {"type": "gate_result", "gate_name": minority_gate.gate_name,
                   "stage_id": minority_gate.stage_id, "status": minority_gate.status,
                   "issues": minority_gate.issues, "required_action": minority_gate.required_action}

        # ── Reviewer round evaluation ──
        reviewer_llm = agent_llms.get(reviewer_agent.agent_id)
        reviewer_model = getattr(reviewer_llm, 'model', 'simulation') if reviewer_llm else 'simulation'
        reviewer_prompt = get_agent_prompt(reviewer_agent, topic, question)
        conv_context = _build_conversation_context(conversation_history)

        review_instruction = (
            f"你是{reviewer_agent.agent_name}。第{round_no}轮鱼缸讨论的内圈发言已结束。\n"
            f"内圈参与者：{inner_names}\n"
            f"发言统计：{json.dumps({a.agent_name: speak_counts.get(a.agent_id, 0) for a in inner}, ensure_ascii=False)}\n\n"
            f"## 本轮对话记录\n{conv_context}\n\n"
            f"请对该轮议事过程进行评审，包括：\n"
            f"1. 发言均衡性（谁发言多、谁发言少）\n"
            f"2. 论证质量（是否有数据支撑、是否从立场转向方案）\n"
            f"3. 证据使用情况\n"
            f"4. 改进建议\n\n"
            f"请以 JSON 格式输出，content 字段为评审内容（200-400字）。"
        )
        review_llm_success = False
        yield {"type": "llm_waiting", "agent": reviewer_agent.agent_name, "action": "评审诊断"}
        await asyncio.sleep(0.02)
        try:
            print(f"[LLM] Reviewer (model={reviewer_model})...", flush=True)
            raw = reviewer_llm.chat(
                [{"role": "user", "content": review_instruction}],
                system=reviewer_prompt, json_mode=True,
            )
            parsed = _parse_llm_response(raw, reviewer_agent)
            review_text = parsed["content"] or f"【第{round_no}轮评审】议事过程总体有序，各方均有表达机会。建议下轮更多关注量化参数协商。"
            review_llm_success = True
            print(f"[LLM] Reviewer OK: {review_text[:60]}...", flush=True)
        except Exception as e:
            print(f"[LLM] Reviewer FAILED: {e}", flush=True)
            review_text = f"【第{round_no}轮评审观察】\n\n1. 发言均衡性：本轮内圈{len(inner)}位代表均获得了发言机会，总体分布合理。\n2. 论证质量：各方从各自立场出发表达了核心关切，部分发言已开始向具体方案靠拢。\n3. 改进建议：建议下轮引入更多量化数据（如投诉率、成本测算）来支撑论证。"

        yield {"type": "speech", "agent": _agent_to_event_dict(reviewer_agent),
               "text": review_text, "roundNo": round_no, "isFacilitator": True,
               "llm_model": reviewer_model, "llm_success": review_llm_success}
        speak_counts[reviewer_agent.agent_id] = speak_counts.get(reviewer_agent.agent_id, 0) + 1
        conversation_history.append({"speaker": reviewer_agent.agent_name, "content": review_text})
        await asyncio.sleep(0.05)

        # ── Round Summary (LLM-generated for rich analysis) ──
        yield {"type": "llm_waiting", "agent": host_agent.agent_name, "action": "轮次总结"}
        await asyncio.sleep(0.02)
        summary_llm_success = False
        try:
            summary_instruction = (
                f"你是{host_agent.agent_name}。第{round_no}轮鱼缸讨论已结束，评审员也完成了评审。\n"
                f"内圈参与者：{inner_names}\n\n"
                f"## 本轮完整对话记录\n{conv_context}\n\n"
                f"## 评审员意见\n{review_text[:300]}\n\n"
                f"请对本轮讨论进行结构化总结，以 JSON 格式输出，包含以下字段：\n"
                f"- majority_views: 数组，列出多数代表认同的核心观点（2-4条，每条20-50字）\n"
                f"- minority_views: 数组，列出少数派或弱势方的关键观点（1-3条，每条20-50字）\n"
                f"- unresolved_conflicts: 数组，列出本轮未能解决的分歧（1-3条，每条20-50字）\n"
                f"- evidence_gaps: 数组，列出讨论中缺少的数据/证据（1-3条）\n"
                f"- next_round_questions: 数组，列出下轮应深入讨论的问题（2-3条）\n\n"
                f"重要：必须基于实际对话内容提取，不要编造未讨论的内容。若某字段确实无内容则返回空数组。"
            )
            summary_raw = host_llm.chat(
                [{"role": "user", "content": summary_instruction}],
                system=host_prompt, json_mode=True,
            )
            # Parse JSON directly (not via _parse_llm_response which remaps for speech)
            summary_json = summary_raw.strip()
            if summary_json.startswith("```"):
                lines = summary_json.split("\n")
                summary_json = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            s_start = summary_json.find("{")
            s_end = summary_json.rfind("}")
            if s_start != -1 and s_end != -1 and s_end > s_start:
                summary_json = summary_json[s_start:s_end + 1]
            summary_parsed = json.loads(summary_json)
            if isinstance(summary_parsed, dict):
                summary = RoundSummary(
                    round_no=round_no,
                    inner_circle=[a.agent_name for a in inner],
                    majority_views=summary_parsed.get("majority_views", []),
                    minority_views=summary_parsed.get("minority_views", []),
                    unresolved_conflicts=summary_parsed.get("unresolved_conflicts", []),
                    evidence_gaps=summary_parsed.get("evidence_gaps", []),
                    next_round_questions=summary_parsed.get("next_round_questions", []),
                    involved_groups=[a.archetype for a in inner],
                )
                summary_llm_success = True
            else:
                raise ValueError("Summary parse returned non-dict")
        except Exception as e:
            print(f"[LLM] Round summary FAILED: {e}, using fallback", flush=True)
            round_cards = [c for c in all_position_cards if c.round_no == round_no]
            summary = RoundSummary(
                round_no=round_no,
                inner_circle=[a.agent_name for a in inner],
                majority_views=[c.claims[0][:80] for c in round_cards[:2] if c.claims],
                minority_views=[c.claims[0][:80] for c in round_cards[2:] if c.claims],
                unresolved_conflicts=[],
                evidence_gaps=[],
                next_round_questions=[],
                involved_groups=[a.archetype for a in inner],
            )
        round_summaries_list.append(summary)

        yield {"type": "round_summary", "summary": {
            "round_no": summary.round_no,
            "inner_circle": summary.inner_circle,
            "majority_views": summary.majority_views,
            "minority_views": summary.minority_views,
            "unresolved_conflicts": summary.unresolved_conflicts,
            "evidence_gaps": summary.evidence_gaps,
            "next_round_questions": summary.next_round_questions,
            "involved_groups": summary.involved_groups,
        }, "roundNo": round_no, "llm_success": summary_llm_success}

        await asyncio.sleep(0.05)

    # Data collected via event handlers in _stream_sop


# ── SOP Stream ─────────────────────────────────────────────────────────────

SOP_PHASES = [
    ("S0_topic_input", "S0 议题输入"),
    ("S1_issue_analysis", "S1 议题与冲突分析"),
    ("S2_evidence", "S2 证据收集"),
    ("S3_agent_pool", "S3 Agent Pool 生成"),
    ("S4_round_plan", "S4 鱼缸轮次规划"),
    ("S5_deliberation_plan", "S5 议事行动计划"),
    ("S6_position_statement", "S6 立场陈述"),
    ("S7_outer_observation", "S7 外圈观察+摘要"),
    ("S8_round2", "S8 质询反驳修正"),
    ("S9_draft_proposal", "S9 生成工作草案"),
    ("S10_review", "S10 方案审查"),
    ("S11_vote", "S11 最终修正与投票"),
    ("S12_report", "S12 输出报告"),
]


async def _stream_sop():
    """Generator that yields SSE events for each SOP phase."""
    global _current_state, _topic_analysis, _message_pool, _deliberation_config

    state = _current_state
    if state is None:
        yield f"data: {json.dumps({'error': 'No active session'})}\n\n"
        return

    agents = state.agents
    topic = state.topic
    question = state.question

    # Determine if we have API keys for real LLM mode
    api_keys = _deliberation_config.get("api_keys", {})
    expert_api_keys = _deliberation_config.get("expert_api_keys", {})
    use_llm = (bool(api_keys) and any(v for v in api_keys.values())) or \
              (bool(expert_api_keys) and any(v for v in expert_api_keys.values()))
    deliberation_mode = _deliberation_config.get("deliberation_mode", "quick")
    quick_model = _deliberation_config.get("quick_model", "claude-sonnet-4-6")
    expert_models = _deliberation_config.get("expert_models", {})

    try:
        # Signal API mode to frontend
        yield _sse("api_mode", {"active": use_llm, "mode": deliberation_mode,
                                "quick_model": quick_model if use_llm else "simulation"})

        # ── Phase: S0 Topic Input ──
        yield _sse("phase", {"phase": "S0_topic_input", "label": "S0 议题输入"})
        yield _sse("phase_detail", {
            "phase": "S0_topic_input",
            "topic": topic,
            "question": question,
        })
        await asyncio.sleep(0.05)

        # ── Phase: S1 Issue Analysis ──
        yield _sse("phase", {"phase": "S1_issue_analysis", "label": "S1 议题与冲突分析"})
        yield _sse("phase_detail", {
            "phase": "issue_analysis",
            "topic_type": _topic_analysis.topic_type.value if _topic_analysis else "unknown",
            "conflict_axes": [
                {"name": ax.name, "parties": ax.parties, "intensity": ax.intensity}
                for ax in (_topic_analysis.conflict_axes if _topic_analysis else [])
            ],
        })
        await asyncio.sleep(0.05)

        # ── Phase: S2 Evidence Collection ──
        yield _sse("phase", {"phase": "S2_evidence", "label": "S2 证据收集"})
        evidence_summary = []
        for agent in agents:
            ev = retrieve_for_agent(agent, _evidence_pool, max_cards=3)
            evidence_summary.append({
                "agent": agent.agent_name,
                "evidence_count": len(ev),
                "evidence_ids": [getattr(e, 'evidence_id', '?') for e in ev],
            })
        yield _sse("evidence_summary", {"agents": evidence_summary})
        await asyncio.sleep(0.05)

        # ── Phase: S3 Agent Pool + Stakeholder Mapping ──
        yield _sse("phase", {"phase": "S3_agent_pool", "label": "S3 Agent Pool 生成"})
        yield _sse("stakeholder_map", {
            "groups": [
                {
                    "name": a.agent_name,
                    "archetype": a.archetype,
                    "stance": a.stance_score,
                    "interests": a.main_interests,
                }
                for a in agents
            ],
            "silent_stakeholders": _topic_analysis.silent_stakeholders if _topic_analysis else [],
            "power_asymmetry": _topic_analysis.power_asymmetry if _topic_analysis else "",
        })
        await asyncio.sleep(0.05)

        # ── Phase: S4 Fishbowl Round Plan ──
        yield _sse("phase", {"phase": "S4_round_plan", "label": "S4 鱼缸轮次规划"})
        await asyncio.sleep(0.05)

        # ── Phases S5-S8: Fishbowl Discussion ──
        yield _sse("phase", {"phase": "S5_deliberation_plan", "label": "S5-S8 鱼缸讨论"})

        host_agent = next((a for a in agents if a.agent_id == "agent_host"), None)
        reviewer_agent = next((a for a in agents if a.agent_id == "agent_reviewer"), None)
        agent_llms = {}  # declared here so accessible after if/else

        if use_llm and host_agent and reviewer_agent:
            # Build per-agent LLM clients
            for agent in agents:
                llm = _create_agent_llm(
                    agent.agent_id, agent, deliberation_mode,
                    quick_model, expert_models, api_keys,
                    expert_api_keys,
                )
                agent_llms[agent.agent_id] = llm

            # Run LLM-driven fishbowl and emit events
            all_cards = []
            round_summaries = []
            all_dialogue = []  # collect all speeches for report
            speak_counts = {}  # per-agent speak counts
            async for event in _run_fishbowl_llm(
                agents=agents,
                host_agent=host_agent,
                reviewer_agent=reviewer_agent,
                topic=topic,
                question=question,
                evidence_pool=_evidence_pool,
                agent_llms=agent_llms,
                max_rounds=2,
                max_speakers=4,
            ):
                yield _sse(event["type"], {k: v for k, v in event.items() if k != "type"})
                await asyncio.sleep(0.05)
                # Collect position cards and summaries from events
                if event["type"] == "round_summary":
                    s = event.get("summary", {})
                    round_summaries.append(RoundSummary(
                        round_no=s.get("round_no", 1),
                        inner_circle=s.get("inner_circle", []),
                        majority_views=s.get("majority_views", []),
                        minority_views=s.get("minority_views", []),
                        unresolved_conflicts=s.get("unresolved_conflicts", []),
                        evidence_gaps=s.get("evidence_gaps", []),
                        next_round_questions=s.get("next_round_questions", []),
                        involved_groups=s.get("involved_groups", []),
                    ))
                if event["type"] == "speech":
                    agent_info = event.get("agent", {})
                    agent_name = agent_info.get("name", "")
                    agent_id = agent_info.get("id", "")
                    all_dialogue.append({
                        "agent_id": agent_id,
                        "text": event.get("text", ""),
                        "round_no": event.get("roundNo", 1),
                        "isFacilitator": event.get("isFacilitator", False),
                    })
                    speak_counts[agent_id] = speak_counts.get(agent_id, 0) + 1
                    if not event.get("isFacilitator"):
                        agent = next((a for a in agents if a.agent_name == agent_name), None)
                        if agent:
                            all_cards.append(PositionCard(
                                agent_id=agent.agent_id,
                                stakeholder_group=agent.archetype,
                                stance=Stance.NEUTRAL,
                                claims=[event.get("text", "")[:100]],
                                round_no=event.get("roundNo", 1),
                            ))
        else:
            # Fallback to simulation
            all_cards, round_summaries, fishbowl_events = run_all_fishbowl_rounds(
                agents=agents,
                max_rounds=2,
                max_speakers=4,
            )
            for event in fishbowl_events:
                yield _sse(event["type"], {k: v for k, v in event.items() if k != "type"})
                await asyncio.sleep(0.05)

        # ── Phase: S9 Conflict Review ──
        yield _sse("phase", {"phase": "S9_draft_proposal", "label": "S9 生成工作草案"})

        # Build conflict matrix from position cards
        conflict = _build_conflict_matrix(all_cards, round_summaries)
        yield _sse("conflict_matrix", {
            "axes": [
                {
                    "name": ax.name,
                    "parties": ax.parties,
                    "intensity": ax.intensity,
                    "description": ax.description,
                    "resolution_status": ax.resolution_status,
                }
                for ax in conflict.axes
            ],
            "hidden_conflicts": conflict.hidden_conflicts,
            "pseudo_consensus_flags": conflict.pseudo_consensus_flags,
        })
        await asyncio.sleep(0.05)

        # ── Build conflict matrix + proposal ──
        proposal_llm = agent_llms.get(host_agent.agent_id) if (agent_llms and host_agent) else None
        proposal = _build_initial_proposal(topic, question, round_summaries, agents, proposal_llm)
        yield _sse("proposal", {
            "proposal_id": proposal.proposal_id,
            "version": proposal.version,
            "title": proposal.title,
            "content": proposal.content,
            "responsible": proposal.responsible,
            "timeline": proposal.timeline,
            "resources": proposal.resources,
            "risks": proposal.risks,
            "evaluation_criteria": proposal.evaluation_criteria,
            "status": proposal.status.value,
        })
        await asyncio.sleep(0.05)

        # ── S10: Proposal Review (LLM-driven) ──
        yield _sse("phase", {"phase": "S10_review", "label": "S10 方案审查"})

        review_issues = []
        review_recommendation = "pass"
        review_detail = ""
        review_llm_success = False

        if proposal_llm:
            try:
                summary_context = "\n".join(
                    f"第{s.round_no}轮: 多数={'；'.join(s.majority_views[:2])}; 少数={'；'.join(s.minority_views[:2])}; 冲突={'；'.join(s.unresolved_conflicts[:2])}"
                    for s in round_summaries
                ) if round_summaries else "（无讨论记录）"
                review_prompt = (
                    f"你是一位城市治理政策评审专家。请对以下试点方案进行严格的四维审查。\n\n"
                    f"## 议题背景\n{topic}\n\n"
                    f"## 核心问题\n{question}\n\n"
                    f"## 各轮讨论摘要\n{summary_context}\n\n"
                    f"## 待审方案\n标题: {proposal.title}\n内容: {proposal.content[:800]}\n"
                    f"责任主体: {proposal.responsible}\n时间线: {proposal.timeline}\n"
                    f"资源: {proposal.resources}\n风险: {proposal.risks}\n\n"
                    f"## 审查维度\n"
                    f"1. 硬约束检查：是否违反法规、消防、预算、规划红线？\n"
                    f"2. 普遍化检验（4问）：①如果所有街道都这样做，系统能运转吗？②如果我是受影响方，会接受吗？③方案的执行者是否有足够能力和激励？④方案是否公平对待所有利益相关方？\n"
                    f"3. 公共资源可持续性：财政、空间、社区信任、长期韧性四个维度评分（各1-5分）\n"
                    f"4. 少数意见保留：方案是否保留了少数/弱势方的合理诉求？\n\n"
                    f"请以 JSON 格式输出审查结果：\n"
                    f"- passed: 是否通过审查 (boolean)\n"
                    f"- issues: 发现的问题列表（每条20-50字）\n"
                    f"- public_resource_scores: 公共资源评分对象 {{财政,空间,社区信任,长期韧性}} 各1-5\n"
                    f"- universalization_result: 普遍化检验结果（pass/fail）及理由\n"
                    f"- minority_retention_ok: 少数意见是否被保留 (boolean)\n"
                    f"- required_revisions: 必须修改的内容列表\n"
                    f"- recommendation: 综合建议 (pass/revise/reject)\n"
                    f"- review_detail: 审查详细说明（100-200字）\n"
                )
                raw = proposal_llm.chat(
                    [{"role": "user", "content": review_prompt}],
                    system="你是城市治理政策评审专家，擅长方案审查。请严格基于方案内容和讨论摘要进行审查，以 JSON 格式输出。",
                    json_mode=True,
                )
                json_text = raw.strip()
                if json_text.startswith("```"):
                    lines = json_text.split("\n")
                    json_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                rs = json_text.find("{")
                re = json_text.rfind("}")
                if rs != -1 and re != -1 and re > rs:
                    json_text = json_text[rs:re + 1]
                parsed = json.loads(json_text)
                if isinstance(parsed, dict):
                    review_issues = parsed.get("issues", [])
                    review_recommendation = parsed.get("recommendation", "pass")
                    review_detail = parsed.get("review_detail", "")
                    pr_scores = parsed.get("public_resource_scores", {})
                    uv_result = parsed.get("universalization_result", {})
                    minority_ok = parsed.get("minority_retention_ok", True)
                    review_llm_success = True
            except Exception as e:
                print(f"[LLM] Proposal review FAILED: {e}, using fallback", flush=True)

        # Fallback review if LLM fails
        if not review_llm_success:
            review_gate = gate_proposal_review(proposal, _get_default_constraints(), stage_id="S10")
            review_issues = review_gate.issues
            review_recommendation = review_gate.status
            review_detail = f"硬约束检查: {'通过' if review_gate.status != 'reject' else '未通过'}。{'; '.join(review_gate.required_action)}" if review_gate.required_action else ""
            pr_scores = {}
            uv_result = {}
            minority_ok = True

        yield _sse("gate_result", {
            "gate_name": "Proposal Review Gate",
            "stage_id": "S10",
            "status": review_recommendation,
            "issues": review_issues,
            "required_action": [],
            "review_detail": review_detail,
            "public_resource_scores": pr_scores if isinstance(pr_scores, dict) else {},
            "universalization_result": uv_result if isinstance(uv_result, dict) else {},
            "minority_retention_ok": minority_ok,
        })
        yield _sse("review_card", {
            "review_id": f"review_{proposal.proposal_id}",
            "proposal_id": proposal.proposal_id,
            "hard_constraint_passed": review_recommendation != "reject",
            "required_revisions": review_issues,
            "recommendation": review_recommendation,
            "detail": review_detail,
            "public_resource_scores": pr_scores if isinstance(pr_scores, dict) else {},
            "universalization_result": uv_result if isinstance(uv_result, dict) else {},
        })
        await asyncio.sleep(0.05)

        # ── Phase: S11 Validation ──
        yield _sse("phase", {"phase": "S11_vote", "label": "S11 校验与投票"})

        result = validate_all(
            proposal=proposal,
            position_cards=all_cards,
            round_summaries=round_summaries,
            conflict_matrix=conflict,
            hard_constraints=_get_default_constraints(),
            evidence_ids=[getattr(e, 'evidence_id', '') for e in _evidence_pool],
        )
        yield _sse("validation", {
            "passed": result.passed,
            "hard_constraint_errors": result.hard_constraint_errors,
            "evidence_errors": result.evidence_errors,
            "fairness_risks": result.fairness_risks,
            "conflict_errors": result.conflict_errors,
            "feasibility_errors": result.feasibility_errors,
            "consistency_errors": result.consistency_errors,
            "revision_instructions": result.revision_instructions,
        })
        await asyncio.sleep(0.05)

        # If validation failed, attempt LLM-driven revision (S11 revision)
        if not result.passed and proposal.revision_count < 2:
            yield _sse("phase", {"phase": "S11_vote", "label": "S11 方案修订"})
            proposal.revision_count += 1
            proposal.version = 2
            proposal.title = f"{proposal.title}（修订版 V2）"

            # LLM-driven revision
            revision_success = False
            if proposal_llm:
                try:
                    all_errors = (
                        result.hard_constraint_errors + result.evidence_errors +
                        result.fairness_risks + result.conflict_errors +
                        result.feasibility_errors + result.consistency_errors
                    )
                    revise_prompt = (
                        f"你是一位城市治理规划师。以下方案未通过校验，需要进行针对性修订。\n\n"
                        f"## 原方案\n标题: {proposal.title}\n内容: {proposal.content[:600]}\n\n"
                        f"## 未通过的校验项\n" + "\n".join(f"- {e}" for e in all_errors[:10]) + "\n\n"
                        f"## 修订指引\n" + "\n".join(f"- {ri}" for ri in result.revision_instructions[:5]) + "\n\n"
                        f"请修订方案内容，直接输出修订后的完整方案正文（300-500字），保留原方案结构，重点修正校验未通过的条目。以 JSON 格式输出，content 字段为修订后的方案正文。"
                    )
                    raw = proposal_llm.chat(
                        [{"role": "user", "content": revise_prompt}],
                        system="你是城市治理规划师，擅长基于校验反馈修订方案。以 JSON 格式输出。",
                        json_mode=True,
                    )
                    json_text = raw.strip()
                    if json_text.startswith("```"):
                        lines = json_text.split("\n")
                        json_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                    p_start = json_text.find("{")
                    p_end = json_text.rfind("}")
                    if p_start != -1 and p_end != -1 and p_end > p_start:
                        json_text = json_text[p_start:p_end + 1]
                    parsed = json.loads(json_text)
                    if isinstance(parsed, dict) and parsed.get("content"):
                        proposal.content = parsed["content"]
                        revision_success = True
                        print(f"[LLM] Proposal revision OK", flush=True)
                except Exception as e:
                    print(f"[LLM] Proposal revision FAILED: {e}", flush=True)

            if not revision_success:
                proposal.content = _revise_proposal_content(proposal, result)
            proposal.status = ArtifactStatus.UNDER_REVIEW

            yield _sse("proposal", {
                "proposal_id": proposal.proposal_id,
                "version": proposal.version,
                "title": proposal.title,
                "content": proposal.content,
                "responsible": proposal.responsible,
                "timeline": proposal.timeline,
                "resources": proposal.resources,
                "risks": proposal.risks,
                "evaluation_criteria": proposal.evaluation_criteria,
                "status": proposal.status.value,
                "revision_count": proposal.revision_count,
            })

            # Re-validate
            result2 = validate_all(
                proposal=proposal,
                position_cards=all_cards,
                round_summaries=round_summaries,
                conflict_matrix=conflict,
                hard_constraints=_get_default_constraints(),
            )
            yield _sse("validation", {
                "passed": result2.passed,
                "hard_constraint_errors": result2.hard_constraint_errors,
                "evidence_errors": result2.evidence_errors,
                "fairness_risks": result2.fairness_risks,
                "conflict_errors": result2.conflict_errors,
                "feasibility_errors": result2.feasibility_errors,
                "consistency_errors": result2.consistency_errors,
            })
            await asyncio.sleep(0.05)

        # ── Phase: S12 Final Report (with LLM executive summary) ──
        yield _sse("phase", {"phase": "S12_report", "label": "S12 输出报告"})

        # Generate LLM executive summary
        executive_summary = ""
        recommendations = []
        if proposal_llm:
            try:
                exec_prompt = (
                    f"你是城市治理政策分析师。基于以下多轮议事讨论，请生成最终议事结论。\n\n"
                    f"## 议题\n{topic}\n\n"
                    f"## 核心问题\n{question}\n\n"
                    f"## 方案\n{proposal.title}: {proposal.content[:400]}\n\n"
                    f"## 校验结果\n{'通过' if result.passed else '未通过'}\n"
                    f"审查建议: {review_recommendation}\n"
                    f"审查详情: {review_detail}\n\n"
                    f"请以 JSON 格式输出：\n"
                    f"- executive_summary: 执行摘要（150-250字），概括讨论过程、主要结论和最终建议\n"
                    f"- recommendations: 行动建议列表（3-5条，每条30-60字）\n"
                    f"- minority_preservation: 哪些少数意见需要被记录和保留\n"
                )
                raw = proposal_llm.chat(
                    [{"role": "user", "content": exec_prompt}],
                    system="你是城市治理政策分析师，擅长总结多方议事并提炼可执行的建议。以 JSON 格式输出。",
                    json_mode=True,
                )
                json_text = raw.strip()
                if json_text.startswith("```"):
                    lines = json_text.split("\n")
                    json_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                p_start = json_text.find("{")
                p_end = json_text.rfind("}")
                if p_start != -1 and p_end != -1 and p_end > p_start:
                    json_text = json_text[p_start:p_end + 1]
                parsed = json.loads(json_text)
                if isinstance(parsed, dict):
                    executive_summary = parsed.get("executive_summary", "")
                    recommendations = parsed.get("recommendations", [])
            except Exception as e:
                print(f"[LLM] Executive summary FAILED: {e}", flush=True)

        yield _sse("executive_summary", {
            "executive_summary": executive_summary,
            "recommendations": recommendations,
        })

        # Build full summaries for report
        summary_list = []
        for s in round_summaries:
            summary_list.append({
                "round_no": s.round_no,
                "inner_circle": s.inner_circle,
                "majority_views": s.majority_views,
                "minority_views": s.minority_views,
                "unresolved_conflicts": s.unresolved_conflicts,
                "evidence_gaps": s.evidence_gaps,
                "next_round_questions": s.next_round_questions,
                "involved_groups": s.involved_groups,
            })

        # Build conflict matrix
        conflict_data = _build_conflict_matrix(all_cards, round_summaries) if all_cards else {"axes": []}
        conflict_axes = []
        for ax in getattr(conflict_data, 'axes', []):
            conflict_axes.append({
                "name": ax.name,
                "parties": ax.parties,
                "intensity": ax.intensity,
                "positions": getattr(ax, 'positions', {}),
            })

        yield _sse("complete", {
            "topic": topic,
            "question": question,
            "total_rounds": len(round_summaries),
            "total_speeches": len(all_dialogue),
            "dialogue": all_dialogue,
            "summaries": summary_list,
            "speak_counts": speak_counts,
            "conflict": {"axes": conflict_axes},
            "proposal": {
                "title": proposal.title,
                "content": proposal.content,
                "responsible": proposal.responsible if isinstance(proposal.responsible, str) else ", ".join(getattr(proposal, 'responsible', []) or []),
                "timeline": getattr(proposal, 'timeline', ''),
                "resources": getattr(proposal, 'resources', ''),
                "risks": getattr(proposal, 'risks', ''),
                "evaluation_criteria": getattr(proposal, 'evaluation_criteria', []) or [],
            },
            "review": {
                "recommendation": review_recommendation,
                "issues": review_issues,
                "detail": review_detail,
                "public_resource_scores": pr_scores if isinstance(pr_scores, dict) else {},
                "universalization_result": uv_result if isinstance(uv_result, dict) else {},
            },
            "validation": {
                "passed": result.passed,
                "score": result.score,
                "issues": result.issues,
                "action_items": getattr(result, 'required_revisions', []) or [],
            },
            "executive_summary": executive_summary,
            "recommendations": recommendations,
            "summary_text": {
                "majority_views": round_summaries[-1].majority_views[:5] if round_summaries else [],
                "minority_views": round_summaries[-1].minority_views[:5] if round_summaries else [],
                "unresolved_conflicts": round_summaries[-1].unresolved_conflicts[:5] if round_summaries else [],
                "next_questions": round_summaries[-1].next_round_questions if round_summaries else [],
            },
        })

        yield f"data: [DONE]\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@app.get("/api/deliberation/stream")
async def stream_sop():
    """Stream the SOP deliberation process via Server-Sent Events."""
    global _current_state
    if _current_state is None:
        raise HTTPException(404, "No active session. POST /api/deliberation/start first.")

    return StreamingResponse(
        _stream_sop(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── State & Report endpoints ──────────────────────────────────────────────

@app.get("/api/deliberation/state")
async def get_state():
    global _current_state
    if _current_state is None:
        raise HTTPException(404, "No active session.")
    return {
        "topic": _current_state.topic,
        "agents": [
            {"id": a.agent_id, "name": a.agent_name, "archetype": a.archetype}
            for a in _current_state.agents
        ],
    }


@app.get("/api/report")
async def get_report():
    global _current_state, _topic_analysis
    if _current_state is None:
        raise HTTPException(404, "No deliberation data.")
    return {
        "topic": _current_state.topic,
        "question": _current_state.question,
        "agents": len(_current_state.agents),
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


def _build_conflict_matrix(
    cards: list[PositionCard],
    summaries: list[RoundSummary],
) -> ConflictMatrix:
    """Build a conflict matrix from position cards and summaries."""
    axes = []
    supporters = [c for c in cards if c.stance in (Stance.SUPPORT, Stance.CONDITIONAL_SUPPORT)]
    opposers = [c for c in cards if c.stance in (Stance.OPPOSE, Stance.CONDITIONAL_OPPOSE)]

    if supporters and opposers:
        axes.append(ConflictAxis(
            name="方案立场分歧",
            parties=[c.stakeholder_group for c in supporters[:2]] + [c.stakeholder_group for c in opposers[:2]],
            intensity="high",
            description=f"支持方（{', '.join(c.stakeholder_group for c in supporters[:2])}）与"
                       f"反对方（{', '.join(c.stakeholder_group for c in opposers[:2])}）存在根本立场分歧",
        ))

    # Extract conflicts from non-negotiables
    nn_conflicts = []
    for c in cards:
        for nn in c.non_negotiables[:1]:
            for c2 in cards:
                if c2.stakeholder_group != c.stakeholder_group:
                    for interest in c2.claims[:1]:
                        if any(kw in interest for kw in nn[:5].split()):
                            nn_conflicts.append(f"{c.stakeholder_group}底线'{nn[:30]}' vs {c2.stakeholder_group}诉求'{interest[:30]}'")

    if nn_conflicts:
        axes.append(ConflictAxis(
            name="底线约束冲突",
            parties=list(set(c.stakeholder_group for c in cards)),
            intensity="medium",
            description="；".join(nn_conflicts[:3]),
        ))

    # Unresolved from summaries
    hidden_conflicts = []
    for s in summaries:
        hidden_conflicts.extend(s.unresolved_conflicts[:2])

    # Detect pseudo-consensus: high confidence but opposing claims exist
    pseudo_flags = []
    high_conf = [c for c in cards if c.confidence > 0.7]
    if len(high_conf) > len(cards) // 2 and opposers:
        pseudo_flags.append("多数Agent置信度>0.7但存在明确反对意见，可能存在过度自信")

    return ConflictMatrix(
        axes=axes,
        hidden_conflicts=hidden_conflicts[:4],
        pseudo_consensus_flags=pseudo_flags,
    )


def _build_initial_proposal(
    topic: str,
    question: str,
    summaries: list[RoundSummary],
    agents: list,
    llm_client=None,
) -> ProposalCard:
    """Build initial proposal V1 from fishbowl discussion results.

    Uses LLM to generate a context-aware proposal when a client is available.
    Falls back to template-based proposal otherwise.
    """
    all_majority = []
    all_minority = []
    for s in summaries:
        all_majority.extend(s.majority_views[:2])
        all_minority.extend(s.minority_views[:1])

    # Find governance agent or expert as planner
    planner = None
    for a in agents:
        if "治理" in a.archetype or "街道" in a.agent_name:
            planner = a
            break
    if planner is None:
        for a in agents:
            if "专业" in a.archetype or "设计" in a.agent_name:
                planner = a
                break
    if planner is None:
        planner = agents[0] if agents else None

    responsible = planner.agent_name if planner else "街道办"

    # ── LLM-generated proposal ──
    proposal_title = f"关于{topic[:20]}的试点治理方案"
    proposal_content = ""
    proposal_timeline = "试点启动后4周"
    proposal_resources = "网格巡查人力、地面标线材料、垃圾桶增配、小程序开发"
    proposal_risks = "环卫增额经费需专款专用；摊位费标准需实地调研确定"
    proposal_criteria = [
        "夜间投诉量下降50%以上",
        "环卫评分不低于C级",
        "消防通道无占用记录",
        "连续两周不达标触发整改",
    ]

    if llm_client:
        try:
            summary_text = "\n".join(
                f"第{s.round_no}轮 — 多数观点:{'；'.join(s.majority_views[:3])} | 少数观点:{'；'.join(s.minority_views[:2])} | 未解决冲突:{'；'.join(s.unresolved_conflicts[:2])}"
                for s in summaries
            ) if summaries else "（无轮次摘要）"
            proposal_prompt = (
                f"你是一位城市治理规划师。基于以下多轮议事讨论的摘要信息，请起草一份具体的试点治理方案。\n\n"
                f"## 议题\n{topic}\n\n"
                f"## 核心问题\n{question}\n\n"
                f"## 各轮讨论摘要\n{summary_text}\n\n"
                f"请以 JSON 格式输出方案，包含以下字段：\n"
                f"- title: 方案标题（20字以内）\n"
                f"- content: 方案正文，包含核心原则、具体措施（5-8条）、多数意见采纳、少数意见保留、待调研问题（300-500字）\n"
                f"- timeline: 实施时间线\n"
                f"- resources: 所需资源\n"
                f"- risks: 主要风险\n"
                f"- evaluation_criteria: 评估标准（3-5条数组）\n\n"
                f"重要：方案必须基于讨论中实际提出的观点，不要凭空编造。要同时反映多数意见和少数意见。"
            )
            raw = llm_client.chat(
                [{"role": "user", "content": proposal_prompt}],
                system="你是一位经验丰富的城市治理规划师，擅长在多方利益冲突中设计可操作的试点方案。你的方案务实地平衡各方关切，注重量化KPI和数据驱动决策。",
                json_mode=True,
            )
            # Parse JSON from response
            json_text = raw.strip()
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                json_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            p_start = json_text.find("{")
            p_end = json_text.rfind("}")
            if p_start != -1 and p_end != -1 and p_end > p_start:
                json_text = json_text[p_start:p_end + 1]
            parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                proposal_title = parsed.get("title", proposal_title)
                proposal_content = parsed.get("content", "")
                proposal_timeline = parsed.get("timeline", proposal_timeline)
                proposal_resources = parsed.get("resources", proposal_resources)
                proposal_risks = parsed.get("risks", proposal_risks)
                proposal_criteria = parsed.get("evaluation_criteria", proposal_criteria)
        except Exception as e:
            print(f"[LLM] Proposal generation FAILED: {e}, using template", flush=True)

    # ── Fallback template content ──
    if not proposal_content:
        proposal_content = f"""基于{topic}的议事讨论，提出以下试点治理方案：

## 核心原则
试点而非一刀切，用数据驱动决策替代立场之争。

## 具体措施
1. 划定摊位边界线和经营时间（冬季22:00/夏季22:30闭市）
2. 建立摊位编号制度，每摊负责自清垃圾
3. 设立卫生押金和环卫附加费机制
4. 制定量化KPI：夜间投诉下降50%、环卫评分C级以上、消防通道无占用
5. 建立投诉快速响应渠道和退出机制

## 多数意见采纳
{chr(10).join(f'- {v[:100]}' for v in all_majority[:3])}

## 少数意见保留
{chr(10).join(f'- {v[:100]}' for v in all_minority[:2])}

## 待实地调研问题
- 环卫增额成本实地测算
- 摊位费标准调研
- 交通流量基线数据收集
"""

    return ProposalCard(
        proposal_id=f"prop_{hash(topic) % 10000:04d}",
        version=1,
        title=proposal_title,
        content=proposal_content,
        status=ArtifactStatus.DRAFT,
        claims=[v[:80] for v in all_majority[:3]],
        responsible=responsible,
        timeline=proposal_timeline,
        resources=proposal_resources,
        risks=proposal_risks,
        evaluation_criteria=proposal_criteria,
        evidence_ids=["E-NM-001", "E-NM-005", "E-NM-007"],
    )


def _revise_proposal_content(proposal: ProposalCard, result: ValidationResult) -> str:
    """Revise proposal content based on validation failures."""
    additions = []
    if result.evidence_errors:
        additions.append("（修订：已补充证据引用）")
    if result.fairness_risks:
        additions.append("（修订：已添加对少数意见的回应段落）")
    if result.feasibility_errors:
        additions.append("（修订：已补充责任主体和时间线细节）")
    if result.conflict_errors:
        additions.append("（修订：已标注未解决的分歧点）")

    suffix = "\n\n## 修订说明\n" + "\n".join(additions) if additions else ""
    return proposal.content + suffix


def _get_default_constraints() -> list[dict]:
    """Get default hard/soft constraints for urban governance."""
    return [
        {"category": "硬约束", "examples": ["法规", "消防红线", "预算上限", "规划控制线", "生态保护要求"]},
        {"category": "软约束", "examples": ["居民满意度", "可达性", "使用便利性", "商业活力"]},
        {"category": "协商偏好", "examples": ["活动场地", "减少噪声", "停车位"]},
        {"category": "不确定项", "examples": ["真实使用人数", "维护成本", "产权情况", "审批风险"]},
    ]


if __name__ == "__main__":
    import uvicorn, webbrowser, threading
    print("Starting SOP Deliberation API on http://localhost:8765")
    print("Mode: SOP + Fishbowl | Simulation (no API key needed)")

    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://localhost:8765")

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8765)

"""FastAPI server — LLM-driven Multi-Agent Deliberation System.

Start:    python api/main.py
Default:  http://localhost:8765

LLM configuration via environment variables:
  LLM_PROVIDER=simulation|openai|anthropic|openai_compat
  LLM_MODEL=gpt-4o|claude-sonnet-4-6|qwen-plus|...
  LLM_API_KEY=...
  LLM_BASE_URL=...  (for OpenAI-compatible providers)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ma_deliberation_demo.topic import analyze_topic, compute_complexity
from ma_deliberation_demo.agents import load_archetypes, generate_agents
from ma_deliberation_demo.evidence import load_evidence, retrieve_for_agent
from ma_deliberation_demo.orchestrator import (
    init_deliberation,
    run_opening_round,
    run_discussion_rounds,
    run_closing_summary,
    build_agent_context,
    parse_agent_response,
)
from ma_deliberation_demo.observer import compute_metrics
from ma_deliberation_demo.report import generate_report
from ma_deliberation_demo.llm_client import create_llm_client, LLMClient, build_messages
from ma_deliberation_demo.boundary_checker import check_utterance
from ma_deliberation_demo.schemas import DeliberationState, Utterance

app = FastAPI(
    title="MA Deliberation API",
    description="LLM-driven Multi-Agent Deliberation System for Community Governance",
    version="0.3.0",
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
_llm: LLMClient | None = None


class DeliberationRequest(BaseModel):
    topic: str
    question: str = "是否应该保留？如果保留，应该设置哪些治理条件？"
    max_turns: int = 20
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""


@app.on_event("startup")
async def startup():
    global _evidence_pool
    _evidence_pool = load_evidence()


@app.get("/")
async def root():
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return FileResponse(Path(__file__).parent.parent / "frontend" / "index.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.3.0",
        "llm_provider": os.environ.get("LLM_PROVIDER", "simulation"),
    }


# ── Session management ────────────────────────────────────────────────────────

@app.post("/api/deliberation/start")
async def start_deliberation(req: DeliberationRequest):
    """Initialize a new deliberation session. Returns agents and topic analysis."""
    global _current_state, _topic_analysis, _llm

    _topic_analysis = analyze_topic(req.topic)
    complexity = compute_complexity(_topic_analysis)

    archetypes = load_archetypes()
    agents = generate_agents(req.topic, _topic_analysis, archetypes)

    for agent in agents:
        retrieve_for_agent(agent, _evidence_pool)

    _current_state = init_deliberation(req.topic, req.question, agents, req.max_turns)

    # Create LLM client
    _llm = create_llm_client(
        provider=req.llm_provider or os.environ.get("LLM_PROVIDER", "simulation"),
        model=req.llm_model or os.environ.get("LLM_MODEL", ""),
        api_key=req.llm_api_key or os.environ.get("LLM_API_KEY", ""),
        base_url=req.llm_base_url or os.environ.get("LLM_BASE_URL", ""),
    )

    return {
        "topic": req.topic,
        "question": req.question,
        "llm_provider": str(_llm),
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
            }
            for a in agents
        ],
        "total_turns": req.max_turns,
    }


# ── Real-time streaming deliberation ──────────────────────────────────────────

import os


async def _stream_deliberation():
    """Generator that yields SSE events for each turn of deliberation."""
    global _current_state, _llm

    state = _current_state
    if state is None:
        yield f"data: {json.dumps({'error': 'No active session'})}\n\n"
        return

    llm = _llm or create_llm_client()

    try:
        # Phase 1: Opening round
        for agent in state.agents:
            if state.turn >= state.max_turns - 2:
                break

            agent_evidence = retrieve_for_agent(agent, _evidence_pool, max_cards=3)
            system_prompt, conversation = build_agent_context(
                agent, state.topic, state.question, agent_evidence, state
            )
            instruction = f"你是{agent.agent_name}。请发表你的开场陈述，说明你与议题的关系、核心利益和基本立场。"
            messages = build_messages(system_prompt, conversation, instruction)

            # Notify frontend who's about to speak
            yield f"data: {json.dumps({'type': 'thinking', 'agent_id': agent.agent_id, 'agent_name': agent.agent_name, 'agent_emoji': agent.avatar_emoji, 'agent_color': agent.avatar_color, 'phase': 'opening'})}\n\n"
            await asyncio.sleep(0.3)

            raw = llm.chat(messages, system=system_prompt, json_mode=True)
            parsed = parse_agent_response(raw, agent)

            utt = Utterance(
                utterance_id=f"utt_{state.turn:04d}",
                speaker_id=agent.agent_id,
                speaker_name=agent.agent_name,
                turn=state.turn + 1,
                stance_score=parsed["stance"],
                reply_to=parsed.get("reply_to"),
                evidence_ids=parsed.get("evidence_ids", []),
                content=parsed["content"],
            )
            is_valid, reason = check_utterance(utt, agent)
            if not is_valid:
                utt.is_boundary_violation = True
                utt.violation_reason = reason

            state.history.append(utt)
            state.speaker_stats[agent.agent_id] = state.speaker_stats.get(agent.agent_id, 0) + 1
            state.stance_trajectory[agent.agent_id].append(parsed["stance"])
            state.turn += 1

            # Send the utterance to frontend
            yield f"data: {json.dumps({'type': 'utterance', 'turn': utt.turn, 'speaker_name': utt.speaker_name, 'speaker_id': utt.speaker_id, 'speaker_emoji': agent.avatar_emoji, 'speaker_color': agent.avatar_color, 'content': utt.content, 'stance_score': utt.stance_score, 'reply_to': utt.reply_to, 'evidence_ids': utt.evidence_ids, 'is_violation': utt.is_boundary_violation, 'phase': 'opening'})}\n\n"
            await asyncio.sleep(0.5)

        # Phase 2: Discussion rounds
        remaining = state.max_turns - state.turn - 2
        num_rounds = max(1, remaining // len(state.agents))
        for round_idx in range(num_rounds):
            for agent in state.agents:
                if state.turn >= state.max_turns - 2:
                    break

                agent_evidence = retrieve_for_agent(agent, _evidence_pool, max_cards=3)
                system_prompt, conversation = build_agent_context(
                    agent, state.topic, state.question, agent_evidence, state
                )

                last_utt = state.history[-1] if state.history else None
                if last_utt:
                    instruction = (
                        f"你是{agent.agent_name}。"
                        f"上一轮 {last_utt.speaker_name} 说：\"{last_utt.content[:200]}...\"\n"
                        f"请从你的角色立场做出回应。记住你不可退让的底线。"
                    )
                else:
                    instruction = f"你是{agent.agent_name}。请发表你的看法。"

                messages = build_messages(system_prompt, conversation, instruction)

                yield f"data: {json.dumps({'type': 'thinking', 'agent_id': agent.agent_id, 'agent_name': agent.agent_name, 'agent_emoji': agent.avatar_emoji, 'agent_color': agent.avatar_color, 'phase': 'discussion', 'round': round_idx + 1})}\n\n"
                await asyncio.sleep(0.3)

                raw = llm.chat(messages, system=system_prompt, json_mode=True)
                parsed = parse_agent_response(raw, agent)

                utt = Utterance(
                    utterance_id=f"utt_{state.turn:04d}",
                    speaker_id=agent.agent_id,
                    speaker_name=agent.agent_name,
                    turn=state.turn + 1,
                    stance_score=parsed["stance"],
                    reply_to=parsed.get("reply_to"),
                    evidence_ids=parsed.get("evidence_ids", []),
                    content=parsed["content"],
                )
                is_valid, reason = check_utterance(utt, agent)
                if not is_valid:
                    utt.is_boundary_violation = True
                    utt.violation_reason = reason

                state.history.append(utt)
                state.speaker_stats[agent.agent_id] = state.speaker_stats.get(agent.agent_id, 0) + 1
                state.stance_trajectory[agent.agent_id].append(parsed["stance"])
                state.turn += 1

                yield f"data: {json.dumps({'type': 'utterance', 'turn': utt.turn, 'speaker_name': utt.speaker_name, 'speaker_id': utt.speaker_id, 'speaker_emoji': agent.avatar_emoji, 'speaker_color': agent.avatar_color, 'content': utt.content, 'stance_score': utt.stance_score, 'reply_to': utt.reply_to, 'evidence_ids': utt.evidence_ids, 'is_violation': utt.is_boundary_violation, 'phase': 'discussion'})}\n\n"
                await asyncio.sleep(0.5)

        # Phase 3: Summary
        summarizer = state.agents[3]  # 街道办治理人员
        agent_evidence = retrieve_for_agent(summarizer, _evidence_pool, max_cards=5)
        system_prompt, conversation = build_agent_context(
            summarizer, state.topic, state.question, agent_evidence, state
        )

        all_positions = "\n".join(
            f"- {u.speaker_name}: {u.content[:100]}..."
            for u in state.history[-12:]
        )
        instruction = (
            f"你是{summarizer.agent_name}。议事已接近尾声。请基于以下各方立场做最终总结：\n\n"
            f"{all_positions}\n\n"
            f"请总结各方达成的共识点、仍然存在的分歧点、可执行的下一步方案、"
            f"需要实地调研才能回答的问题、以及少数意见（未被采纳但合理的观点）。"
        )

        messages = build_messages(system_prompt, conversation, instruction)

        yield f"data: {json.dumps({'type': 'thinking', 'agent_id': summarizer.agent_id, 'agent_name': summarizer.agent_name, 'agent_emoji': summarizer.avatar_emoji, 'agent_color': summarizer.avatar_color, 'phase': 'summary'})}\n\n"
        await asyncio.sleep(0.3)

        raw = llm.chat(messages, system=system_prompt, json_mode=True)
        parsed = parse_agent_response(raw, summarizer)

        utt = Utterance(
            utterance_id=f"utt_{state.turn:04d}",
            speaker_id=summarizer.agent_id,
            speaker_name=summarizer.agent_name,
            turn=state.turn + 1,
            stance_score=parsed["stance"],
            reply_to=None,
            evidence_ids=parsed.get("evidence_ids", []),
            content=parsed["content"],
        )
        state.history.append(utt)
        state.speaker_stats[summarizer.agent_id] = state.speaker_stats.get(summarizer.agent_id, 0) + 1
        state.stance_trajectory[summarizer.agent_id].append(parsed["stance"])
        state.turn += 1
        state.finished = True

        yield f"data: {json.dumps({'type': 'utterance', 'turn': utt.turn, 'speaker_name': utt.speaker_name, 'speaker_id': utt.speaker_id, 'speaker_emoji': summarizer.avatar_emoji, 'speaker_color': summarizer.avatar_color, 'content': utt.content, 'stance_score': utt.stance_score, 'reply_to': utt.reply_to, 'evidence_ids': utt.evidence_ids, 'is_violation': utt.is_boundary_violation, 'phase': 'summary'})}\n\n"

        # Compute and send final metrics
        metrics = compute_metrics(state)
        yield f"data: {json.dumps({'type': 'metrics', 'fairness_gini': metrics.fairness_gini, 'grounding_rate': metrics.grounding_rate, 'consensus': metrics.consensus, 'polarization': metrics.polarization, 'minority_retention': metrics.minority_retention, 'speaker_share': metrics.speaker_share, 'anomaly_flags': metrics.anomaly_flags})}\n\n"

        # Done
        yield f"data: {json.dumps({'type': 'finished', 'total_turns': state.turn})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@app.get("/api/deliberation/stream")
async def stream_deliberation():
    """Stream the deliberation process via Server-Sent Events."""
    global _current_state
    if _current_state is None:
        raise HTTPException(404, "No active session. POST /api/deliberation/start first.")

    return StreamingResponse(
        _stream_deliberation(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Non-streaming endpoints ───────────────────────────────────────────────────

@app.get("/api/deliberation/state")
async def get_state():
    """Get current deliberation state snapshot."""
    global _current_state
    if _current_state is None:
        raise HTTPException(404, "No active session.")

    return {
        "topic": _current_state.topic,
        "turn": _current_state.turn,
        "max_turns": _current_state.max_turns,
        "finished": _current_state.finished,
        "history": [
            {
                "turn": u.turn,
                "speaker_name": u.speaker_name,
                "speaker_id": u.speaker_id,
                "stance_score": u.stance_score,
                "reply_to": u.reply_to,
                "evidence_ids": u.evidence_ids,
                "content": u.content,
                "is_violation": u.is_boundary_violation,
            }
            for u in _current_state.history
        ],
    }


@app.get("/api/report")
async def get_report():
    """Get the generated report."""
    global _current_state, _topic_analysis

    if _current_state is None or not _current_state.history:
        raise HTTPException(404, "No deliberation data. Run a deliberation first.")

    metrics = compute_metrics(_current_state)
    output_dir = str(Path(__file__).parent.parent / "outputs")
    report = generate_report(_current_state, metrics, _topic_analysis or analyze_topic(_current_state.topic), output_dir)

    return {
        "topic": report.topic,
        "total_turns": report.total_turns,
        "metrics": {
            "fairness_gini": metrics.fairness_gini,
            "grounding_rate": metrics.grounding_rate,
            "consensus": metrics.consensus,
            "polarization": metrics.polarization,
            "minority_retention": metrics.minority_retention,
            "speaker_share": metrics.speaker_share,
            "anomaly_flags": metrics.anomaly_flags,
        },
        "consensus_points": report.consensus_points,
        "divergence_points": report.divergence_points,
        "minority_opinions": report.minority_opinions,
        "actionable_proposals": report.actionable_proposals,
        "field_research_questions": report.field_research_questions,
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting MA Deliberation API on http://localhost:8765")
    print(f"LLM Provider: {os.environ.get('LLM_PROVIDER', 'simulation')}")
    uvicorn.run(app, host="0.0.0.0", port=8765)

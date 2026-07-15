"""Orchestrator: LLM-driven multi-agent deliberation.

This is NOT a scripted replay. Each agent receives:
  1. Its own system prompt (role + interests + boundaries)
  2. Its matched evidence cards
  3. The conversation history
  4. A structured-response instruction

The agent then GENERATES its own response via an LLM call. The orchestrator
decides who speaks next using dynamic scheduling (priority: addressed party >
silent stakeholders > round-robin).
"""

from __future__ import annotations

import json
import re
import uuid

from .schemas import (
    AgentCard,
    DeliberationState,
    Utterance,
)
from .evidence import EvidenceCard, format_evidence_context
from .agents import get_agent_prompt
from .llm_client import LLMClient, create_llm_client, build_messages
from .boundary_checker import check_utterance


# ── Structured response instruction ──────────────────────────────────────────

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
3. 必须回应上一位发言者的核心观点（如果与你的立场相关）
4. 不要泛泛地说"我同意大家"
5. 保留至少一个你不可退让的底线
6. 可以提出条件性方案，而非简单的支持/反对
"""

# ── Speaker selection ─────────────────────────────────────────────────────────

def select_next_speaker(state: DeliberationState) -> AgentCard:
    """Select which agent should speak next.

    Priority:
    1. Agent explicitly addressed in the last utterance (if they haven't responded yet)
    2. Agent with fewest speaking turns (silent stakeholder priority)
    3. Round-robin
    """
    if not state.history:
        # First turn: pick the agent with strongest positive stance (proponent opens)
        return max(state.agents, key=lambda a: a.stance_score)

    last_utt = state.history[-1]

    # Priority 1: Who was addressed?
    if last_utt.reply_to:
        for agent in state.agents:
            if agent.agent_name == last_utt.reply_to:
                # Check they haven't spoken since being addressed
                recent_speakers = {
                    u.speaker_name
                    for u in state.history[-3:]  # last 3 turns
                }
                if agent.agent_name not in recent_speakers:
                    return agent

    # Priority 2: Least-speaking agent (favor silent stakeholders)
    speaking_counts = state.speaker_stats.copy()
    # Ensure all agents have an entry
    for agent in state.agents:
        if agent.agent_id not in speaking_counts:
            speaking_counts[agent.agent_id] = 0

    # Sort by: (is_silent_stakeholder DESC, count ASC)
    def sort_key(agent: AgentCard) -> tuple:
        is_silent = 1 if agent.archetype in ("间接影响者", "silent_stakeholder", "弱势群体") else 0
        count = speaking_counts.get(agent.agent_id, 0)
        return (-is_silent, count)

    sorted_agents = sorted(state.agents, key=sort_key)
    return sorted_agents[0]


def select_summary_speaker(state: DeliberationState) -> AgentCard:
    """Select the best agent to give a closing summary."""
    # Prefer governance/professional roles for summary
    for agent in state.agents:
        if agent.archetype in ("治理方", "专业观察者"):
            # Pick the one who has spoken less (to balance)
            return agent
    return state.agents[0]


# ── Response parsing ──────────────────────────────────────────────────────────

def parse_agent_response(raw_response: str, agent: AgentCard) -> dict:
    """Parse the LLM response into structured fields.

    Handles both clean JSON and JSON embedded in markdown/text.
    """
    # Try to extract JSON from the response
    json_str = raw_response.strip()

    # Remove markdown code fences if present
    if json_str.startswith("```"):
        lines = json_str.split("\n")
        # Remove first line (```json or ```) and last line (```)
        json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Find JSON object boundaries
    start = json_str.find("{")
    end = json_str.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = json_str[start:end + 1]

    try:
        parsed = json.loads(json_str)
        return {
            "speaker": parsed.get("speaker", agent.agent_name),
            "stance": float(parsed.get("stance", agent.stance_score)),
            "reply_to": parsed.get("reply_to"),
            "evidence_ids": parsed.get("evidence_ids", []),
            "content": parsed.get("content", ""),
        }
    except (json.JSONDecodeError, ValueError):
        # Fallback: extract content heuristically
        return {
            "speaker": agent.agent_name,
            "stance": agent.stance_score,
            "reply_to": None,
            "evidence_ids": [],
            "content": raw_response[:500],
        }


# ── Main orchestration ────────────────────────────────────────────────────────

def init_deliberation(
    topic: str,
    question: str,
    agents: list[AgentCard],
    max_turns: int = 20,
) -> DeliberationState:
    """Initialize a new deliberation session."""
    return DeliberationState(
        topic=topic,
        question=question,
        max_turns=max_turns,
        agents=agents,
        speaker_stats={a.agent_id: 0 for a in agents},
        stance_trajectory={a.agent_id: [a.stance_score] for a in agents},
    )


def build_agent_context(
    agent: AgentCard,
    topic: str,
    question: str,
    evidence_cards: list[EvidenceCard],
    state: DeliberationState,
) -> tuple[str, list[dict]]:
    """Build the system prompt and conversation messages for an agent."""
    # Build system prompt from role definition
    system_prompt = get_agent_prompt(agent, topic, question)

    # Append evidence context
    if evidence_cards:
        system_prompt += "\n\n## 你可引用的证据材料\n"
        system_prompt += format_evidence_context(evidence_cards)

    # Append structured output requirement
    system_prompt += f"\n\n{STRUCTURED_OUTPUT_INSTRUCTION}"

    # Build conversation history messages
    conversation = []
    for u in state.history:
        conversation.append({
            "speaker": u.speaker_name,
            "content": u.content,
            "turn": u.turn,
        })

    return system_prompt, conversation


def run_turn(
    state: DeliberationState,
    evidence_pool: list[EvidenceCard],
    llm: LLMClient | None = None,
) -> Utterance | None:
    """Execute one turn of LLM-driven deliberation.

    Returns the generated utterance, or None if deliberation is finished.
    """
    if state.finished or state.turn >= state.max_turns:
        state.finished = True
        return None

    if llm is None:
        llm = create_llm_client()

    # Select speaker
    speaker = select_next_speaker(state)

    # Get evidence for this agent
    from .evidence import retrieve_for_agent
    agent_evidence = retrieve_for_agent(speaker, evidence_pool, max_cards=3)

    # Build context
    system_prompt, conversation = build_agent_context(
        speaker, state.topic, state.question, agent_evidence, state
    )

    # Build current instruction based on turn
    if state.turn == 0:
        instruction = f"你是{speaker.agent_name}。请发表你的开场陈述，说明你的基本立场和核心诉求。"
    elif state.turn >= state.max_turns - 3:
        instruction = (
            f"你是{speaker.agent_name}。议事已接近尾声。"
            f"请发表你的最终陈述，明确你接受什么、不接受什么。"
        )
    else:
        last_utt = state.history[-1] if state.history else None
        if last_utt:
            instruction = (
                f"你是{speaker.agent_name}。"
                f"上一轮 {last_utt.speaker_name} 说：\"{last_utt.content[:150]}...\"\n"
                f"请从你的角色立场出发做出回应。"
            )
        else:
            instruction = f"你是{speaker.agent_name}。请从你的角色立场出发发表看法。"

    # Build messages for LLM
    messages = build_messages(system_prompt, conversation, instruction)

    # Call LLM
    raw_response = llm.chat(messages, system=system_prompt, json_mode=True)

    # Parse response
    parsed = parse_agent_response(raw_response, speaker)

    # Create utterance
    utterance = Utterance(
        utterance_id=f"utt_{state.turn:04d}",
        speaker_id=speaker.agent_id,
        speaker_name=speaker.agent_name,
        turn=state.turn + 1,
        stance_score=parsed["stance"],
        reply_to=parsed.get("reply_to"),
        evidence_ids=parsed.get("evidence_ids", []),
        content=parsed["content"],
    )

    # Run boundary checker
    is_valid, violation_reason = check_utterance(utterance, speaker)
    if not is_valid:
        utterance.is_boundary_violation = True
        utterance.violation_reason = violation_reason
        # Still include the utterance but mark it

    # Update state
    state.history.append(utterance)
    state.speaker_stats[speaker.agent_id] = state.speaker_stats.get(speaker.agent_id, 0) + 1
    state.stance_trajectory[speaker.agent_id].append(parsed["stance"])
    state.turn += 1

    return utterance


def run_opening_round(
    state: DeliberationState,
    evidence_pool: list[EvidenceCard],
    llm: LLMClient,
) -> list[Utterance]:
    """Run opening statements: each agent speaks once."""
    utterances = []
    for agent in state.agents:
        if state.turn >= state.max_turns:
            break

        from .evidence import retrieve_for_agent
        agent_evidence = retrieve_for_agent(agent, evidence_pool, max_cards=3)

        system_prompt, conversation = build_agent_context(
            agent, state.topic, state.question, agent_evidence, state
        )

        instruction = f"你是{agent.agent_name}。请发表你的开场陈述，说明你与议题的关系、你的核心利益和基本立场。"

        messages = build_messages(system_prompt, conversation, instruction)
        raw_response = llm.chat(messages, system=system_prompt, json_mode=True)
        parsed = parse_agent_response(raw_response, agent)

        utterance = Utterance(
            utterance_id=f"utt_{state.turn:04d}",
            speaker_id=agent.agent_id,
            speaker_name=agent.agent_name,
            turn=state.turn + 1,
            stance_score=parsed["stance"],
            reply_to=parsed.get("reply_to"),
            evidence_ids=parsed.get("evidence_ids", []),
            content=parsed["content"],
        )

        is_valid, reason = check_utterance(utterance, agent)
        if not is_valid:
            utterance.is_boundary_violation = True
            utterance.violation_reason = reason

        state.history.append(utterance)
        state.speaker_stats[agent.agent_id] = state.speaker_stats.get(agent.agent_id, 0) + 1
        state.stance_trajectory[agent.agent_id].append(parsed["stance"])
        state.turn += 1
        utterances.append(utterance)

    return utterances


def run_discussion_rounds(
    state: DeliberationState,
    evidence_pool: list[EvidenceCard],
    llm: LLMClient,
    num_rounds: int = 2,
) -> list[Utterance]:
    """Run multiple rounds of responsive discussion."""
    utterances = []
    for _ in range(num_rounds):
        for agent in state.agents:
            if state.turn >= state.max_turns - 2:  # Reserve last 2 turns for summary
                return utterances

            from .evidence import retrieve_for_agent
            agent_evidence = retrieve_for_agent(agent, evidence_pool, max_cards=3)

            system_prompt, conversation = build_agent_context(
                agent, state.topic, state.question, agent_evidence, state
            )

            last_utt = state.history[-1] if state.history else None
            if last_utt:
                instruction = (
                    f"你是{agent.agent_name}。"
                    f"上一轮 {last_utt.speaker_name} 说：\"{last_utt.content[:200]}...\"\n"
                    f"请从你的角色立场出发做出回应。你可以表示同意、反对或补充新观点。"
                    f"请记住你不可退让的底线。"
                )
            else:
                instruction = f"你是{agent.agent_name}。请继续发表你的看法。"

            messages = build_messages(system_prompt, conversation, instruction)
            raw_response = llm.chat(messages, system=system_prompt, json_mode=True)
            parsed = parse_agent_response(raw_response, agent)

            utterance = Utterance(
                utterance_id=f"utt_{state.turn:04d}",
                speaker_id=agent.agent_id,
                speaker_name=agent.agent_name,
                turn=state.turn + 1,
                stance_score=parsed["stance"],
                reply_to=parsed.get("reply_to"),
                evidence_ids=parsed.get("evidence_ids", []),
                content=parsed["content"],
            )

            is_valid, reason = check_utterance(utterance, agent)
            if not is_valid:
                utterance.is_boundary_violation = True
                utterance.violation_reason = reason

            state.history.append(utterance)
            state.speaker_stats[agent.agent_id] = state.speaker_stats.get(agent.agent_id, 0) + 1
            state.stance_trajectory[agent.agent_id].append(parsed["stance"])
            state.turn += 1
            utterances.append(utterance)

    return utterances


def run_closing_summary(
    state: DeliberationState,
    evidence_pool: list[EvidenceCard],
    llm: LLMClient,
) -> Utterance:
    """Generate a closing summary."""
    summarizer = select_summary_speaker(state)

    from .evidence import retrieve_for_agent
    agent_evidence = retrieve_for_agent(summarizer, evidence_pool, max_cards=5)

    system_prompt, conversation = build_agent_context(
        summarizer, state.topic, state.question, agent_evidence, state
    )

    # Build a summary of all positions
    all_positions = "\n".join(
        f"- {u.speaker_name}: {u.content[:100]}..."
        for u in state.history[-12:]  # last 12 utterances for context
    )

    instruction = (
        f"你是{summarizer.agent_name}。议事已接近尾声。请基于以下各方立场做最终总结：\n\n"
        f"{all_positions}\n\n"
        f"请总结：\n"
        f"1. 各方达成的共识点\n"
        f"2. 仍然存在的分歧点\n"
        f"3. 可执行的下一步方案\n"
        f"4. 需要实地调研才能回答的问题\n"
        f"5. 少数意见（未被采纳但合理的观点）\n\n"
        f"请以 JSON 格式输出。"
    )

    messages = build_messages(system_prompt, conversation, instruction)
    raw_response = llm.chat(messages, system=system_prompt, json_mode=True)
    parsed = parse_agent_response(raw_response, summarizer)

    utterance = Utterance(
        utterance_id=f"utt_{state.turn:04d}",
        speaker_id=summarizer.agent_id,
        speaker_name=summarizer.agent_name,
        turn=state.turn + 1,
        stance_score=parsed["stance"],
        reply_to=None,
        evidence_ids=parsed.get("evidence_ids", []),
        content=parsed["content"],
    )

    state.history.append(utterance)
    state.speaker_stats[summarizer.agent_id] = state.speaker_stats.get(summarizer.agent_id, 0) + 1
    state.stance_trajectory[summarizer.agent_id].append(parsed["stance"])
    state.turn += 1
    state.finished = True

    return utterance


def run_full_deliberation(
    topic: str,
    question: str,
    agents: list[AgentCard],
    evidence_pool: list[EvidenceCard],
    max_turns: int = 20,
    llm_client: LLMClient | None = None,
) -> DeliberationState:
    """Run the full deliberation with LLM-driven agent responses.

    Flow:
    1. Opening round: each agent gives opening statement
    2. Discussion rounds: agents respond to each other
    3. Closing summary: moderator/professional summarizes
    """
    if llm_client is None:
        llm_client = create_llm_client()

    state = init_deliberation(topic, question, agents, max_turns)

    # Phase 1: Opening statements
    run_opening_round(state, evidence_pool, llm_client)

    # Phase 2: Discussion (fill remaining turns)
    remaining_turns = max_turns - state.turn - 2  # Reserve 2 for summary
    num_discussion_rounds = max(1, remaining_turns // len(agents))
    run_discussion_rounds(state, evidence_pool, llm_client, num_discussion_rounds)

    # Phase 3: Closing summary
    run_closing_summary(state, evidence_pool, llm_client)

    return state

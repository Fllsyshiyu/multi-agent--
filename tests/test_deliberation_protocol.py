from ma_deliberation_demo.artifacts import MotionStatus, RoundSummary
from ma_deliberation_demo.organizational_behavior import assess_group_dynamics
from ma_deliberation_demo.procedural_validators import gate_procedural_readiness
from ma_deliberation_demo.protocols import ProtocolRuntime
from ma_deliberation_demo.protocols.speaker_scheduler import schedule_speakers
from ma_deliberation_demo.schemas import AgentCard
from ma_deliberation_demo.agents import generate_agents, load_archetypes
from ma_deliberation_demo.topic import analyze_topic
import asyncio


def agent(agent_id: str, stance: float, archetype: str = "直接受影响者") -> AgentCard:
    return AgentCard(
        agent_id=agent_id, agent_name=agent_id, archetype=archetype,
        relationship_to_topic="test", stance_score=stance,
    )


def test_main_motion_requires_another_agent_to_second_then_opens_debate():
    proposer, seconder = agent("proposer", 0.8), agent("seconder", -0.6)
    runtime = ProtocolRuntime()
    motion = runtime.open_main_motion("试点条件化治理", proposer)

    assert motion.status == MotionStatus.AWAITING_SECOND
    assert not runtime.second_current_motion(proposer)
    assert runtime.second_current_motion(seconder)
    assert runtime.current_motion.status == MotionStatus.DEBATE_OPEN
    assert runtime.events[-1].reason == "附议仅表示值得讨论，不表示赞成"


def test_amendment_precedes_main_motion_and_closure_needs_minority_and_evidence():
    proposer, seconder, amender = agent("p", 0.8), agent("s", -0.7), agent("a", 0.1)
    runtime = ProtocolRuntime()
    runtime.open_main_motion("主议案", proposer)
    runtime.second_current_motion(seconder)
    amendment = runtime.propose_amendment("增加环卫经费条款", amender)

    assert amendment is not None
    assert runtime.current_motion.motion_type.value == "amendment"
    assert runtime.second_current_motion(seconder)
    assert not runtime.close_debate(amender, minority_retained=False, evidence_ready=True)
    assert runtime.current_motion.status == MotionStatus.DEBATE_OPEN
    assert runtime.close_debate(amender, minority_retained=True, evidence_ready=True)
    assert runtime.current_motion.status == MotionStatus.VOTING


def test_adopted_amendment_updates_parent_and_returns_to_main_motion():
    proposer, seconder, amender = agent("p", 0.8), agent("s", -0.7), agent("a", 0.1)
    runtime = ProtocolRuntime()
    main = runtime.open_main_motion("主议案", proposer)
    runtime.second_current_motion(seconder)
    amendment = runtime.propose_amendment("增加环卫经费条款", amender)
    assert amendment is not None
    runtime.second_current_motion(seconder)
    runtime.close_debate(amender, minority_retained=True, evidence_ready=True)
    runtime.record_vote(proposer, "support")
    runtime.record_vote(seconder, "support")

    assert runtime.finalise_vote([proposer, seconder, amender], amender) == "amendment_adopted"
    assert runtime.current_motion is main
    assert main.status == MotionStatus.DEBATE_OPEN
    assert "增加环卫经费条款" in main.content


def test_speaker_scheduler_prioritises_low_participation_and_alternates_positions():
    positive, negative, neutral = agent("positive", 0.8), agent("negative", -0.8), agent("neutral", 0.0)
    ordered = schedule_speakers([positive, negative, neutral], {"positive": 3, "negative": 0, "neutral": 0})

    assert ordered[0].agent_id == "negative"
    assert ordered[1].agent_id == "positive"


def test_group_dynamics_flags_dominance_and_unsafe_language():
    assessment = assess_group_dynamics([
        {"speaker": "甲", "content": "大家一致同意，你们根本不懂。", "evidence_ids": []},
        {"speaker": "甲", "content": "完全赞同，立刻通过。", "evidence_ids": []},
        {"speaker": "乙", "content": "", "evidence_ids": []},
    ], ["甲", "乙", "丙"])

    assert assessment.speaker_dominance > 0.35
    assert assessment.psychological_safety_risk > 0
    assert assessment.interventions


def test_procedural_gate_preserves_minority_and_evidence_requirements():
    proposer, seconder = agent("p", 0.8), agent("s", -0.8)
    runtime = ProtocolRuntime()
    runtime.open_main_motion("主议案", proposer)
    runtime.second_current_motion(seconder)

    rejected = gate_procedural_readiness(runtime, RoundSummary(minority_views=[], evidence_gaps=[]))
    passed = gate_procedural_readiness(runtime, RoundSummary(minority_views=["反方条件"], evidence_gaps=[]))

    assert rejected.status == "revise"
    assert passed.status == "pass"


def test_api_session_registers_a_debating_motion():
    from api.main import DeliberationRequest, start_deliberation

    result = asyncio.run(start_deliberation(DeliberationRequest(topic="小区门口夜市是否应该保留？")))

    assert result["protocol"]["status"] == "debate_open"
    assert "条件化治理建议" in result["protocol"]["current_motion"]


def test_agent_ids_are_deterministic_for_the_same_topic():
    analysis = analyze_topic("小区门口夜市是否应该保留？")
    first = generate_agents("小区门口夜市是否应该保留？", analysis, load_archetypes())
    second = generate_agents("小区门口夜市是否应该保留？", analysis, load_archetypes())

    assert [(a.agent_id, a.agent_name) for a in first] == [(a.agent_id, a.agent_name) for a in second]


def test_simulation_stream_emits_protocol_and_behavior_events():
    import api.main as api

    async def collect():
        await api.start_deliberation(api.DeliberationRequest(topic="小区门口夜市是否应该保留？", max_rounds=1, max_speakers=3))
        return [item async for item in api._stream_sop()]

    events = asyncio.run(collect())

    assert any("procedural_event" in event for event in events)
    assert any("behavior_assessment" in event for event in events)
    assert sum("round_summary" in event for event in events) == 1
    assert events[-1] == "data: [DONE]\n\n"

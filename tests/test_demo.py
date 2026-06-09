from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo.agents import generate_agents, load_archetypes
from ma_deliberation_demo.evidence import load_evidence, retrieve_for_agent
from ma_deliberation_demo.llm_client import create_llm_client
from ma_deliberation_demo.observer import compute_metrics
from ma_deliberation_demo.orchestrator import run_full_deliberation
from ma_deliberation_demo.report import generate_report
from ma_deliberation_demo.topic import analyze_topic


def test_demo_runs_in_simulation_mode():
    topic = "小区门口夜市是否应该保留？"
    analysis = analyze_topic(topic)
    agents = generate_agents(topic, analysis, load_archetypes())
    evidence_pool = load_evidence(ROOT / "data" / "evidence_cards.csv")
    for agent in agents:
        retrieve_for_agent(agent, evidence_pool)

    state = run_full_deliberation(
        topic,
        "如果保留，应该设置哪些治理条件？",
        agents,
        evidence_pool,
        max_turns=8,
        llm_client=create_llm_client(provider="simulation"),
    )
    metrics = compute_metrics(state)
    report = generate_report(state, metrics, analysis, str(ROOT / "outputs"))

    assert len(state.agents) >= 5
    assert len(state.history) >= 6
    assert metrics.grounding_rate > 0
    assert report.topic == topic

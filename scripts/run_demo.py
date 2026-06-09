"""Run the LLM-driven multi-agent deliberation demo.

Usage:
  python scripts/run_demo.py --topic "小区门口夜市是否应该保留？"

LLM configuration via environment variables:
  LLM_PROVIDER=simulation|openai|anthropic|openai_compat
  LLM_MODEL=gpt-4o (or your model)
  LLM_API_KEY=sk-...
  LLM_BASE_URL=https://api.openai.com/v1  (for OpenAI-compatible APIs)

With simulation mode (default):
  python scripts/run_demo.py

With real LLM:
  LLM_PROVIDER=openai LLM_API_KEY=sk-xxx python scripts/run_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ma_deliberation_demo.topic import analyze_topic, compute_complexity
from ma_deliberation_demo.agents import load_archetypes, generate_agents
from ma_deliberation_demo.evidence import load_evidence, retrieve_for_agent
from ma_deliberation_demo.llm_client import create_llm_client
from ma_deliberation_demo.orchestrator import run_full_deliberation
from ma_deliberation_demo.observer import compute_metrics
from ma_deliberation_demo.report import generate_report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="LLM-driven Multi-Agent Deliberation Demo")
    parser.add_argument("--topic", type=str, default="小区门口夜市是否应该保留？")
    parser.add_argument("--question", type=str, default="夜市是否应该保留？如果保留，应该设置哪些治理条件？")
    parser.add_argument("--max-turns", type=int, default=18)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--llm-provider", type=str, default="")
    parser.add_argument("--llm-model", type=str, default="")
    parser.add_argument("--llm-api-key", type=str, default="")
    parser.add_argument("--llm-base-url", type=str, default="")
    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = str(Path(__file__).parent.parent / "outputs")

    print("=" * 60)
    print("  多智能体议事厅 Demo — LLM-driven")
    print("  Multi-Agent Deliberation System v0.3")
    print("=" * 60)
    print()

    # LLM Client
    llm = create_llm_client(
        provider=args.llm_provider,
        model=args.llm_model,
        api_key=args.llm_api_key,
        base_url=args.llm_base_url,
    )
    print(f"[LLM] {llm}")
    print()

    # 1. Topic analysis
    print("[1/6] 分析议题...")
    topic_analysis = analyze_topic(args.topic)
    complexity = compute_complexity(topic_analysis)
    print(f"  类型: {topic_analysis.topic_type.value} | 复杂度: {complexity['total']}/10 ({complexity['level']})")
    for ax in topic_analysis.conflict_axes:
        print(f"  冲突轴: {ax.name} ({ax.intensity})")
    print()

    # 2. Generate agents
    print("[2/6] 生成利益相关方 Agent...")
    archetypes = load_archetypes()
    agents = generate_agents(args.topic, topic_analysis, archetypes)
    for a in agents:
        print(f"  {a.avatar_emoji} {a.agent_name} ({a.archetype}) stance={a.stance_score:+.1f}")
    print()

    # 3. Evidence
    print("[3/6] 加载证据库...")
    evidence_pool = load_evidence()
    print(f"  证据总数: {len(evidence_pool)} 条")
    for a in agents:
        cards = retrieve_for_agent(a, evidence_pool)
        print(f"  {a.agent_name}: {len(cards)} 条匹配证据")
    print()

    # 4. Deliberation (LLM-driven!)
    print(f"[4/6] 执行多智能体议事 (LLM-driven, max {args.max_turns} turns)...")
    print("  每个 Agent 根据自己的角色设定、证据卡和对话历史独立生成发言...")
    print()
    state = run_full_deliberation(
        args.topic, args.question, agents, evidence_pool,
        max_turns=args.max_turns, llm_client=llm,
    )

    for u in state.history:
        stance_str = f"{u.stance_score:+.2f}"
        reply = f" -> {u.reply_to}" if u.reply_to else ""
        evidence = f" [{', '.join(u.evidence_ids)}]" if u.evidence_ids else ""
        print(f"  [T{u.turn:02d}] {u.speaker_name} (stance={stance_str}){reply}{evidence}")
        print(f"         {u.content[:120]}...")
        if u.is_boundary_violation:
            print(f"         !! BOUNDARY VIOLATION: {u.violation_reason}")
    print()

    # 5. Metrics
    print("[5/6] Observer 计算指标...")
    metrics = compute_metrics(state)
    print(f"  Fairness Gini:  {metrics.fairness_gini:.3f}")
    print(f"  Grounding rate: {metrics.grounding_rate:.2%}")
    print(f"  Consensus:      {metrics.consensus:.3f}")
    print(f"  Polarization:   {metrics.polarization:.3f}")
    print(f"  Minority ret.:  {metrics.minority_retention:.3f}")
    if metrics.anomaly_flags:
        for flag in metrics.anomaly_flags:
            print(f"  :warning: {flag}")
    print()

    # 6. Report
    print("[6/6] 生成议事报告...")
    report = generate_report(state, metrics, topic_analysis, args.output_dir)
    print(f"  报告已保存: {args.output_dir}/")
    print(f"  共识点: {len(report.consensus_points)} | 分歧点: {len(report.divergence_points)}")
    print(f"  可执行方案: {len(report.actionable_proposals)} | 待调研: {len(report.field_research_questions)}")
    print()
    print("=" * 60)
    print("  议事完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

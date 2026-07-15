"""Evaluation script for the MA Deliberation Demo."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ma_deliberation_demo.topic import analyze_topic, compute_complexity
from ma_deliberation_demo.agents import load_archetypes, generate_agents
from ma_deliberation_demo.evidence import load_evidence, retrieve_for_agent
from ma_deliberation_demo.orchestrator import run_full_deliberation
from ma_deliberation_demo.observer import compute_metrics


def run_eval(topic: str, question: str, n_runs: int = 5):
    """Run evaluation multiple times and report mean/variance."""
    print(f"Running {n_runs} evaluation runs...")

    results = []
    for run_idx in range(n_runs):
        topic_analysis = analyze_topic(topic)
        archetypes = load_archetypes()
        agents = generate_agents(topic, topic_analysis, archetypes)
        evidence_pool = load_evidence()
        for agent in agents:
            retrieve_for_agent(agent, evidence_pool)

        state = run_full_deliberation(topic, question, agents, evidence_pool)
        metrics = compute_metrics(state)

        results.append({
            "run": run_idx + 1,
            "turns": state.turn,
            "fairness_gini": metrics.fairness_gini,
            "grounding_rate": metrics.grounding_rate,
            "consensus": metrics.consensus,
            "polarization": metrics.polarization,
            "minority_retention": metrics.minority_retention,
            "anomaly_count": len(metrics.anomaly_flags),
        })

    # Compute statistics
    keys = ["fairness_gini", "grounding_rate", "consensus", "polarization", "minority_retention"]
    stats = {}
    for key in keys:
        vals = [r[key] for r in results]
        stats[key] = {
            "mean": sum(vals) / len(vals),
            "min": min(vals),
            "max": max(vals),
            "std": (sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5,
        }

    print("\nEvaluation Results:")
    print(f"{'Metric':<25} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print("-" * 60)
    for key in keys:
        s = stats[key]
        print(f"{key:<25} {s['mean']:>8.4f} {s['std']:>8.4f} {s['min']:>8.4f} {s['max']:>8.4f}")

    # Save results
    output_dir = Path(__file__).parent.parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "eval_results.json", "w", encoding="utf-8") as f:
        json.dump({"runs": results, "statistics": stats}, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to {output_dir / 'eval_results.json'}")
    return results, stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="小区门口夜市是否应该保留？")
    parser.add_argument("--question", default="夜市是否应该保留？如果保留，应该设置哪些治理条件？")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    run_eval(args.topic, args.question, args.runs)

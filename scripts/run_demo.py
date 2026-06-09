from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo import run_deliberation  # noqa: E402
from ma_deliberation_demo.schemas import to_dict  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a configurable multi-agent deliberation demo.")
    parser.add_argument("--topic", default="小区门口夜市是否应该保留？", help="规划议题")
    parser.add_argument("--evidence", default=str(ROOT / "data" / "evidence_cards.csv"), help="Evidence CSV path")
    parser.add_argument("--out", default=str(ROOT / "outputs"), help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run_deliberation(args.topic, args.evidence)

    report_path = out_dir / "demo_report.md"
    transcript_path = out_dir / "demo_transcript.json"
    metrics_path = out_dir / "demo_metrics.json"

    report_path.write_text(result.report_markdown, encoding="utf-8")
    transcript_path.write_text(json.dumps([to_dict(x) for x in result.transcript], ensure_ascii=False, indent=2), encoding="utf-8")
    metrics_path.write_text(json.dumps(to_dict(result.metrics), ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 多智能体议事厅 Demo 已完成 ===")
    print(f"Topic: {args.topic}")
    print(f"Agents: {', '.join(agent.agent_name for agent in result.agents)}")
    print(f"Turns: {len(result.transcript)}")
    print(f"Grounding rate: {result.metrics.grounding_rate:.2%}")
    print(f"Fairness Gini: {result.metrics.fairness_gini:.3f}")
    if result.metrics.consensus_history:
        print(f"Consensus: {result.metrics.consensus_history[0]['consensus_score']:.3f} -> {result.metrics.consensus_history[-1]['consensus_score']:.3f}")
    print(f"Report: {report_path}")
    print(f"Transcript: {transcript_path}")
    print(f"Metrics: {metrics_path}")


if __name__ == "__main__":
    main()

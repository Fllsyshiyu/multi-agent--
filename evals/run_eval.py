from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo import run_deliberation  # noqa: E402
from ma_deliberation_demo.schemas import to_dict  # noqa: E402


def main() -> None:
    evidence = ROOT / "data" / "evidence_cards.csv"
    topics = [
        "小区门口夜市是否应该保留？",
        "老旧小区是否应该加装电梯？",
    ]
    rows = []
    for topic in topics:
        result = run_deliberation(topic, evidence)
        rows.append({
            "topic": topic,
            "num_agents": len(result.agents),
            "num_turns": len(result.transcript),
            "grounding_rate": result.metrics.grounding_rate,
            "fairness_gini": result.metrics.fairness_gini,
            "first_consensus": result.metrics.consensus_history[0]["consensus_score"] if result.metrics.consensus_history else None,
            "last_consensus": result.metrics.consensus_history[-1]["consensus_score"] if result.metrics.consensus_history else None,
            "minority_agents": result.metrics.minority_agents,
        })
    out = ROOT / "outputs" / "eval_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo import run_deliberation


def test_demo_runs():
    result = run_deliberation("小区门口夜市是否应该保留？", ROOT / "data" / "evidence_cards.csv")
    assert len(result.agents) >= 5
    assert len(result.transcript) >= 10
    assert result.metrics.grounding_rate > 0.5
    assert "议事报告" in result.report_markdown

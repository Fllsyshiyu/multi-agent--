"""Schema checks for the curated external-case knowledge corpus."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "knowledge" / "external_cases.jsonl"


REQUIRED_FIELDS = {
    "id",
    "knowledge_type",
    "topic",
    "region",
    "date_range",
    "scenario",
    "stakeholders",
    "interventions",
    "implementers",
    "deliberation_method",
    "outcomes",
    "failure_modes",
    "transfer_conditions",
    "non_transferable_differences",
    "evidence_level",
    "source_records",
    "summary_for_rag",
    "retrieval_tags",
    "verification_gaps",
}


def test_external_cases_jsonl_is_valid_and_ready_for_retrieval() -> None:
    rows = [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert rows
    assert len({row["id"] for row in rows}) == len(rows)

    for row in rows:
        assert REQUIRED_FIELDS <= row.keys()
        assert row["knowledge_type"] == "external_case"
        assert row["summary_for_rag"].strip()
        assert isinstance(row["source_records"], list) and row["source_records"]
        assert all(
            isinstance(source, dict)
            and str(source.get("url", "")).startswith(("http://", "https://"))
            for source in row["source_records"]
        )

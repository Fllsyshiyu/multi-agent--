"""Recover structured external-case records from a malformed ChatGPT export.

Usage:
  python scripts/clean_external_cases.py INPUT.txt data/knowledge/external_cases.jsonl

The source file is never overwritten.  The script only keeps fields that can
be recovered deterministically and records any suspect fields in a sidecar
report so they can be reviewed before the cases enter a production RAG.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


CASE_START = re.compile(r'\{"id":"(C-\d{3})"')
STRING_FIELDS = (
    "id", "knowledge_type", "topic", "region", "date_range", "scenario",
    "deliberation_method", "evidence_level", "summary_for_rag",
)
LIST_FIELDS = (
    "stakeholders", "interventions", "implementers", "outcomes",
    "failure_modes", "transfer_conditions", "non_transferable_differences",
    "retrieval_tags", "verification_gaps",
)


def _clean_text(value: str) -> str:
    """Remove a known malformed Markdown-link suffix, never inventing text."""
    value = value.strip()
    value = re.split(r'\]\(https?://', value, maxsplit=1)[0]
    return value.replace('[[https://', 'https://').replace('[[http://', 'http://').rstrip('\\]')


def _string_value(record: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}":"((?:\\.|[^"\\])*)"', record)
    if not match:
        return ""
    try:
        return _clean_text(json.loads(f'"{match.group(1)}"'))
    except json.JSONDecodeError:
        return _clean_text(match.group(1))


def _array_body(record: str, field: str) -> str | None:
    marker = f'"{field}":['
    start = record.find(marker)
    if start < 0:
        return None
    index = start + len(marker) - 1
    depth = 0
    quoted = False
    escaped = False
    for pos in range(index, len(record)):
        char = record[pos]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                return record[index + 1:pos]
    return None


def _string_list(record: str, field: str) -> list[str]:
    body = _array_body(record, field)
    if body is None:
        return []
    try:
        values = json.loads(f'[{body}]')
        return [_clean_text(str(value)) for value in values if _clean_text(str(value))]
    except json.JSONDecodeError:
        values = re.findall(r'"((?:\\.|[^"\\])*)"', body)
        return [_clean_text(value) for value in values if _clean_text(value)]


def _sources(record: str) -> list[dict]:
    pattern = re.compile(
        r'\{"title":"((?:\\.|[^"\\])*)","url":"((?:\\.|[^"\\])*)",'
        r'"publisher":"((?:\\.|[^"\\])*)","published_at":"((?:\\.|[^"\\])*)",'
        r'"source_type":"((?:\\.|[^"\\])*)"\}'
    )
    sources = []
    for title, url, publisher, published_at, source_type in pattern.findall(record):
        url = _clean_text(url)
        if not re.match(r"https?://", url):
            continue
        sources.append({
            "title": _clean_text(title),
            "url": url,
            "publisher": _clean_text(publisher),
            "published_at": _clean_text(published_at),
            "source_type": _clean_text(source_type),
        })
    return sources


def recover_cases(text: str) -> tuple[list[dict], list[dict]]:
    matches = list(CASE_START.finditer(text))
    cases: list[dict] = []
    report: list[dict] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw = text[match.start():end]
        case = {field: _string_value(raw, field) for field in STRING_FIELDS}
        case.update({field: _string_list(raw, field) for field in LIST_FIELDS})
        case["source_records"] = _sources(raw)
        case["knowledge_type"] = "external_case"

        issues = []
        if not case["id"]:
            issues.append("missing_id")
        if not case["source_records"]:
            issues.append("no_recoverable_source_url")
        if case["evidence_level"] not in {"high", "medium", "low"}:
            issues.append("invalid_evidence_level")
        if not case["summary_for_rag"]:
            issues.append("missing_rag_summary")
        report.append({"id": case["id"], "issues": issues})
        cases.append(case)
    return cases, report


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/clean_external_cases.py INPUT.txt OUTPUT.jsonl")
        return 2
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    cases, report = recover_cases(source.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    report_path = output.with_name(f"{output.stem}_cleaning_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Recovered {len(cases)} cases to {output}")
    print(f"Review report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

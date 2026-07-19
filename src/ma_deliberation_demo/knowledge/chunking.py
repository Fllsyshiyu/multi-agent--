"""Turn a source case into small, attributable retrieval units."""

from __future__ import annotations

from typing import Any, Iterable

from .schema import CaseChunk


def _items(values: Iterable[Any]) -> str:
    return "；".join(str(value).strip() for value in values if str(value).strip())


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else f"{text[:max_chars - 1]}…"


def _case_prefix(case: dict[str, Any]) -> str:
    return " | ".join(
        part for part in (
            f"案例 {case.get('id', '')}",
            f"主题：{case.get('topic', '')}",
            f"地区：{case.get('region', '')}",
            "知识类型：外部参考案例（不是当前社区事实）",
        ) if part
    )


def chunk_case(case: dict[str, Any], *, max_chars: int = 1200) -> list[CaseChunk]:
    """Create balanced chunks without separating claims from their caveats."""
    case_id = str(case.get("id", "")).strip()
    if not case_id:
        raise ValueError("Case record is missing id.")
    source_records = tuple(case.get("source_records", []))
    common = {
        "case_id": case_id,
        "knowledge_type": str(case.get("knowledge_type", "external_case")),
        "topic": str(case.get("topic", "")),
        "region": str(case.get("region", "")),
        "evidence_level": str(case.get("evidence_level", "low")),
        "retrieval_tags": tuple(case.get("retrieval_tags", [])),
        "source_records": source_records,
        "verification_gaps": tuple(case.get("verification_gaps", [])),
    }
    prefix = _case_prefix(case)
    definitions = (
        ("overview", "案例概况", [case.get("summary_for_rag", ""), case.get("scenario", "")]),
        ("interventions", "干预措施与实施主体", [
            f"议事/处置方式：{case.get('deliberation_method', '')}",
            f"干预措施：{_items(case.get('interventions', []))}",
            f"实施主体：{_items(case.get('implementers', []))}",
            f"相关方：{_items(case.get('stakeholders', []))}",
        ]),
        ("outcomes", "结果与失败模式", [
            f"已知结果：{_items(case.get('outcomes', []))}",
            f"失败模式/局限：{_items(case.get('failure_modes', []))}",
        ]),
        ("transferability", "迁移条件与待核验事项", [
            f"可迁移条件：{_items(case.get('transfer_conditions', []))}",
            f"不可直接迁移的差异：{_items(case.get('non_transferable_differences', []))}",
            f"待核验事项：{_items(case.get('verification_gaps', []))}",
        ]),
    )
    chunks = []
    for chunk_type, heading, sections in definitions:
        body = "\n".join(section.strip() for section in sections if str(section).strip())
        if not body:
            continue
        chunks.append(CaseChunk(
            chunk_id=f"{case_id}:{chunk_type}",
            chunk_type=chunk_type,
            text=_clip(f"{prefix}\n{heading}：{body}", max_chars),
            **common,
        ))
    return chunks


def chunk_cases(cases: Iterable[dict[str, Any]], *, max_chars: int = 1200) -> list[CaseChunk]:
    chunks: list[CaseChunk] = []
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", ""))
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case id: {case_id}")
        seen_ids.add(case_id)
        chunks.extend(chunk_case(case, max_chars=max_chars))
    return chunks

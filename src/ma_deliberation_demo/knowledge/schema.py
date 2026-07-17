"""Data contracts for source cases, retrieval chunks, and search results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class CaseChunk:
    chunk_id: str
    case_id: str
    knowledge_type: str
    topic: str
    chunk_type: str
    text: str
    region: str = ""
    evidence_level: str = "low"
    retrieval_tags: tuple[str, ...] = ()
    source_records: tuple[dict[str, Any], ...] = ()
    verification_gaps: tuple[str, ...] = ()
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.case_id or not self.text.strip():
            raise ValueError("A knowledge chunk needs chunk_id, case_id, and text.")
        if not self.content_hash:
            object.__setattr__(self, "content_hash", self.compute_hash())

    def compute_hash(self) -> str:
        stable = "\n".join((
            self.chunk_id,
            self.knowledge_type,
            self.topic,
            self.chunk_type,
            self.text,
            self.evidence_level,
            "|".join(self.retrieval_tags),
            "|".join(self.verification_gaps),
        ))
        return sha256(stable.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("retrieval_tags", "source_records", "verification_gaps"):
            data[key] = list(data[key])
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CaseChunk":
        return cls(
            **{
                **raw,
                "retrieval_tags": tuple(raw.get("retrieval_tags", [])),
                "source_records": tuple(raw.get("source_records", [])),
                "verification_gaps": tuple(raw.get("verification_gaps", [])),
            }
        )


@dataclass(frozen=True)
class RetrievalHit:
    chunk: CaseChunk
    score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None


@dataclass
class IndexBuildReport:
    source_case_count: int = 0
    chunk_count: int = 0
    embedded_count: int = 0
    reused_count: int = 0
    backend: str = ""
    warnings: list[str] = field(default_factory=list)

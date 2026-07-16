"""Safe, neutral host prompts selected from observable risk signals."""

from __future__ import annotations

from .group_dynamics import BehaviorAssessment


def host_interventions(assessment: BehaviorAssessment, limit: int = 2) -> list[str]:
    """Return concise host actions without diagnosing participants personally."""
    return assessment.interventions[:limit]

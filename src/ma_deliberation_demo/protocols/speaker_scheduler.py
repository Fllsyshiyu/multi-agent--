"""Fair, procedure-aware speaker ordering for a Fishbowl inner circle."""

from __future__ import annotations

from ..schemas import AgentCard


def schedule_speakers(
    agents: list[AgentCard],
    speak_counts: dict[str, int] | None = None,
    last_stance_sign: int | None = None,
) -> list[AgentCard]:
    """Return an order that prioritises first speakers and alternates viewpoints.

    This is deliberately deterministic: the host cannot silently favour an
    authoritative role, and tests can verify the ordering.
    """
    counts = speak_counts or {}
    remaining = list(agents)
    ordered: list[AgentCard] = []
    previous_sign = last_stance_sign

    def sign(agent: AgentCard) -> int:
        return 1 if agent.stance_score > 0.15 else (-1 if agent.stance_score < -0.15 else 0)

    while remaining:
        candidates = remaining
        if previous_sign in (-1, 1):
            opposite = [a for a in remaining if sign(a) == -previous_sign]
            if opposite:
                candidates = opposite

        # First-time speakers, lower total participation, then stable agent id.
        selected = min(candidates, key=lambda a: (counts.get(a.agent_id, 0), a.agent_id))
        ordered.append(selected)
        remaining.remove(selected)
        if sign(selected):
            previous_sign = sign(selected)

    return ordered

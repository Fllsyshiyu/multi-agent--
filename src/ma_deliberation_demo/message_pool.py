"""Message Pool + Subscription — agents only see relevant information.

6 pools from the SOP document:
  case_context       — topic background, constraints, user input
  evidence_pool      — verified data and sources
  stakeholder_pool   — role profiles, position statements
  deliberation_pool  — round summaries, conflict points
  proposal_pool      — proposals and revision history
  review_pool        — evaluation, validation, risk alerts
"""

from __future__ import annotations

from typing import Any


POOL_NAMES = [
    "case_context",
    "evidence_pool",
    "stakeholder_pool",
    "deliberation_pool",
    "proposal_pool",
    "review_pool",
]

# Default subscriptions per agent archetype
DEFAULT_SUBSCRIPTIONS = {
    "resident": ["case_context", "stakeholder_pool", "evidence_pool"],
    "vulnerable_group": ["case_context", "stakeholder_pool", "evidence_pool", "deliberation_pool"],
    "expert": ["case_context", "evidence_pool", "proposal_pool"],
    "manager": ["case_context", "stakeholder_pool", "proposal_pool", "review_pool"],
    "business": ["case_context", "stakeholder_pool", "proposal_pool"],
    "moderator": ["case_context", "stakeholder_pool", "deliberation_pool", "proposal_pool", "review_pool"],
    "opposition": ["stakeholder_pool", "proposal_pool", "review_pool"],
}


class MessagePool:
    """Central message pool with subscription-based access.

    Agents subscribe to pools; they only receive content from subscribed pools.
    This prevents information overload and enforces role-appropriate context windows.
    """

    def __init__(self):
        self._pools: dict[str, list[dict]] = {name: [] for name in POOL_NAMES}
        self._subscriptions: dict[str, set[str]] = {}  # agent_id -> {pool_names}

    def subscribe(self, agent_id: str, pool_names: list[str]) -> None:
        """Subscribe an agent to specific pools."""
        self._subscriptions[agent_id] = set(pool_names)

    def subscribe_by_archetype(self, agent_id: str, archetype: str) -> None:
        """Subscribe using default archetype subscriptions."""
        pools = DEFAULT_SUBSCRIPTIONS.get(archetype, ["case_context", "stakeholder_pool"])
        self.subscribe(agent_id, pools)

    def publish(self, pool_name: str, item: dict) -> None:
        """Publish an item to a pool."""
        if pool_name in self._pools:
            self._pools[pool_name].append(item)

    def get_for_agent(self, agent_id: str) -> dict[str, list[dict]]:
        """Return all pool contents this agent is subscribed to."""
        subbed = self._subscriptions.get(agent_id, set())
        if not subbed:
            # No subscription = see everything (moderator fallback)
            return dict(self._pools)
        return {name: self._pools[name] for name in subbed if name in self._pools}

    def get_pool(self, pool_name: str) -> list[dict]:
        """Get all items in a specific pool."""
        return self._pools.get(pool_name, [])

    def clear(self) -> None:
        """Reset all pools."""
        for name in self._pools:
            self._pools[name] = []

    def summarize_for_agent(self, agent_id: str) -> str:
        """Build a compact context string for LLM prompt injection."""
        visible = self.get_for_agent(agent_id)
        parts = []

        for pool_name, items in visible.items():
            if not items:
                continue
            label = {
                "case_context": "议题背景",
                "evidence_pool": "可用证据",
                "stakeholder_pool": "利益相关方",
                "deliberation_pool": "讨论摘要",
                "proposal_pool": "方案记录",
                "review_pool": "评估反馈",
            }.get(pool_name, pool_name)

            lines = [f"## {label}"]
            for item in items[-5:]:  # Last 5 items per pool
                if isinstance(item, dict):
                    for k, v in item.items():
                        if v and k not in ("raw_response",):
                            lines.append(f"- {k}: {str(v)[:200]}")
                else:
                    lines.append(f"- {str(item)[:200]}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts) if parts else "（无可访问信息）"

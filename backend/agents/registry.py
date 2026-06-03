"""Agent Registry — allowlisted sub-agents available for dynamic planning."""

from typing import Any


class AgentRegistry:
    """Registry of sub-agents that domain agents can delegate to."""

    def __init__(self):
        self._agents: dict[str, Any] = {}

    def register(self, name: str, agent: Any):
        self._agents[name] = agent

    def get(self, name: str) -> Any | None:
        return self._agents.get(name)

    def available(self) -> list[str]:
        return list(self._agents.keys())

    def descriptions(self) -> dict[str, str]:
        """Return agent name → capability description for planner prompt."""
        descs = {}
        for name, agent in self._agents.items():
            doc = getattr(agent, "__doc__", None) or agent.__class__.__doc__ or ""
            descs[name] = doc.strip().split("\n")[0] if doc else name
        return descs

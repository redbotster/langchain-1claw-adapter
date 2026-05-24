"""LangChain Tool wrapper that routes calls through a Vault."""

from __future__ import annotations

from typing import Any, Optional

from .intent import Intent, IntentDeniedError
from .vault import Vault


class VaultBackedTool:
    """A LangChain-compatible tool that resolves credentials via a Vault.

    The agent sees a normal tool with `name`, `description`, and `run(...)`,
    but never reads the underlying credential. Every call submits an Intent
    to the vault, which checks policy before performing the upstream request.

    This class deliberately does NOT inherit from `langchain_core.tools.BaseTool`
    so the package can be imported without a hard langchain dependency. The
    public surface (`name`, `description`, `run`, `arun`) is shaped to drop
    into LangChain's agent framework via `Tool.from_function(...)` or by
    subclassing `BaseTool` in a thin wrapper. See `examples/paid_api_call.py`.
    """

    def __init__(
        self,
        name: str,
        description: str,
        vault: Vault,
        credential_handle: str,
        endpoint: str,
        estimated_usd_per_call: float = 0.0,
        agent_id: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self._vault = vault
        self._credential_handle = credential_handle
        self._endpoint = endpoint
        self._estimated_usd_per_call = estimated_usd_per_call
        self._agent_id = agent_id

    def run(self, **kwargs: Any) -> Any:
        """Invoke the tool. Submits an Intent and either returns the response
        or raises IntentDeniedError."""
        intent = Intent(
            tool_name=self.name,
            credential_handle=self._credential_handle,
            endpoint=self._endpoint,
            args=kwargs,
            estimated_usd=self._estimated_usd_per_call,
            agent_id=self._agent_id,
        )
        result = self._vault.submit_intent(intent)
        if not result.ok:
            raise IntentDeniedError(result.denial_reason or "policy denied", intent)
        return result.response

    async def arun(self, **kwargs: Any) -> Any:
        # Sync vault for now; async support is on the roadmap.
        return self.run(**kwargs)

    def __repr__(self) -> str:
        return f"VaultBackedTool(name={self.name!r}, handle={self._credential_handle!r})"

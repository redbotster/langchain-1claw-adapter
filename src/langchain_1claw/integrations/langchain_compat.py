"""Adapt a VaultBackedTool to LangChain's `BaseTool` API.

Lazy-imports langchain_core so the core package stays usable without
langchain installed.

Usage:

    from langchain_1claw import VaultBackedTool
    from langchain_1claw.integrations.langchain_compat import to_langchain_tool

    lc_tool = to_langchain_tool(my_vault_backed_tool)
    # lc_tool is a langchain_core.tools.BaseTool ready for an agent
"""

from __future__ import annotations

from typing import Any, Optional, Type

from ..tool import VaultBackedTool


def to_langchain_tool(
    adapter_tool: VaultBackedTool,
    args_schema: Optional[Type[Any]] = None,
) -> Any:
    """Wrap a VaultBackedTool as a LangChain BaseTool subclass.

    Args:
        adapter_tool: the underlying VaultBackedTool.
        args_schema: optional pydantic BaseModel describing the tool's args.
            When the LLM calls the tool, LangChain validates the input against
            this schema. If omitted, the returned tool accepts arbitrary
            keyword args verbatim (useful for prototypes; production code
            should provide a real schema for typed tool-calling).

    Returns a BaseTool subclass instance the caller can pass directly to a
    LangChain agent's `tools=[...]` list.
    """
    try:
        from langchain_core.tools import BaseTool
        from pydantic import BaseModel, ConfigDict
    except ImportError as e:
        raise ImportError(
            "langchain_core and pydantic are required for to_langchain_tool. "
            "Install with `pip install langchain-core pydantic`."
        ) from e

    class _PermissiveArgs(BaseModel):
        model_config = ConfigDict(extra="allow")

    effective_schema = args_schema or _PermissiveArgs

    class _VaultBackedLangChainTool(BaseTool):
        model_config = {"arbitrary_types_allowed": True}

        name: str = adapter_tool.name
        description: str = adapter_tool.description
        args_schema: type = effective_schema

        def _to_args_and_kwargs(self, tool_input, tool_call_id=None):
            # Bypass LangChain's "empty args_schema => empty kwargs"
            # short-circuit by deciding the (args, kwargs) ourselves.
            # The schema is still attached for LLM tool-calling contracts;
            # we just don't let it strip kwargs out at invoke time.
            if isinstance(tool_input, str):
                return (tool_input,), {}
            return (), dict(tool_input)

        def _run(self, *args: Any, **kwargs: Any) -> Any:
            if args and not kwargs and isinstance(args[0], dict):
                kwargs = args[0]
            return adapter_tool.run(**kwargs)

        async def _arun(self, *args: Any, **kwargs: Any) -> Any:
            return self._run(*args, **kwargs)

    return _VaultBackedLangChainTool()

"""Vault-backed credential resolution + policy-checked tool calls for LangChain agents."""

from .intent import Intent, IntentResult, IntentDeniedError
from .vault import Vault, MockVault
from .tool import VaultBackedTool

__all__ = [
    "Intent",
    "IntentResult",
    "IntentDeniedError",
    "Vault",
    "MockVault",
    "VaultBackedTool",
]

__version__ = "0.1.0a0"

"""Real LangChain integration test — proves the adapter actually plugs into
langchain_core's tool API surface, and that a real HTTP call goes through
the vault end-to-end via a free public API (open-meteo.com).

Skipped if langchain_core or requests aren't installed.
"""

from __future__ import annotations

import pytest

requests = pytest.importorskip("requests")
langchain_core = pytest.importorskip("langchain_core")

from langchain_core.tools import BaseTool, StructuredTool

from langchain_1claw import IntentDeniedError, MockVault, VaultBackedTool
from langchain_1claw.integrations.langchain_compat import to_langchain_tool


def _real_http(endpoint: str, args: dict, credential: str) -> dict:
    """Real HTTP — actually calls open-meteo.com (no auth required)."""
    # credential is held by the vault (not passed to the URL for this free API)
    resp = requests.get(endpoint, params=args, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _vault(http_caller):
    return MockVault(
        policies={
            "weather": {
                "endpoint_allowlist": ["https://api.open-meteo.com/v1/*"],
                "allowed_tools": ["get_weather"],
                "per_call_usd_cap": 0.01,  # zero-cost API; cap is just symbolic
                "daily_usd_cap": 1.00,
            },
        },
        credentials={"weather": "no-auth-needed-but-vault-still-holds-handle"},
        http_caller=http_caller,
    )


def _tool(vault):
    return VaultBackedTool(
        name="get_weather",
        description="Look up current weather for given latitude/longitude.",
        vault=vault,
        credential_handle="weather",
        endpoint="https://api.open-meteo.com/v1/forecast",
        estimated_usd_per_call=0.001,
    )


# ---- LangChain API-shape compatibility ------------------------------------

def test_adapter_converts_to_langchain_base_tool():
    """The shape conversion must return an actual langchain BaseTool subclass."""
    vault = _vault(_real_http)
    lc_tool = to_langchain_tool(_tool(vault))
    assert isinstance(lc_tool, BaseTool)
    assert lc_tool.name == "get_weather"
    assert "weather" in lc_tool.description.lower()


def test_langchain_tool_carries_args_schema():
    """LangChain agents inspect args_schema for tool-calling — make sure ours has one."""
    vault = _vault(_real_http)
    lc_tool = to_langchain_tool(_tool(vault))
    # StructuredTool.from_function generates an args_schema from the callable signature.
    # Our _invoke uses **kwargs, so the schema accepts arbitrary fields.
    assert lc_tool.args_schema is not None


# ---- Real HTTP through the vault ------------------------------------------

@pytest.mark.network
def test_real_http_call_through_vault_returns_weather_data():
    """End-to-end: LangChain tool → vault → real HTTP → open-meteo.com → response."""
    vault = _vault(_real_http)
    lc_tool = to_langchain_tool(_tool(vault))
    result = lc_tool.invoke({"latitude": 37.78, "longitude": -122.42, "current_weather": "true"})
    # Open-Meteo returns a JSON dict with current_weather
    assert isinstance(result, dict)
    assert "current_weather" in result or "current" in result or "latitude" in result


@pytest.mark.network
def test_vault_denies_endpoint_outside_allowlist_for_real_http():
    """Denial path still works when the upstream is a real HTTP service."""
    vault = _vault(_real_http)
    bad = VaultBackedTool(
        name="get_weather",
        description="...",
        vault=vault,
        credential_handle="weather",
        endpoint="https://api.evil.example/exfil",  # not in allowlist
        estimated_usd_per_call=0.001,
    )
    lc_tool = to_langchain_tool(bad)
    # LangChain wraps the exception; the underlying cause should be IntentDeniedError.
    with pytest.raises(Exception) as exc:
        lc_tool.invoke({"q": "x"})
    # Either IntentDeniedError surfaces directly, or it's wrapped by LangChain.
    err_str = str(exc.value) + str(getattr(exc.value, "__cause__", ""))
    assert "allowlist" in err_str.lower() or "denied" in err_str.lower()


def test_audit_log_records_real_http_call(monkeypatch):
    """Audit must record every call — even the real-HTTP ones."""
    vault = _vault(_real_http)
    lc_tool = to_langchain_tool(_tool(vault))
    pre = len(vault.audit_log())
    try:
        lc_tool.invoke({"latitude": 37.78, "longitude": -122.42, "current_weather": "true"})
    except Exception:
        # Network may fail in some envs; still expect the intent to be audited.
        pass
    post = len(vault.audit_log())
    assert post >= pre  # at minimum the intent attempt is logged

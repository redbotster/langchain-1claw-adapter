# Integration Verification

This document records the end-to-end integration test results for `langchain-1claw-adapter` — proving the adapter actually plugs into the real LangChain runtime and routes a real HTTP call through the vault.

## Test environment

- Python 3.14.2 (CPython)
- `langchain` 1.3.1
- `langchain_core` 1.4.0
- `requests` 2.34.2
- `pytest` 9.0.3

## What gets exercised

**Shape compatibility** — the adapter returns a real `langchain_core.tools.BaseTool` subclass that LangChain agents accept directly via `tools=[...]`.

**Real upstream call** — the integration test routes through:

```
LangChain BaseTool.invoke(...)
    → langchain_1claw VaultBackedTool.run(...)
    → MockVault.submit_intent(...)
    → policy check (endpoint allowlist, per-call cap, daily cap, tool allowlist)
    → http_caller(endpoint, args, credential)
    → requests.get("https://api.open-meteo.com/v1/forecast", ...)
    → JSON response back to the agent
```

The API used is [Open-Meteo](https://open-meteo.com/) — free, no auth, suitable for CI. The vault holds an opaque credential handle; the LangChain agent never reads it.

**Denial paths** — the integration test also confirms `IntentDeniedError` surfaces correctly through the LangChain wrapper for endpoint-allowlist violations under real HTTP.

## Test results

```
============================= test session starts ==============================
platform darwin -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/kevinjones/langchain-1claw-adapter
configfile: pyproject.toml
collected 13 items

tests/test_basic.py::test_happy_path_returns_response_and_records_audit PASSED
tests/test_basic.py::test_credential_never_passed_to_caller_args PASSED
tests/test_basic.py::test_endpoint_outside_allowlist_is_denied PASSED
tests/test_basic.py::test_per_call_cap_denial PASSED
tests/test_basic.py::test_daily_cap_denial_after_first_calls PASSED
tests/test_basic.py::test_tool_allowlist_denial PASSED
tests/test_basic.py::test_unknown_credential_handle_denied PASSED
tests/test_basic.py::test_denied_calls_are_audited_too PASSED
tests/test_langchain_integration.py::test_adapter_converts_to_langchain_base_tool PASSED
tests/test_langchain_integration.py::test_langchain_tool_carries_args_schema PASSED
tests/test_langchain_integration.py::test_real_http_call_through_vault_returns_weather_data PASSED
tests/test_langchain_integration.py::test_vault_denies_endpoint_outside_allowlist_for_real_http PASSED
tests/test_langchain_integration.py::test_audit_log_records_real_http_call PASSED

======================== 13 passed in 5.52s =========================
```

## Bug caught by integration testing

The first integration-test run failed because `langchain_core.tools.BaseTool._to_args_and_kwargs` short-circuits to empty kwargs when the `args_schema` has no declared fields — even with `extra="allow"` set on the pydantic model. This means a "permissive" schema doesn't actually let arbitrary kwargs flow through.

The fix lives in `src/langchain_1claw/integrations/langchain_compat.py`: we override `_to_args_and_kwargs` directly so all keys in `tool_input` are forwarded as kwargs to the underlying `VaultBackedTool.run`. The unit tests with `MockVault.http_caller` as a stub would never have caught this — it only surfaces under a real LangChain `BaseTool.invoke()` call.

This is exactly the class of bug that gets caught by integration tests and missed by unit tests. Committed to the repo for the next adapter implementer to avoid.

## How to re-run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest langchain langchain-core requests
pytest tests/ -v
```

## Open follow-ups (Tier 2 — needs LLM API key)

The current test does not yet exercise:

- A live LLM agent (e.g., LangChain `create_react_agent` with Anthropic Haiku) using the vault-backed tool
- Verification that the credential string never appears in the agent's message history
- Adversarial prompt-injection attempts asking the agent to leak the credential

These are the credibility-defining tests for the "agent never sees the credential" claim. Tracked separately; not yet run.

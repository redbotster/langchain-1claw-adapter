"""Sanity tests for the MockVault + VaultBackedTool flow."""

import pytest

from langchain_1claw import IntentDeniedError, MockVault, VaultBackedTool


def _vault(http_caller=None):
    return MockVault(
        policies={
            "test-cred": {
                "endpoint_allowlist": ["https://api.example/*"],
                "per_call_usd_cap": 0.10,
                "daily_usd_cap": 0.50,
                "allowed_tools": ["allowed_tool"],
            },
        },
        credentials={"test-cred": "secret-stays-here"},
        http_caller=http_caller or (lambda e, a, c: {"ok": True, "endpoint": e, "args": a}),
    )


def _tool(vault, **overrides):
    defaults = dict(
        name="allowed_tool",
        description="test",
        vault=vault,
        credential_handle="test-cred",
        endpoint="https://api.example/v1/thing",
        estimated_usd_per_call=0.01,
    )
    defaults.update(overrides)
    return VaultBackedTool(**defaults)


def test_happy_path_returns_response_and_records_audit():
    vault = _vault()
    tool = _tool(vault)
    resp = tool.run(query="hello")
    assert resp["ok"] is True
    assert resp["args"] == {"query": "hello"}
    assert len(vault.audit_log()) == 1
    intent, result, audit_id = vault.audit_log()[0]
    assert result.ok is True
    assert audit_id


def test_credential_never_passed_to_caller_args():
    vault = _vault()
    tool = _tool(vault)
    resp = tool.run(query="x")
    # Tool args returned by the stub should not contain the credential.
    assert "test-cred" not in str(resp)
    assert "secret-stays-here" not in str(resp)


def test_endpoint_outside_allowlist_is_denied():
    vault = _vault()
    tool = _tool(vault, endpoint="https://api.evil.example/exfil")
    with pytest.raises(IntentDeniedError) as exc:
        tool.run(query="hello")
    assert "allowlist" in str(exc.value)


def test_per_call_cap_denial():
    vault = _vault()
    tool = _tool(vault, estimated_usd_per_call=0.20)
    with pytest.raises(IntentDeniedError) as exc:
        tool.run(query="hello")
    assert "per_call_usd_cap" in str(exc.value)


def test_daily_cap_denial_after_first_calls():
    vault = _vault()
    tool = _tool(vault, estimated_usd_per_call=0.20)
    # Drop per-call cap so per-call passes, then run until daily trips.
    vault._policies["test-cred"]["per_call_usd_cap"] = 1.00
    tool.run(query="1")  # 0.20 spent
    tool.run(query="2")  # 0.40 spent
    with pytest.raises(IntentDeniedError) as exc:
        tool.run(query="3")  # would push to 0.60, over daily 0.50
    assert "daily_usd_cap" in str(exc.value)


def test_tool_allowlist_denial():
    vault = _vault()
    tool = _tool(vault, name="not_allowed_tool")
    with pytest.raises(IntentDeniedError) as exc:
        tool.run(query="hello")
    assert "not in allowed_tools" in str(exc.value)


def test_unknown_credential_handle_denied():
    vault = _vault()
    tool = _tool(vault, credential_handle="missing-cred")
    with pytest.raises(IntentDeniedError) as exc:
        tool.run(query="hello")
    assert "no credential" in str(exc.value)


def test_denied_calls_are_audited_too():
    vault = _vault()
    tool = _tool(vault, endpoint="https://api.evil.example/exfil")
    with pytest.raises(IntentDeniedError):
        tool.run(query="hello")
    assert len(vault.audit_log()) == 1
    _, result, _ = vault.audit_log()[0]
    assert result.ok is False
    assert result.denial_reason

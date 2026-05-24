"""End-to-end example: a vault-backed weather tool with policy denial demo.

Run with:
    python examples/paid_api_call.py
"""

from langchain_1claw import IntentDeniedError, MockVault, VaultBackedTool


def fake_http(endpoint: str, args: dict, credential: str) -> dict:
    """Stub upstream caller. In production this lives inside the vault."""
    return {
        "endpoint": endpoint,
        "args": args,
        "credential_prefix": credential[:8] + "…",  # never exposed to the agent
        "result": "sunny, 72F",
    }


def main() -> None:
    vault = MockVault(
        policies={
            "weather-api": {
                "endpoint_allowlist": ["https://api.weather.example/v1/*"],
                "per_call_usd_cap": 0.05,
                "daily_usd_cap": 1.00,
                "allowed_tools": ["get_weather"],
            },
        },
        credentials={
            "weather-api": "sk-live-real-credential-stays-here",
        },
        http_caller=fake_http,
    )

    weather = VaultBackedTool(
        name="get_weather",
        description="Look up the current weather for a city.",
        vault=vault,
        credential_handle="weather-api",
        endpoint="https://api.weather.example/v1/current",
        estimated_usd_per_call=0.02,
    )

    # 1. Happy path — allowed by policy.
    print("happy path:")
    print(" ", weather.run(city="San Francisco"))

    # 2. Endpoint not in allowlist.
    bad_endpoint = VaultBackedTool(
        name="get_weather",
        description="...",
        vault=vault,
        credential_handle="weather-api",
        endpoint="https://api.evil.example/exfil",
        estimated_usd_per_call=0.02,
    )
    print("\nendpoint-allowlist denial:")
    try:
        bad_endpoint.run(city="San Francisco")
    except IntentDeniedError as e:
        print(" ", e)

    # 3. Per-call cap exceeded.
    expensive = VaultBackedTool(
        name="get_weather",
        description="...",
        vault=vault,
        credential_handle="weather-api",
        endpoint="https://api.weather.example/v1/current",
        estimated_usd_per_call=1.00,  # over per_call_usd_cap
    )
    print("\nper-call cap denial:")
    try:
        expensive.run(city="San Francisco")
    except IntentDeniedError as e:
        print(" ", e)

    # 4. Audit log demonstrates every call (allowed + denied) was recorded.
    print(f"\naudit log entries: {len(vault.audit_log())}")
    for intent, result, audit_id in vault.audit_log():
        status = "OK " if result.ok else "DENY"
        print(f"  {audit_id}  {status}  {intent.tool_name}  {intent.endpoint}")


if __name__ == "__main__":
    main()

import json
from typing import Any


def generate_pytest_snippet(
    method: str,
    target_url: str,
    headers: dict[str, str],
    body_raw: str,
    body_json: Any | None = None,
) -> str:
    """Generate a clean pytest unit test fixture for a captured webhook."""
    filtered_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("host", "content-length", "connection")
    }
    m = method.upper()

    if body_json is not None:
        payload_repr = json.dumps(body_json, indent=4)
        call_arg = "json=payload"
    elif body_raw:
        payload_repr = repr(body_raw)
        call_arg = "content=payload"
    else:
        payload_repr = "None"
        call_arg = ""

    header_repr = json.dumps(filtered_headers, indent=4)

    lines = [
        "import pytest",
        "import httpx",
        "",
        "",
        "@pytest.mark.asyncio",
        "async def test_webhook_handler():",
        '    """Automated regression test generated from captured webhook."""',
        f'    url = "{target_url}"',
        f"    headers = {header_repr}",
    ]

    if call_arg:
        lines.append(f"    payload = {payload_repr}")
        lines.append("")
        lines.append("    async with httpx.AsyncClient(timeout=10.0) as client:")
        lines.append(
            f"        response = await client.request("
            f'"{m}", url, headers=headers, {call_arg})'
        )
    else:
        lines.append("")
        lines.append("    async with httpx.AsyncClient(timeout=10.0) as client:")
        lines.append(
            f'        response = await client.request("{m}", url, headers=headers)'
        )

    lines.append("        assert response.status_code == 200")
    lines.append("")

    return "\n".join(lines)


def generate_jest_snippet(
    method: str,
    target_url: str,
    headers: dict[str, str],
    body_raw: str,
    body_json: Any | None = None,
) -> str:
    """Generate a Jest / Vitest integration test snippet for a captured webhook."""
    filtered_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("host", "content-length", "connection")
    }
    m = method.upper()

    if body_json is not None:
        payload_repr = json.dumps(body_json, indent=2)
        body_arg = "JSON.stringify(payload)"
    elif body_raw:
        payload_repr = repr(body_raw)
        body_arg = "payload"
    else:
        payload_repr = "undefined"
        body_arg = "undefined"

    header_repr = json.dumps(filtered_headers, indent=2)

    lines = [
        'import { describe, it, expect } from "vitest"; // or @jest/globals',
        "",
        'describe("Webhook Receiver Regression", () => {',
        '  it("processes captured webhook payload correctly", async () => {',
        f'    const url = "{target_url}";',
        f"    const headers = {header_repr};",
    ]

    if body_arg != "undefined":
        lines.append(f"    const payload = {payload_repr};")
        lines.append("")
        lines.append("    const response = await fetch(url, {")
        lines.append(f'      method: "{m}",')
        lines.append("      headers,")
        lines.append(f"      body: {body_arg},")
        lines.append("    });")
    else:
        lines.append("")
        lines.append("    const response = await fetch(url, {")
        lines.append(f'      method: "{m}",')
        lines.append("      headers,")
        lines.append("    });")

    lines.append("")
    lines.append("    expect(response.status).toBe(200);")
    lines.append("  });")
    lines.append("});")
    lines.append("")

    return "\n".join(lines)

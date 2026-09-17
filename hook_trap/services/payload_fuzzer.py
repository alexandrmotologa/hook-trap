import copy
import json
import logging
import time
import uuid
from typing import Any

import httpx

from hook_trap.models import (
    FuzzingConfig,
    FuzzMutationCase,
    FuzzMutationType,
    FuzzResilienceGrade,
    FuzzRunResult,
    FuzzTestResult,
)
from hook_trap.ws_manager import ConnectionManager, ws_manager

logger = logging.getLogger("hook_trap.payload_fuzzer")

SIGNATURE_HEADERS = {
    "stripe-signature",
    "x-hub-signature-256",
    "x-hub-signature",
    "x-shopify-hmac-sha256",
    "svix-signature",
    "webhook-signature",
    "x-signature",
}


def _get_key_paths(obj: Any, prefix: list[str] | None = None) -> list[list[str]]:
    """Collect all nested dictionary key paths from a JSON structure."""
    if prefix is None:
        prefix = []
    paths: list[list[str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current = [*prefix, k]
            paths.append(current)
            if isinstance(v, dict | list):
                paths.extend(_get_key_paths(v, current))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, dict | list):
                paths.extend(_get_key_paths(item, [*prefix, str(i)]))
    return paths


def _set_path_value(obj: Any, path: list[str], value: Any) -> None:
    """Set the value at a nested path."""
    curr = obj
    for p in path[:-1]:
        if isinstance(curr, dict):
            curr = curr[p]
        elif isinstance(curr, list):
            curr = curr[int(p)]
    last_key = path[-1]
    if isinstance(curr, dict):
        curr[last_key] = value
    elif isinstance(curr, list):
        curr[int(last_key)] = value


def _delete_path(obj: Any, path: list[str]) -> None:
    """Delete a key at a nested path."""
    curr = obj
    for p in path[:-1]:
        if isinstance(curr, dict):
            curr = curr[p]
        elif isinstance(curr, list):
            curr = curr[int(p)]
    last_key = path[-1]
    if isinstance(curr, dict) and last_key in curr:
        del curr[last_key]
    elif isinstance(curr, list) and 0 <= int(last_key) < len(curr):
        curr.pop(int(last_key))


def _get_path_value(obj: Any, path: list[str]) -> Any:
    """Get the value at a nested path."""
    curr = obj
    for p in path:
        if isinstance(curr, dict):
            curr = curr[p]
        elif isinstance(curr, list):
            curr = curr[int(p)]
    return curr


class PayloadFuzzer:
    """Service that mutates payloads and audits webhook receiver resilience."""

    def __init__(self, connection_manager: ConnectionManager | None = None) -> None:
        self._ws_manager = connection_manager or ws_manager

    def generate_mutations(
        self,
        payload_raw: str,
        headers: dict[str, str] | None = None,
        config: FuzzingConfig | None = None,
    ) -> list[FuzzMutationCase]:
        """Generate deterministic payload mutations according to fuzzing configuration."""
        cfg = config or FuzzingConfig()
        enabled = set(cfg.enabled_mutations)
        hdrs = dict(headers or {})
        cases: list[FuzzMutationCase] = []

        is_json = False
        parsed_json = None
        try:
            parsed_json = json.loads(payload_raw)
            is_json = True
        except Exception:
            is_json = False

        # 1. Missing Key Mutations
        if is_json and FuzzMutationType.MISSING_KEY in enabled:
            paths = _get_key_paths(parsed_json)
            for path in paths:
                if len(cases) >= cfg.max_mutations:
                    break
                cloned = copy.deepcopy(parsed_json)
                _delete_path(cloned, path)
                field_str = ".".join(path)
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name=f"omit_{field_str}",
                        mutation_type=FuzzMutationType.MISSING_KEY,
                        field_path=field_str,
                        description=f"Omit field '{field_str}' to test schema validation.",
                        mutated_payload=json.dumps(cloned),
                        mutated_headers=hdrs,
                    )
                )

        # 2. Null Injection Mutations
        if is_json and FuzzMutationType.NULL_INJECTION in enabled:
            paths = _get_key_paths(parsed_json)
            for path in paths:
                if len(cases) >= cfg.max_mutations:
                    break
                cloned = copy.deepcopy(parsed_json)
                _set_path_value(cloned, path, None)
                field_str = ".".join(path)
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name=f"null_{field_str}",
                        mutation_type=FuzzMutationType.NULL_INJECTION,
                        field_path=field_str,
                        description=f"Inject null into required field '{field_str}'.",
                        mutated_payload=json.dumps(cloned),
                        mutated_headers=hdrs,
                    )
                )

        # 3. Type Confusion Mutations
        if is_json and FuzzMutationType.TYPE_CONFUSION in enabled:
            paths = _get_key_paths(parsed_json)
            for path in paths:
                if len(cases) >= cfg.max_mutations:
                    break
                try:
                    val = _get_path_value(parsed_json, path)
                except Exception:
                    continue

                if isinstance(val, bool):
                    confused: Any = "invalid_boolean_string"
                elif isinstance(val, int | float):
                    confused = True
                elif isinstance(val, str):
                    confused = 99999
                elif isinstance(val, dict):
                    confused = ["confused_array_item"]
                elif isinstance(val, list):
                    confused = {"confused_dict": True}
                else:
                    confused = 0

                cloned = copy.deepcopy(parsed_json)
                _set_path_value(cloned, path, confused)
                field_str = ".".join(path)
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name=f"type_confuse_{field_str}",
                        mutation_type=FuzzMutationType.TYPE_CONFUSION,
                        field_path=field_str,
                        description=(
                            f"Type confusion for '{field_str}': swapped "
                            f"{type(val).__name__} for {type(confused).__name__}."
                        ),
                        mutated_payload=json.dumps(cloned),
                        mutated_headers=hdrs,
                    )
                )

        # 4. Corrupted Webhook Signatures
        if FuzzMutationType.CORRUPTED_SIGNATURE in enabled and len(cases) < cfg.max_mutations:
            found_sig = False
            for k, v in hdrs.items():
                if k.lower() in SIGNATURE_HEADERS:
                    found_sig = True
                    corrupted_hdrs = dict(hdrs)
                    if v and len(v) > 3:
                        last_ch = v[-1]
                        replacement = "0" if last_ch != "0" else "1"
                        corrupted_hdrs[k] = v[:-1] + replacement
                    else:
                        corrupted_hdrs[k] = "corrupted_signature_value"

                    cases.append(
                        FuzzMutationCase(
                            case_id=str(uuid.uuid4())[:8],
                            mutation_name=f"corrupt_{k.lower()}",
                            mutation_type=FuzzMutationType.CORRUPTED_SIGNATURE,
                            field_path=f"header:{k}",
                            description=(
                                f"Corrupt signature in header '{k}' to verify "
                                "cryptographic verification."
                            ),
                            mutated_payload=payload_raw,
                            mutated_headers=corrupted_hdrs,
                        )
                    )

            if not found_sig and len(cases) < cfg.max_mutations:
                # Inject an invalid signature header
                injected_hdrs = dict(hdrs)
                injected_hdrs["X-Hub-Signature-256"] = "sha256=corrupted_invalid_signature_hash_000"
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name="invalid_x_hub_signature",
                        mutation_type=FuzzMutationType.CORRUPTED_SIGNATURE,
                        field_path="header:X-Hub-Signature-256",
                        description=(
                            "Inject forged X-Hub-Signature-256 to test signature enforcement."
                        ),
                        mutated_payload=payload_raw,
                        mutated_headers=injected_hdrs,
                    )
                )

        # 5. Malformed JSON Mutations
        if FuzzMutationType.MALFORMED_JSON in enabled and len(cases) < cfg.max_mutations:
            raw_stripped = payload_raw.strip()
            # Trailing comma before close
            if raw_stripped.endswith("}"):
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name="malformed_trailing_comma",
                        mutation_type=FuzzMutationType.MALFORMED_JSON,
                        field_path=None,
                        description="Inject illegal trailing comma into JSON object.",
                        mutated_payload=raw_stripped[:-1] + ', "extra": 1,}',
                        mutated_headers=hdrs,
                    )
                )

            if len(cases) < cfg.max_mutations:
                # Truncated JSON / unclosed brace
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name="malformed_unclosed_brace",
                        mutation_type=FuzzMutationType.MALFORMED_JSON,
                        field_path=None,
                        description="Truncate closing brace from JSON.",
                        mutated_payload=raw_stripped[:-1] if raw_stripped else "{",
                        mutated_headers=hdrs,
                    )
                )

            if len(cases) < cfg.max_mutations:
                # Non-JSON syntax garbage
                cases.append(
                    FuzzMutationCase(
                        case_id=str(uuid.uuid4())[:8],
                        mutation_name="malformed_syntax_garbage",
                        mutation_type=FuzzMutationType.MALFORMED_JSON,
                        field_path=None,
                        description="Inject broken syntax tokens into payload.",
                        mutated_payload=f"<<MALFORMED_PAYLOAD>>{payload_raw}",
                        mutated_headers=hdrs,
                    )
                )

        return cases[: cfg.max_mutations]

    def evaluate_resilience(
        self,
        status_code: int | None,
        error: str | None = None,
    ) -> tuple[str, bool, str]:
        """
        Evaluate target response code for resilience against mutated inputs.
        400/401/403/422: PASSED (Graceful validation error)
        500/502/503/504: VULNERABLE (Unhandled crash)
        200..299: ACCEPTED (Warning: accepted malformed input)
        Connection/Timeout: VULNERABLE
        """
        if status_code in (400, 401, 403, 422):
            return (
                FuzzResilienceGrade.PASSED,
                True,
                f"Receiver safely rejected mutation with HTTP {status_code}.",
            )
        if status_code in (500, 502, 503, 504):
            return (
                FuzzResilienceGrade.VULNERABLE,
                False,
                f"VULNERABLE: Receiver crashed with unhandled HTTP {status_code}.",
            )
        if status_code is not None and 200 <= status_code < 300:
            return (
                FuzzResilienceGrade.ACCEPTED,
                False,
                f"ACCEPTED: Endpoint accepted invalid payload with HTTP {status_code}.",
            )
        if error:
            return (
                FuzzResilienceGrade.VULNERABLE,
                False,
                f"VULNERABLE: Endpoint threw connection error or crashed: {error}",
            )
        return (
            FuzzResilienceGrade.ERROR,
            False,
            f"Unexpected HTTP status: {status_code}",
        )

    async def run_fuzz_tests(
        self,
        target_url: str,
        payload_raw: str,
        headers: dict[str, str] | None = None,
        method: str = "POST",
        config: FuzzingConfig | None = None,
        timeout: float = 5.0,
        channel_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> FuzzRunResult:
        """Execute fuzz mutations against target URL and compile resilience score."""
        cfg = config or FuzzingConfig()
        cases = self.generate_mutations(payload_raw, headers, cfg)

        results: list[FuzzTestResult] = []


        for case in cases:
            headers_to_send = {
                k: v
                for k, v in case.mutated_headers.items()
                if k.lower() not in {"host", "content-length", "connection"}
            }
            body_bytes = case.mutated_payload.encode("utf-8")

            status_code: int | None = None
            response_body = ""
            error_msg: str | None = None

            start_time = time.perf_counter()
            try:
                if client is not None:
                    resp = await client.request(
                        method=method,
                        url=target_url,
                        content=body_bytes,
                        headers=headers_to_send,
                    )
                    status_code = resp.status_code
                    response_body = resp.text[:2048]
                else:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_c:
                        resp = await http_c.request(
                            method=method,
                            url=target_url,
                            content=body_bytes,
                            headers=headers_to_send,
                        )
                        status_code = resp.status_code
                        response_body = resp.text[:2048]
            except httpx.TimeoutException:
                error_msg = f"Timed out after {timeout}s"
            except httpx.ConnectError:
                error_msg = "Connection refused or failed"
            except Exception as exc:
                error_msg = str(exc)

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            resilience_grade, passed, desc = self.evaluate_resilience(status_code, error_msg)

            test_res = FuzzTestResult(
                case_id=case.case_id,
                mutation_name=case.mutation_name,
                mutation_type=case.mutation_type,
                field_path=case.field_path,
                description=desc,
                status_code=status_code,
                latency_ms=latency_ms,
                resilience_grade=resilience_grade,
                passed=passed,
                response_body=response_body,
                error=error_msg,
            )
            results.append(test_res)

            if channel_id:
                await self._ws_manager.broadcast(
                    channel_id,
                    {
                        "event": "fuzz_case_completed",
                        "data": test_res.model_dump(),
                    },
                )

        passed_count = sum(1 for r in results if r.resilience_grade == FuzzResilienceGrade.PASSED)
        vulnerable_count = sum(
            1 for r in results if r.resilience_grade == FuzzResilienceGrade.VULNERABLE
        )
        accepted_count = sum(
            1 for r in results if r.resilience_grade == FuzzResilienceGrade.ACCEPTED
        )
        error_count = sum(1 for r in results if r.resilience_grade == FuzzResilienceGrade.ERROR)
        all_passed = vulnerable_count == 0 and accepted_count == 0 and error_count == 0

        summary = (
            f"Fuzz run completed across {len(results)} cases. "
            f"Passed: {passed_count}, Vulnerable (5xx/crashes): {vulnerable_count}, "
            f"Accepted invalid: {accepted_count}, Errors: {error_count}."
        )

        return FuzzRunResult(
            target_url=target_url,
            total_cases=len(results),
            passed_count=passed_count,
            vulnerable_count=vulnerable_count,
            accepted_count=accepted_count,
            error_count=error_count,
            all_passed=all_passed,
            summary=summary,
            cases=results,
        )


# Singleton instance
payload_fuzzer = PayloadFuzzer()

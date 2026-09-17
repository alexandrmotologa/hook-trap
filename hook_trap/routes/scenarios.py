import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hook_trap.config import settings
from hook_trap.database import (
    add_scenario_step,
    create_scenario,
    delete_scenario,
    delete_scenario_step,
    get_channel_config,
    get_scenario,
    get_webhook_request_detail,
    list_scenarios_by_channel,
    update_scenario,
)
from hook_trap.models import (
    FuzzMutationCase,
    FuzzRunRequest,
    FuzzRunResult,
    Scenario,
    ScenarioCreate,
    ScenarioRunRequest,
    ScenarioRunResult,
    ScenarioStep,
    ScenarioStepCreate,
    ScenarioUpdate,
)
from hook_trap.services.payload_fuzzer import payload_fuzzer
from hook_trap.services.scenario_runner import scenario_runner

logger = logging.getLogger("hook_trap.scenarios")

router = APIRouter(tags=["Scenarios & Fuzzing"])


@router.get("/api/scenarios", response_model=list[Scenario])
async def list_scenarios(channel_id: str = Query(...)) -> list[dict[str, Any]]:
    """Retrieve all saved scenarios for a specific channel."""
    return await list_scenarios_by_channel(settings.db_path, channel_id)


@router.post("/api/scenarios", response_model=Scenario, status_code=201)
async def create_new_scenario(payload: ScenarioCreate) -> dict[str, Any]:
    """Create a new webhook scenario with optional initial steps."""
    scenario_data = {
        "channel_id": payload.channel_id,
        "name": payload.name,
        "description": payload.description,
        "target_url": payload.target_url,
        "delay_between_steps_ms": payload.delay_between_steps_ms,
    }
    steps_data = [s.model_dump() for s in payload.steps] if payload.steps else None
    created = await create_scenario(settings.db_path, scenario_data, steps=steps_data)
    return created


@router.get("/api/scenarios/{scenario_id}", response_model=Scenario)
async def get_scenario_by_id(scenario_id: str) -> dict[str, Any]:
    """Get full scenario details including all ordered execution steps."""
    scenario = await get_scenario(settings.db_path, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    return scenario


@router.put("/api/scenarios/{scenario_id}", response_model=Scenario)
async def update_existing_scenario(scenario_id: str, payload: ScenarioUpdate) -> dict[str, Any]:
    """Update scenario attributes and optionally replace steps."""
    data = payload.model_dump(exclude_unset=True)
    steps_data = None
    if "steps" in data and data["steps"] is not None:
        steps_data = [s.model_dump() for s in payload.steps]  # type: ignore[union-attr]
        data.pop("steps")

    updated = await update_scenario(settings.db_path, scenario_id, data, steps=steps_data)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    return updated


@router.delete("/api/scenarios/{scenario_id}")
async def delete_existing_scenario(scenario_id: str) -> dict[str, Any]:
    """Delete a scenario and all its associated steps."""
    success = await delete_scenario(settings.db_path, scenario_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    return {"status": "deleted", "id": scenario_id}


@router.post("/api/scenarios/{scenario_id}/steps", response_model=ScenarioStep, status_code=201)
async def add_step_to_scenario(scenario_id: str, payload: ScenarioStepCreate) -> dict[str, Any]:
    """Append a new step to an existing scenario."""
    scenario = await get_scenario(settings.db_path, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    created_step = await add_scenario_step(settings.db_path, scenario_id, payload.model_dump())
    return created_step


@router.delete("/api/scenarios/{scenario_id}/steps/{step_id}")
async def delete_step_from_scenario(scenario_id: str, step_id: str) -> dict[str, Any]:
    """Remove a step from a scenario."""
    success = await delete_scenario_step(settings.db_path, scenario_id, step_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Step '{step_id}' not found in scenario")
    return {"status": "deleted", "step_id": step_id}


@router.post("/api/scenarios/{scenario_id}/run", response_model=ScenarioRunResult)
async def run_scenario(
    scenario_id: str,
    payload: ScenarioRunRequest | None = None,
) -> ScenarioRunResult:
    """Execute a scenario sequence runner with latency tracking and assertions."""
    target_url_override = payload.target_url if payload else None
    try:
        return await scenario_runner.run(
            db_path=settings.db_path,
            scenario_id=scenario_id,
            target_url_override=target_url_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scenario execution failed: {exc}")


# --- Payload Fuzzing Endpoints ---


@router.post("/api/scenarios/fuzz/generate", response_model=list[FuzzMutationCase])
async def generate_fuzz_mutations(payload: FuzzRunRequest) -> list[FuzzMutationCase]:
    """Generate mutation test cases from an input webhook payload without executing them."""
    return payload_fuzzer.generate_mutations(
        payload_raw=payload.payload_raw,
        headers=payload.headers,
        config=payload.config,
    )


@router.post("/api/scenarios/fuzz/run", response_model=FuzzRunResult)
async def run_fuzz_test_suite(payload: FuzzRunRequest) -> FuzzRunResult:
    """Execute the full mutation fuzzing test suite against a target URL."""
    return await payload_fuzzer.run_fuzz_tests(
        target_url=payload.target_url,
        payload_raw=payload.payload_raw,
        headers=payload.headers,
        method=payload.method,
        config=payload.config,
        timeout=payload.timeout,
        channel_id=payload.channel_id,
    )


@router.post(
    "/api/channels/{channel_id}/requests/{request_id}/fuzz",
    response_model=FuzzRunResult,
)
async def fuzz_captured_request(
    channel_id: str,
    request_id: str,
    payload: ScenarioRunRequest | None = None,
) -> FuzzRunResult:
    """Trigger automated payload fuzzing directly from an existing captured webhook request."""
    req_detail = await get_webhook_request_detail(settings.db_path, channel_id, request_id)
    if not req_detail:
        raise HTTPException(status_code=404, detail="Captured request not found")

    target_url = payload.target_url if payload and payload.target_url else None
    if not target_url:
        cfg = await get_channel_config(settings.db_path, channel_id)
        target_url = (
            cfg.get("auto_forward_url")
            if cfg
            else None
        ) or settings.default_auto_forward_url

    if not target_url:
        raise HTTPException(
            status_code=400,
            detail="No target URL provided or configured for this channel.",
        )

    return await payload_fuzzer.run_fuzz_tests(
        target_url=target_url,
        payload_raw=req_detail.get("body_raw", ""),
        headers=req_detail.get("headers", {}),
        method=req_detail.get("method", "POST"),
        channel_id=channel_id,
    )

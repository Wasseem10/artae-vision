import asyncio

from fastapi.testclient import TestClient
from video_intelligence_api.calibration import SCENARIOS
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.models import Zone
from video_intelligence_api.rule_compiler import (
    FULL_FRAME_ZONE_NAME,
    compile_rule_prompt,
)

PERSON_PRESENCE_PROMPT = "Alert me when a person is present in Full frame (automatic)."


def test_catalog_prompts_compile_to_the_declared_temporal_mode() -> None:
    settings = ApiSettings(
        environment="test",
        database_url="sqlite+aiosqlite://",
        agent_key="test-agent-key-123456789",
        dashboard_key="test-dashboard-key-12345",
        rule_compiler_provider="deterministic",
    )
    geometry = Zone(
        id="full-frame-zone",
        camera_id="camera-1",
        name=FULL_FRAME_ZONE_NAME,
        points=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
    )

    for scenario in SCENARIOS:
        result = asyncio.run(compile_rule_prompt(settings, scenario.prompt, [geometry]))
        assert result.compiled_rule is not None, scenario.key
        execution = plan_job(result.compiled_rule, scenario.prompt)
        assert execution.support.temporal_mode == scenario.temporal_mode, scenario.key


def _camera(client: TestClient) -> dict:
    return client.post(
        "/api/v1/cameras",
        json={"name": "calibration-camera", "source_uri": "0"},
    ).json()


def _create_person_presence(
    client: TestClient,
    camera_id: str,
    *,
    name: str,
    variant: str,
    source_kind: str = "controlled",
    tags: list[str] | None = None,
) -> dict:
    expected = (
        [{"start_seconds": 1, "end_seconds": 3, "label": "event"}]
        if variant == "positive"
        else []
    )
    response = client.post(
        "/api/v1/evaluations",
        json={
            "name": name,
            "camera_id": camera_id,
            "source_uri": f"fixtures/{name}.mp4",
            "prompt": PERSON_PRESENCE_PROMPT,
            "duration_seconds": 5,
            "expected_intervals": expected,
            "scenario_key": "person_presence",
            "scenario_variant": variant,
            "source_kind": source_kind,
            "environment_tags": tags or ["normal light"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _score(client: TestClient, evaluation: dict) -> None:
    response = client.post(
        f"/api/v1/evaluations/{evaluation['id']}/score",
        json={
            "predicted_intervals": evaluation["expected_intervals"],
            "provider_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "input_price_per_million_usd": 0,
            "output_price_per_million_usd": 0,
        },
    )
    assert response.status_code == 200, response.text


def test_calibration_catalog_discloses_automated_and_manual_metrics(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/calibration/scenarios")

    assert response.status_code == 200
    scenarios = {item["key"]: item for item in response.json()}
    assert len(scenarios) == 8
    assert scenarios["ppe_removal"]["temporal_mode"] == "transition"
    assert scenarios["ppe_removal"]["visual_skills"] == ["ppe_compliance"]
    assert scenarios["serial_number_ocr"]["metric_family"] == "structured_text"
    assert scenarios["serial_number_ocr"]["automation_status"] == "manual_only"


def test_calibration_readiness_excludes_synthetic_and_requires_variants(
    api_client: TestClient,
) -> None:
    camera = _camera(api_client)
    synthetic = _create_person_presence(
        api_client,
        camera["id"],
        name="synthetic-positive",
        variant="positive",
        source_kind="synthetic",
    )
    _score(api_client, synthetic)

    initial = api_client.get("/api/v1/calibration/readiness").json()
    person_initial = next(
        item for item in initial["scenarios"] if item["key"] == "person_presence"
    )
    assert initial["real_world_accuracy_claimable"] is False
    assert initial["credible_scored_clips"] == 0
    assert initial["public_benchmark_clips"] == 0
    assert person_initial["synthetic_pipeline_checks"] == 1

    evaluations = [
        _create_person_presence(
            api_client,
            camera["id"],
            name="positive-normal",
            variant="positive",
        ),
        _create_person_presence(
            api_client,
            camera["id"],
            name="positive-low-light",
            variant="positive",
            tags=["low light"],
        ),
        _create_person_presence(
            api_client,
            camera["id"],
            name="negative-normal",
            variant="negative",
        ),
        _create_person_presence(
            api_client,
            camera["id"],
            name="negative-occluded",
            variant="negative",
            tags=["partial occlusion"],
        ),
    ]
    for evaluation in evaluations:
        _score(api_client, evaluation)

    readiness = api_client.get("/api/v1/calibration/readiness").json()
    person = next(
        item for item in readiness["scenarios"] if item["key"] == "person_presence"
    )
    assert readiness["status"] == "collecting"
    assert readiness["real_world_accuracy_claimable"] is False
    assert person["status"] == "ready"
    assert person["credible_scored_clips"] == 4
    assert person["positive_clips"] == 2
    assert person["negative_clips"] == 2
    assert person["challenging_clips"] == 2
    assert person["site_specific_clips"] == 4
    assert person["site_specific_ready"] is True
    assert readiness["site_specific_ready_scenarios"] == 1


def test_public_benchmarks_are_credible_but_not_site_specific(
    api_client: TestClient,
) -> None:
    camera = _camera(api_client)
    benchmark = _create_person_presence(
        api_client,
        camera["id"],
        name="licensed-benchmark",
        variant="negative",
        source_kind="public_benchmark",
        tags=["camera motion"],
    )
    _score(api_client, benchmark)

    readiness = api_client.get("/api/v1/calibration/readiness").json()
    person = next(
        item for item in readiness["scenarios"] if item["key"] == "person_presence"
    )
    assert readiness["public_benchmark_clips"] == 1
    assert readiness["site_specific_clips"] == 0
    assert readiness["site_specific_accuracy_claimable"] is False
    assert readiness["site_specific_ready_scenarios"] == 0
    assert person["public_benchmark_clips"] == 1
    assert person["site_specific_clips"] == 0
    assert person["site_specific_ready"] is False


def test_calibration_evaluation_metadata_is_validated(api_client: TestClient) -> None:
    camera = _camera(api_client)
    missing_metadata = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "invalid-calibration",
            "camera_id": camera["id"],
            "source_uri": "fixtures/invalid.mp4",
            "prompt": PERSON_PRESENCE_PROMPT,
            "duration_seconds": 5,
            "expected_intervals": [{"start_seconds": 1, "end_seconds": 3}],
            "scenario_key": "person_presence",
        },
    )
    assert missing_metadata.status_code == 422
    assert "source kind" in missing_metadata.json()["detail"]

    wrong_prompt = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "wrong-prompt",
            "camera_id": camera["id"],
            "source_uri": "fixtures/wrong.mp4",
            "prompt": "Alert me when a dog is present in Full frame (automatic).",
            "duration_seconds": 5,
            "expected_intervals": [{"start_seconds": 1, "end_seconds": 3}],
            "scenario_key": "person_presence",
            "scenario_variant": "positive",
            "source_kind": "controlled",
        },
    )
    assert wrong_prompt.status_code == 422
    assert "prompt must match" in wrong_prompt.json()["detail"]

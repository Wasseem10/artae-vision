import base64
import io
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image
from video_intelligence_api.browser_vision import (
    VisualDecision,
    decode_frame,
    normalize_conditions,
    normalize_decision,
    normalize_timing,
)
from video_intelligence_api.routes import browser_sessions


def frame():
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(out, format="JPEG")
    return {"at_seconds": 4, "jpeg": base64.b64encode(out.getvalue()).decode()}


def test_timing_requires_complete_frame_states_and_unambiguous_subject():
    decision = normalize_conditions(
        {
            "conditions": [
                {
                    "condition_index": 0,
                    "status": "no_match",
                    "summary": "Car is stationary.",
                    "frame_states": ["inactive", "active", "active", "inactive"],
                },
                {
                    "condition_index": 1,
                    "status": "match",
                    "summary": "Missing observations.",
                    "frame_states": ["active"],
                },
                {
                    "condition_index": 2,
                    "status": "match",
                    "summary": "Multiple similar cars.",
                    "subject_ambiguous": True,
                    "frame_states": ["active"] * 4,
                },
            ]
        },
        4,
        ["Car parked", "Person down", "Blue car parked"],
    )
    result = normalize_timing(decision, 4)
    assert result.status == "match"
    assert result.conditions[0].matched_frame_index == 1
    assert result.conditions[1].frame_states == ["uncertain"] * 4
    assert result.conditions[2].status == "uncertain"
    assert result.conditions[2].matched_frame_index is None


def test_detailed_public_budget_is_signed_and_refinement_does_not_send_alert(
    api_client, monkeypatch
):
    api_client.app.state.settings.strands_enabled = True
    browser_sessions._public_demo_starts.clear()
    browser_sessions._public_demo_checks.clear()
    calls = []

    def inspect(*args):
        calls.append(args)
        return VisualDecision(status="match", summary="Car visible."), {}

    monkeypatch.setattr(browser_sessions, "inspect_frames", inspect)

    async def forbidden_coordinator(*args, **kwargs):
        raise AssertionError("Boundary refinement must not emit another alert")

    monkeypatch.setattr(browser_sessions, "coordinate_incident", forbidden_coordinator)
    start = api_client.post(
        "/api/v1/browser-sessions/public-demo",
        json={"prompt": "Car parked", "detailed": True},
    ).json()
    assert start["max_checks"] == 32
    browser_sessions._public_demo_checks[start["id"]] = 4
    result = api_client.post(
        "/api/v1/browser-sessions/public-demo/analyze",
        json={"token": start["token"], "frames": [frame()], "refinement": True},
    )
    assert result.status_code == 200, result.text
    assert calls[0][-1] is True
    assert result.json()["event"] is None
    assert result.json()["checks_remaining"] == 27
    browser_sessions._public_demo_checks[start["id"]] = 32
    assert (
        api_client.post(
            "/api/v1/browser-sessions/public-demo/analyze",
            json={"token": start["token"], "frames": [frame()]},
        ).status_code
        == 429
    )
    quick = api_client.post(
        "/api/v1/browser-sessions/public-demo", json={"prompt": "Car parked"}
    ).json()
    browser_sessions._public_demo_checks[quick["id"]] = 4
    assert (
        api_client.post(
            "/api/v1/browser-sessions/public-demo/analyze",
            json={"token": quick["token"], "frames": [frame()], "detailed": True},
        ).status_code
        == 429
    )


def test_per_condition_answers_do_not_require_an_aggregate_status():
    decision = normalize_conditions(
        {
            "conditions": [
                {
                    "condition_index": 0,
                    "status": "match",
                    "summary": "Printer visible.",
                    "matched_frame_index": 0,
                },
                {
                    "condition_index": 1,
                    "status": "no_match",
                    "summary": "No dog visible.",
                },
            ]
        },
        8,
        ["A printer is visible", "A dog is visible"],
    )
    assert decision.status == "match"
    assert [item.status for item in decision.conditions] == ["match", "no_match"]
    assert decision.matched_frame_index == 0


def test_conditions_have_separate_answers_and_missing_answers_are_uncertain():
    decision = normalize_conditions(
        {
            "status": "match",
            "summary": "Person visible.",
            "conditions": [
                {
                    "condition_index": 0,
                    "condition": "hallucinated label",
                    "status": "match",
                    "summary": "Person visible.",
                    "matched_frame_index": 3,
                },
                {
                    "condition_index": 1,
                    "status": "no_match",
                    "summary": "No dog visible.",
                },
            ],
        },
        8,
        ["A person is visible", "A dog is visible", "A truck is visible"],
    )
    assert [item.status for item in decision.conditions] == [
        "match",
        "no_match",
        "uncertain",
    ]
    assert decision.conditions[0].condition == "A person is visible"
    assert decision.conditions[0].matched_frame_index == 3
    assert decision.status == "match"


def test_all_negative_conditions_override_inconsistent_top_level_match():
    decision = normalize_conditions(
        {
            "status": "match",
            "summary": "Incorrect aggregate",
            "conditions": [
                {"condition_index": 0, "status": "no_match", "summary": "No person."},
                {"condition_index": 1, "status": "no_match", "summary": "No dog."},
            ],
        },
        8,
        ["A person", "A dog"],
    )
    assert decision.status == "no_match"
    assert decision.matched_frame_index is None


def test_public_run_keeps_checking_after_first_condition_matches(
    api_client, monkeypatch
):
    api_client.app.state.settings.strands_enabled = True
    browser_sessions._public_demo_starts.clear()
    browser_sessions._public_demo_checks.clear()
    prompts = ["A person is visible", "A truck is visible"]
    calls = []

    def inspect(prompt, frames, *_):
        calls.append(prompt)
        active = 0 if len(calls) == 1 else 1
        return normalize_conditions(
            {
                "status": "match",
                "summary": "A condition matched",
                "conditions": [
                    {
                        "condition_index": i,
                        "status": "match" if i == active else "no_match",
                        "summary": "Visible" if i == active else "Not visible",
                        "matched_frame_index": 0,
                    }
                    for i in range(2)
                ],
            },
            len(frames),
            prompts,
        ), {}

    async def coordinator(*_, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "inspect_frames", inspect)
    monkeypatch.setattr(browser_sessions, "coordinate_incident", coordinator)
    token = api_client.post(
        "/api/v1/browser-sessions/public-demo", json={"prompt": "\n".join(prompts)}
    ).json()["token"]
    for batch in range(2):
        response = api_client.post(
            "/api/v1/browser-sessions/public-demo/analyze",
            json={
                "token": token,
                "frames": [{**frame(), "at_seconds": batch * 40 + 1}],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["conditions"][batch]["status"] == "match"
        assert body["event"]["details"]["conditions"][batch]["status"] == "match"
        assert body["checks_remaining"] == 3 - batch
    assert len(calls) == 2


def test_public_demo_rejects_too_many_conditions_before_inference(api_client):
    result = api_client.post(
        "/api/v1/browser-sessions/public-demo",
        json={
            "prompt": "\n".join(["A person is visible"] * 6),
        },
    )
    assert result.status_code == 422


def test_invalid_model_frame_pointer_does_not_crash_a_valid_decision():
    decision = normalize_decision(
        {
            "status": "match",
            "summary": "The condition is visible.",
            "matched_frame_index": 15,
        },
        frame_count=8,
    )
    assert decision.status == "match"
    assert decision.matched_frame_index is None

    valid = normalize_decision(
        {
            "status": "match",
            "summary": "The condition is visible.",
            "matched_frame_index": 3,
        },
        frame_count=8,
    )
    assert valid.matched_frame_index == 3


def custom_session(client):
    response = client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Visual test",
            "job": "custom",
            "prompt": "A red box is visible",
        },
    )
    assert response.status_code == 200, response.text
    client.app.state.settings.strands_enabled = True
    return response.json()["id"]


def test_real_model_result_creates_account_alert_with_durable_evidence_request(
    api_client, monkeypatch
):
    camera = custom_session(api_client)
    calls = []

    def inspect(*args):
        calls.append(args)
        return VisualDecision(status="match", summary="A red box is visible."), {
            "inputTokens": 230
        }

    async def no_coordinator(*args, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "inspect_frames", inspect)
    monkeypatch.setattr(browser_sessions, "coordinate_incident", no_coordinator)
    payload = {"id": str(uuid.uuid4()), "frames": [frame()]}
    path = f"/api/v1/browser-sessions/{camera}/analyze"
    response = api_client.post(path, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event"]["details"]["source"] == "bedrock_vision"
    assert body["event"]["details"]["evidence"]["status"] == "awaiting_recording"
    assert body["event"]["details"]["requires_human"] is True
    assert "jpeg" not in str(body)
    assert api_client.post(path, json=payload).json() == body
    assert len(calls) == 1
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    history = api_client.get(f"/api/v1/browser-sessions/{camera}/events")
    assert history.status_code == 200
    assert history.json()[0]["source_event_id"] == body["event"]["source_event_id"]
    assert history.json()[0]["verification_status"] == "uncertain"
    # Keep the general confirmed feed's safety boundary unchanged.
    assert api_client.get(f"/api/v1/events?camera_id={camera}").json() == []
    from video_intelligence_api.auth import Actor, get_current_actor
    from video_intelligence_api.models import OrganizationRole

    async def other_actor():
        return Actor(
            subject="other",
            organization_id=str(uuid.uuid4()),
            role=OrganizationRole.OWNER,
            issuer="test",
        )

    api_client.app.dependency_overrides[get_current_actor] = other_actor
    try:
        assert (
            api_client.get(f"/api/v1/browser-sessions/{camera}/events").status_code
            == 404
        )
    finally:
        api_client.app.dependency_overrides.clear()
    assert (
        api_client.post(path, json={**payload, "id": str(uuid.uuid4())}).status_code
        == 429
    )
    # A browser cannot bypass the visual model and invent a custom detection.
    assert (
        api_client.post(
            f"/api/v1/browser-sessions/{camera}/events",
            json={
                "id": str(uuid.uuid4()),
                "at_seconds": 4,
                "landmark_visibility": 0.99,
            },
        ).status_code
        == 422
    )


def test_negative_and_unavailable_models_never_fabricate_alerts(
    api_client, monkeypatch
):
    camera = custom_session(api_client)
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(status="no_match", summary="No red box visible."),
            {},
        ),
    )
    response = api_client.post(
        f"/api/v1/browser-sessions/{camera}/analyze",
        json={"id": str(uuid.uuid4()), "frames": [frame()]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["event"] is None
    assert api_client.get("/api/v1/alerts").json() == []
    second = custom_session(api_client)

    def unavailable(*_):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(browser_sessions, "inspect_frames", unavailable)
    response = api_client.post(
        f"/api/v1/browser-sessions/{second}/analyze",
        json={"id": str(uuid.uuid4()), "frames": [frame()]},
    )
    assert response.status_code == 503
    assert api_client.get("/api/v1/alerts").json() == []


def test_invalid_frames_and_empty_jobs_rejected_before_paid_inference(api_client):
    assert (
        api_client.post(
            "/api/v1/browser-sessions",
            json={"id": str(uuid.uuid4()), "name": "Bad", "job": "custom"},
        ).status_code
        == 422
    )
    camera = custom_session(api_client)
    assert (
        api_client.post(
            f"/api/v1/browser-sessions/{camera}/analyze",
            json={
                "id": str(uuid.uuid4()),
                "frames": [{"at_seconds": 0, "jpeg": "x" * 100}],
            },
        ).status_code
        == 422
    )
    assert decode_frame(frame()["jpeg"]).startswith(b"\xff\xd8")


def test_custom_job_waits_for_configured_matching_checks(api_client, monkeypatch):
    response = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Printer watch",
            "job": "custom",
            "prompt": "Visible stringing around the print",
            "check_interval_seconds": 5,
            "confirmation_count": 2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["confirmation_count"] == 2
    camera = response.json()["id"]
    api_client.app.state.settings.strands_enabled = True
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(status="match", summary="Stringing is visible."),
            {},
        ),
    )

    async def no_coordinator(*args, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "coordinate_incident", no_coordinator)
    moment = datetime(2026, 9, 12, tzinfo=timezone.utc)

    def advancing_now():
        nonlocal moment
        moment += timedelta(seconds=4)
        return moment

    monkeypatch.setattr(browser_sessions, "utc_now", advancing_now)
    path = f"/api/v1/browser-sessions/{camera}/analyze"
    first = api_client.post(path, json={"id": str(uuid.uuid4()), "frames": [frame()]})
    assert first.status_code == 200, first.text
    assert first.json()["match_streak"] == 1
    assert first.json()["confirmed"] is False
    assert first.json()["event"] is None
    second_frame = {**frame(), "at_seconds": 9}
    second = api_client.post(
        path, json={"id": str(uuid.uuid4()), "frames": [second_frame]}
    )
    assert second.status_code == 200, second.text
    assert second.json()["confirmed"] is True
    assert second.json()["event"] is not None
    assert len(api_client.get("/api/v1/alerts").json()) == 1


def test_public_demo_analyzes_storyboard_without_account_storage(
    api_client, monkeypatch
):
    api_client.app.state.settings.strands_enabled = True
    browser_sessions._public_demo_starts.clear()
    browser_sessions._public_demo_checks.clear()
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(
                status="match",
                summary="Loose filament is visible around the print.",
                matched_frame_index=1,
            ),
            {"inputTokens": 300},
        ),
    )

    class DemoRun:
        def model_dump(self, **_kwargs):
            return {
                "status": "completed",
                "summary": "Evidence and notification prepared.",
                "tools_invoked": ["preserve_evidence", "notify_responder"],
            }

    async def coordinator(*_args, **_kwargs):
        return DemoRun()

    monkeypatch.setattr(browser_sessions, "coordinate_incident", coordinator)
    started = api_client.post(
        "/api/v1/browser-sessions/public-demo",
        json={
            "prompt": "Alert me when the 3D print has loose filament",
        },
    )
    assert started.status_code == 200, started.text
    token = started.json()["token"]
    early = {**frame(), "at_seconds": 2}
    late = {**frame(), "at_seconds": 42}
    result = api_client.post(
        "/api/v1/browser-sessions/public-demo/analyze",
        json={
            "token": token,
            "frames": [early, late],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "match"
    assert result.json()["matched_frame_index"] == 1
    assert result.json()["event"]["details"]["strands_agent"]["status"] == "completed"
    assert result.json()["checks_remaining"] == 3
    assert api_client.get("/api/v1/alerts").json() == []
    rejected = api_client.post(
        "/api/v1/browser-sessions/public-demo/analyze",
        json={
            "token": token + "tampered",
            "frames": [early],
        },
    )
    assert rejected.status_code == 401

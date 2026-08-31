from video_intelligence_api.evaluation_scoring import TemporalInterval, score_intervals

AGENT_KEY = "test-agent-key-123456789"


def test_replay_video_upload_is_bounded_and_safely_named(api_client) -> None:
    uploaded_response = api_client.post(
        "/api/v1/evaluations/uploads",
        content=b"small-video-fixture",
        headers={
            "Content-Type": "video/mp4",
            "X-Replay-Filename": "..%2Fmasked-entry.mp4",
        },
    )

    assert uploaded_response.status_code == 201, uploaded_response.text
    uploaded = uploaded_response.json()
    assert uploaded["filename"] == "masked-entry.mp4"
    assert uploaded["source_uri"].endswith(".mp4")
    assert uploaded["size_bytes"] == len(b"small-video-fixture")

    invalid = api_client.post(
        "/api/v1/evaluations/uploads",
        content=b"not-a-video",
        headers={"Content-Type": "text/plain", "X-Replay-Filename": "notes.txt"},
    )
    assert invalid.status_code == 415

    oversized = api_client.post(
        "/api/v1/evaluations/uploads",
        content=b"x" * 1025,
        headers={"Content-Type": "video/mp4", "X-Replay-Filename": "large.mp4"},
    )
    assert oversized.status_code == 413


def test_interval_scoring_matches_once_and_reports_misses() -> None:
    metrics = score_intervals(
        [
            TemporalInterval(5, 10, "event"),
            TemporalInterval(20, 24, "event"),
        ],
        [
            TemporalInterval(6, 9, "event", detected_at_seconds=7),
            TemporalInterval(6.5, 8, "event", detected_at_seconds=8),
            TemporalInterval(30, 32, "event", detected_at_seconds=31),
        ],
    )

    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 2
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] == 0.333333
    assert metrics["recall"] == 0.5
    assert metrics["mean_latency_seconds"] == 2
    assert metrics["unmatched_expected_indices"] == [1]


def test_empty_interval_sets_are_a_perfect_no_event_result() -> None:
    metrics = score_intervals([], [])

    assert metrics["precision"] == 1
    assert metrics["recall"] == 1
    assert metrics["f1"] == 1


def test_replay_evaluation_compiles_routes_and_scores(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Replay Camera", "source_uri": "0"},
    ).json()
    created_response = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Masked entry baseline",
            "camera_id": camera["id"],
            "source_uri": "fixtures/masked-entry.mp4",
            "prompt": "Alert me when a masked person enters the store.",
            "duration_seconds": 40,
            "expected_intervals": [
                {"start_seconds": 5, "end_seconds": 10, "label": "event"}
            ],
        },
    )

    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert created["status"] == "draft"
    assert created["execution_strategy"] == "semantic_window"
    assert created["execution_plan"]["provider_requests"] is True
    assert created["compiled_rule"]["instruction"].startswith("Alert me")

    scored_response = api_client.post(
        f"/api/v1/evaluations/{created['id']}/score",
        json={
            "predicted_intervals": [
                {
                    "start_seconds": 6,
                    "end_seconds": 9,
                    "label": "event",
                    "detected_at_seconds": 7,
                    "confidence": 0.92,
                },
                {
                    "start_seconds": 20,
                    "end_seconds": 22,
                    "label": "event",
                    "detected_at_seconds": 21,
                    "confidence": 0.7,
                },
            ],
            "provider_requests": 2,
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_price_per_million_usd": 0.1,
            "output_price_per_million_usd": 0.5,
        },
    )

    assert scored_response.status_code == 200, scored_response.text
    scored = scored_response.json()
    assert scored["status"] == "scored"
    assert scored["metrics"]["true_positives"] == 1
    assert scored["metrics"]["false_positives"] == 1
    assert scored["metrics"]["false_negatives"] == 0
    assert scored["metrics"]["precision"] == 0.5
    assert scored["metrics"]["recall"] == 1
    assert scored["metrics"]["mean_latency_seconds"] == 2
    assert scored["estimated_cost_usd"] == 0.0002

    listed = api_client.get("/api/v1/evaluations").json()
    assert [evaluation["id"] for evaluation in listed] == [created["id"]]


def test_completed_upload_dispatches_real_incident_and_evidence(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Upload Action Camera", "source_uri": "webcam:0"},
    ).json()
    api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "safety floor",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    )
    upload = api_client.post(
        "/api/v1/evaluations/uploads",
        content=b"uploaded-video-evidence",
        headers={"Content-Type": "video/mp4", "X-Replay-Filename": "shift.mp4"},
    ).json()
    evaluation = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "shift.mp4",
            "camera_id": camera["id"],
            "source_uri": upload["source_uri"],
            "prompt": "Alert me when a person stays in the safety floor for 2 seconds.",
            "duration_seconds": 12,
            "expected_intervals": [],
        },
    ).json()
    scored = api_client.post(
        f"/api/v1/evaluations/{evaluation['id']}/score",
        json={
            "predicted_intervals": [
                {
                    "start_seconds": 3,
                    "end_seconds": 7,
                    "detected_at_seconds": 5,
                    "confidence": 0.91,
                }
            ]
        },
    ).json()
    assert scored["status"] == "scored"

    rule = api_client.post(
        f"/api/v1/rule-compilations/{evaluation['compilation_id']}/accept",
        json={},
    ).json()
    api_client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})

    dispatched_response = api_client.post(
        f"/api/v1/evaluations/{evaluation['id']}/dispatch",
        json={"rule_id": rule["id"]},
    )
    assert dispatched_response.status_code == 201, dispatched_response.text
    dispatched = dispatched_response.json()
    assert dispatched["details"]["uploaded_video"] is True
    assert dispatched["details"]["match_count"] == 1
    assert dispatched["confidence"] == 0.91

    alerts = api_client.get("/api/v1/alerts").json()
    assert alerts[0]["event_id"] == dispatched["id"]
    evidence = api_client.get("/api/v1/evidence").json()
    assert evidence[0]["event_id"] == dispatched["id"]
    assert evidence[0]["size_bytes"] == len(b"uploaded-video-evidence")

    duplicate = api_client.post(
        f"/api/v1/evaluations/{evaluation['id']}/dispatch",
        json={"rule_id": rule["id"]},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == dispatched["id"]
    assert len(api_client.get("/api/v1/alerts").json()) == 1


def test_replay_evaluation_rejects_intervals_outside_duration(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Bounds Camera", "source_uri": "0"},
    ).json()

    response = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Invalid labels",
            "camera_id": camera["id"],
            "source_uri": "fixtures/short.mp4",
            "prompt": "Alert me when a person enters.",
            "duration_seconds": 10,
            "expected_intervals": [{"start_seconds": 8, "end_seconds": 12}],
        },
    )

    assert response.status_code == 422


def test_replay_evaluation_is_leased_and_scored_by_worker(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Runner Camera", "source_uri": "0"},
    ).json()
    api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entrance",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    )
    evaluation = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Automatic replay",
            "camera_id": camera["id"],
            "source_uri": "fixtures/entry.mp4",
            "prompt": "Alert me when a person enters the entrance.",
            "duration_seconds": 20,
            "expected_intervals": [{"start_seconds": 5, "end_seconds": 8}],
        },
    ).json()

    queued = api_client.post(f"/api/v1/evaluations/{evaluation['id']}/run").json()
    assert queued["status"] == "queued"

    agent_headers = {"X-Agent-Key": AGENT_KEY}
    assignment_response = api_client.post(
        "/api/v1/agent/evaluations/claim",
        json={"worker_id": "replay-worker-1"},
        headers=agent_headers,
    )
    assert assignment_response.status_code == 200, assignment_response.text
    assignment = assignment_response.json()
    assert assignment["evaluation_id"] == evaluation["id"]
    assert assignment["source_uri"] == "fixtures/entry.mp4"
    assert assignment["rule"]["spec"]["rule_type"] == "zone_entry"

    heartbeat_response = api_client.post(
        f"/api/v1/agent/evaluations/{evaluation['id']}/heartbeat",
        headers=agent_headers,
        json={"worker_id": "replay-worker-1", "processed_seconds": 10},
    )
    assert heartbeat_response.status_code == 200, heartbeat_response.text
    heartbeat = heartbeat_response.json()
    assert heartbeat["processed_seconds"] == 10
    assert heartbeat["progress_percent"] == 50
    assert heartbeat["last_progress_at"] is not None

    wrong_worker = api_client.post(
        f"/api/v1/agent/evaluations/{evaluation['id']}/heartbeat",
        headers=agent_headers,
        json={"worker_id": "replay-worker-2", "processed_seconds": 15},
    )
    assert wrong_worker.status_code == 409

    duplicate_claim = api_client.post(
        "/api/v1/agent/evaluations/claim",
        json={"worker_id": "replay-worker-2"},
        headers=agent_headers,
    )
    assert duplicate_claim.status_code == 204

    result_response = api_client.post(
        f"/api/v1/agent/evaluations/{evaluation['id']}/result",
        headers=agent_headers,
        json={
            "worker_id": "replay-worker-1",
            "predicted_intervals": [
                {
                    "start_seconds": 5.5,
                    "end_seconds": 8,
                    "detected_at_seconds": 6,
                }
            ],
            "provider_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
    )
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    assert result["status"] == "scored"
    assert result["worker_id"] is None
    assert result["metrics"]["f1"] == 1
    assert result["progress_percent"] == 100


def test_replay_worker_failure_is_visible_and_can_be_requeued(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Failure Camera", "source_uri": "0"},
    ).json()
    api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entrance",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    )
    evaluation = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Missing replay",
            "camera_id": camera["id"],
            "source_uri": "fixtures/missing.mp4",
            "prompt": "Alert me when a person enters the entrance.",
            "duration_seconds": 20,
            "expected_intervals": [],
        },
    ).json()
    api_client.post(f"/api/v1/evaluations/{evaluation['id']}/run")
    headers = {"X-Agent-Key": AGENT_KEY}
    api_client.post(
        "/api/v1/agent/evaluations/claim",
        json={"worker_id": "replay-worker-1"},
        headers=headers,
    )

    failed = api_client.post(
        f"/api/v1/agent/evaluations/{evaluation['id']}/result",
        headers=headers,
        json={"worker_id": "replay-worker-1", "error": "Video file does not exist"},
    ).json()
    assert failed["status"] == "failed"
    assert failed["last_error"] == "Video file does not exist"

    requeued = api_client.post(f"/api/v1/evaluations/{evaluation['id']}/run").json()
    assert requeued["status"] == "queued"
    assert requeued["last_error"] is None


def test_regression_suite_preserves_failed_and_passed_gate_history(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Regression Camera", "source_uri": "0"},
    ).json()
    api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entrance",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    )

    def create_baseline(name: str, expected_intervals: list[dict]) -> dict:
        return api_client.post(
            "/api/v1/evaluations",
            json={
                "name": name,
                "camera_id": camera["id"],
                "source_uri": f"fixtures/{name.casefold().replace(' ', '-')}.mp4",
                "prompt": "Alert me when a person enters the entrance.",
                "duration_seconds": 20,
                "expected_intervals": expected_intervals,
            },
        ).json()

    positive = create_baseline(
        "Positive entry",
        [{"start_seconds": 5, "end_seconds": 8}],
    )
    negative = create_baseline("Negative entry", [])
    suite_response = api_client.post(
        "/api/v1/evaluation-suites",
        json={
            "name": "Entrance release gate",
            "evaluation_ids": [positive["id"], negative["id"]],
            "minimum_macro_f1": 0.8,
            "minimum_macro_recall": 0.8,
            "maximum_false_positives": 0,
            "maximum_estimated_cost_usd": 0.01,
            "require_pricing": True,
        },
    )
    assert suite_response.status_code == 201, suite_response.text
    suite = suite_response.json()
    assert suite["latest_run"] is None

    headers = {"X-Agent-Key": AGENT_KEY}

    def complete_next(predicted_intervals: list[dict]) -> None:
        assignment = api_client.post(
            "/api/v1/agent/evaluations/claim",
            headers=headers,
            json={"worker_id": "suite-worker"},
        ).json()
        response = api_client.post(
            f"/api/v1/agent/evaluations/{assignment['evaluation_id']}/result",
            headers=headers,
            json={
                "worker_id": "suite-worker",
                "predicted_intervals": predicted_intervals,
            },
        )
        assert response.status_code == 200, response.text

    failed_run = api_client.post(f"/api/v1/evaluation-suites/{suite['id']}/runs").json()
    assert failed_run["status"] == "queued"
    complete_next([{"start_seconds": 5, "end_seconds": 8}])
    complete_next([{"start_seconds": 1, "end_seconds": 2}])

    failed_result = api_client.get(
        f"/api/v1/evaluation-suites/runs/{failed_run['id']}"
    ).json()
    assert failed_result["status"] == "failed"
    assert failed_result["metrics"]["macro_f1"] == 0.5
    assert failed_result["metrics"]["false_positives"] == 1
    failed_gates = {gate["key"]: gate for gate in failed_result["gate_results"]}
    assert failed_gates["macro_f1"]["passed"] is False
    assert failed_gates["false_positives"]["passed"] is False

    passed_run = api_client.post(f"/api/v1/evaluation-suites/{suite['id']}/runs").json()
    complete_next([{"start_seconds": 5, "end_seconds": 8}])
    complete_next([])
    passed_result = api_client.get(
        f"/api/v1/evaluation-suites/runs/{passed_run['id']}"
    ).json()
    assert passed_result["status"] == "passed"
    assert passed_result["metrics"]["macro_f1"] == 1
    assert passed_result["metrics"]["scenario_metrics"]["unclassified"] == {
        "evaluation_count": 2,
        "macro_precision": 1.0,
        "macro_recall": 1.0,
        "macro_f1": 1.0,
        "false_positives": 0,
        "source_kinds": ["unclassified"],
        "variants": ["unclassified"],
    }
    assert passed_result["results"][0]["scenario_key"] is None
    assert all(gate["passed"] for gate in passed_result["gate_results"])

    history = api_client.get(f"/api/v1/evaluation-suites/{suite['id']}/runs").json()
    assert [run["status"] for run in history] == ["passed", "failed"]
    refreshed_suite = api_client.get(f"/api/v1/evaluation-suites/{suite['id']}").json()
    assert refreshed_suite["latest_run"]["id"] == passed_run["id"]

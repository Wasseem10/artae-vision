"""Focused checks for the native fall candidate baseline CLI."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from video_intelligence_inference.config import Settings
from video_intelligence_inference.control_plane import resolve_rule_config
from video_intelligence_inference.replay import ReplayInterval, ReplayOutput

from scripts import evaluate_native_fall as baseline


def test_missing_model_and_clip_fail_before_runtime_import(tmp_path: Path) -> None:
    model = tmp_path / "pose.pt"
    clip = tmp_path / "fall.mp4"
    args = baseline.parse_args(["--model", str(model), "--clip", str(clip)])

    def unexpected_runtime():
        raise AssertionError("Runtime should not load before file validation")

    with pytest.raises(ValueError, match="Pose model file is missing"):
        baseline.build_report(args, runtime_loader=unexpected_runtime)

    model.write_bytes(b"model")
    with pytest.raises(ValueError, match="Video clip is missing"):
        baseline.build_report(args, runtime_loader=unexpected_runtime)


def test_native_baseline_calls_specialized_pose_replay_and_exports_candidates(
    tmp_path: Path,
) -> None:
    model = tmp_path / "pose.pt"
    clip = tmp_path / "lateral.mp4"
    model.write_bytes(b"model-weights")
    clip.write_bytes(b"licensed-video-fixture")
    args = baseline.parse_args(
        [
            "--model",
            str(model),
            "--clip",
            str(clip),
            "--dataset-name",
            "fixture",
            "--confidence",
            "0.42",
            "--cooldown-seconds",
            "11",
            "--device",
            "cpu",
        ]
    )
    calls = []

    def fake_replay(settings, **kwargs):
        calls.append((settings, kwargs))
        for frame in range(120):
            kwargs["on_progress"](frame / 10)
        return ReplayOutput((ReplayInterval(1.0, 3.0, detected_at_seconds=3.0),))

    report = baseline.build_report(
        args,
        runtime_loader=lambda: (Settings, resolve_rule_config, fake_replay),
        video_probe=lambda _path: baseline.VideoMetadata(12.0, 120, 10.0),
        generated_at="2026-09-26T00:00:00+00:00",
    )

    assert len(calls) == 1
    settings, replay_kwargs = calls[0]
    assert settings.pose_model_name == str(model.resolve())
    assert replay_kwargs["source_uri"] == str(clip.resolve())
    assert replay_kwargs["rule"].execution_strategy == "specialized_pose"
    assert replay_kwargs["rule"].minimum_confidence == 0.42
    assert replay_kwargs["rule"].cooldown_seconds == 11
    assert report["kind"] == "native_fall_candidate_baseline"
    assert report["total_candidates"] == 1
    assert report["results"][0]["candidate_times_seconds"] == [3.0]
    assert report["results"][0]["frames_processed"] == 120
    assert report["results"][0]["duration_seconds"] == 12.0
    assert (
        report["provenance"]["model_sha256"]
        == hashlib.sha256(b"model-weights").hexdigest()
    )
    assert (
        report["results"][0]["clip_sha256"]
        == hashlib.sha256(b"licensed-video-fixture").hexdigest()
    )
    assert report["provenance"]["configuration"]["device"] == "cpu"
    assert "recall" in report["limitation"]


def test_bad_clip_is_rejected_by_video_probe(tmp_path: Path) -> None:
    clip = tmp_path / "broken.mp4"
    clip.write_bytes(b"not video")
    with pytest.raises(ValueError, match="Could not open video clip"):
        baseline.probe_video(clip)


def test_runtime_rejects_code_imported_from_another_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(baseline, "INFERENCE_SOURCE", tmp_path)
    with pytest.raises(RuntimeError, match="not this checkout"):
        baseline._load_runtime()


def test_incomplete_replay_cannot_be_exported(tmp_path: Path) -> None:
    model = tmp_path / "pose.pt"
    clip = tmp_path / "fall.mp4"
    model.write_bytes(b"model")
    clip.write_bytes(b"video")
    args = baseline.parse_args(["--model", str(model), "--clip", str(clip)])

    def short_replay(_settings, **kwargs):
        kwargs["on_progress"](0.0)
        return ReplayOutput(())

    with pytest.raises(RuntimeError, match="Incomplete replay"):
        baseline.build_report(
            args,
            runtime_loader=lambda: (Settings, resolve_rule_config, short_replay),
            video_probe=lambda _path: baseline.VideoMetadata(3.0, 3, 1.0),
        )


def test_cli_reports_missing_model_without_traceback(tmp_path: Path, capsys) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"anything")
    code = baseline.main(
        [
            "--model",
            str(tmp_path / "missing.pt"),
            "--clip",
            str(clip),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "Pose model file is missing" in captured.err
    assert "Traceback" not in captured.err


def test_cli_explains_windows_application_control_block(monkeypatch, capsys) -> None:
    def blocked(_args):
        raise OSError(
            "[WinError 4551] An Application Control policy has blocked this file"
        )

    monkeypatch.setattr(baseline, "build_report", blocked)
    code = baseline.main(["--model", "pose.pt", "--clip", "clip.mp4"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Windows Application Control blocked" in captured.err
    assert "approved host" in captured.err

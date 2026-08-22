import pytest
from video_intelligence_inference.stream_publisher import build_raw_publish_command


def test_raw_publish_command_uses_bounded_shell_free_video_settings() -> None:
    command = build_raw_publish_command(
        "ffmpeg.exe",
        "rtsp://127.0.0.1:8554/camera-1",
        width=1280,
        height=720,
        fps=30,
    )

    assert command[0] == "ffmpeg.exe"
    assert "1280x720" in command
    assert "bgr24" in command
    assert "libx264" in command
    assert command[-1] == "rtsp://127.0.0.1:8554/camera-1"


def test_raw_publish_command_rejects_non_rtsp_destination() -> None:
    with pytest.raises(ValueError, match="RTSP"):
        build_raw_publish_command(
            "ffmpeg.exe",
            "https://example.test/upload",
            width=640,
            height=480,
            fps=15,
        )

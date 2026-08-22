from pathlib import Path

from video_intelligence_inference.publisher import build_ffmpeg_command


def test_ffmpeg_publisher_command_loops_and_uses_safe_argument_list() -> None:
    command = build_ffmpeg_command(
        "C:/tools/ffmpeg.exe",
        Path("C:/video clips/demo.mp4"),
        "rtsp://127.0.0.1:8554/camera-123",
        loop=True,
    )

    assert command[0] == "C:/tools/ffmpeg.exe"
    assert command[command.index("-i") + 1] == str(Path("C:/video clips/demo.mp4"))
    assert command[-1] == "rtsp://127.0.0.1:8554/camera-123"
    assert "-stream_loop" in command
    assert "-rtsp_transport" in command
    assert isinstance(command, list)

from video_intelligence_api.models import SourceType


def infer_source_type(source_uri: str) -> SourceType:
    normalized = source_uri.strip().lower()
    if normalized.startswith("webcam:"):
        return SourceType.WEBCAM
    if normalized.startswith(("rtsp://", "rtsps://")):
        return SourceType.RTSP
    return SourceType.FILE


def redact_source_uri(source_uri: str) -> str:
    normalized = source_uri.strip()
    if normalized.lower().startswith(("rtsp://", "rtsps://")) and "@" in normalized:
        scheme, remainder = normalized.split("://", maxsplit=1)
        host_and_path = remainder.rsplit("@", maxsplit=1)[1]
        return f"{scheme}://***:***@{host_and_path}"
    return normalized

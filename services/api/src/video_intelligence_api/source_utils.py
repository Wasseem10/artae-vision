from urllib.parse import quote, urlsplit, urlunsplit

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


def split_source_credentials(source_uri: str) -> tuple[str, str | None, str | None]:
    """Return a credential-free URI and any decoded user information."""
    parsed = urlsplit(source_uri.strip())
    if parsed.scheme.lower() not in {"rtsp", "rtsps"} or parsed.hostname is None:
        return source_uri.strip(), None, None
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    clean = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return clean, parsed.username, parsed.password


def inject_source_credentials(source_uri: str, username: str, password: str) -> str:
    """Add percent-encoded credentials to an RTSP URI for a trusted edge assignment."""
    parsed = urlsplit(source_uri.strip())
    if parsed.scheme.lower() not in {"rtsp", "rtsps"} or parsed.hostname is None:
        return source_uri.strip()
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    host = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}"
    return urlunsplit(
        (parsed.scheme, f"{userinfo}@{host}", parsed.path, parsed.query, parsed.fragment)
    )

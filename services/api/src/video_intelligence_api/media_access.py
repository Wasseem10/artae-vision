import hashlib
import hmac
import time
from urllib.parse import urlencode

from video_intelligence_api.config import ApiSettings


def signed_evidence_url(
    evidence_id: str, organization_id: str, settings: ApiSettings
) -> str | None:
    if settings.media_signing_key is None:
        return None
    expires = int(time.time()) + settings.media_url_ttl_seconds
    message = f"{evidence_id}.{organization_id}.{expires}".encode()
    signature = hmac.new(
        settings.media_signing_key.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()
    query = urlencode(
        {"organization_id": organization_id, "expires": expires, "signature": signature}
    )
    return f"/api/v1/evidence/{evidence_id}/content?{query}"


def evidence_signature_is_valid(
    evidence_id: str,
    organization_id: str,
    expires: int,
    signature: str,
    settings: ApiSettings,
) -> bool:
    if settings.media_signing_key is None or expires < int(time.time()):
        return False
    message = f"{evidence_id}.{organization_id}.{expires}".encode()
    expected = hmac.new(
        settings.media_signing_key.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def signed_recording_url(
    recording_id: str, organization_id: str, settings: ApiSettings
) -> str | None:
    if settings.media_signing_key is None:
        return None
    expires = int(time.time()) + settings.media_url_ttl_seconds
    message = f"recording.{recording_id}.{organization_id}.{expires}".encode()
    signature = hmac.new(
        settings.media_signing_key.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()
    query = urlencode(
        {"organization_id": organization_id, "expires": expires, "signature": signature}
    )
    return f"/api/v1/recordings/{recording_id}/content?{query}"


def recording_signature_is_valid(
    recording_id: str,
    organization_id: str,
    expires: int,
    signature: str,
    settings: ApiSettings,
) -> bool:
    if settings.media_signing_key is None or expires < int(time.time()):
        return False
    message = f"recording.{recording_id}.{organization_id}.{expires}".encode()
    expected = hmac.new(
        settings.media_signing_key.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

"""Encryption helpers for camera credentials stored by the control plane."""

import json

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from video_intelligence_api.config import ApiSettings
from video_intelligence_api.database import Database
from video_intelligence_api.models import Camera
from video_intelligence_api.source_utils import (
    inject_source_credentials,
    split_source_credentials,
)


class CameraSecretError(RuntimeError):
    """Raised when camera credentials cannot be encrypted or decrypted."""


def _fernet(settings: ApiSettings) -> Fernet:
    key = settings.camera_encryption_key or settings.alert_encryption_key
    if key is None:
        raise CameraSecretError("VIDEO_INTEL_API_CAMERA_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.get_secret_value().encode())
    except (ValueError, TypeError) as exc:
        raise CameraSecretError("The camera encryption key is not a valid Fernet key") from exc


def encrypt_camera_secret(secret: str, settings: ApiSettings) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def decrypt_camera_secret(ciphertext: str, settings: ApiSettings) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CameraSecretError("The stored camera credentials cannot be decrypted") from exc


def encrypt_camera_credentials(username: str, password: str, settings: ApiSettings) -> str:
    payload = json.dumps({"username": username, "password": password}, separators=(",", ":"))
    return encrypt_camera_secret(payload, settings)


def decrypt_camera_credentials(ciphertext: str, settings: ApiSettings) -> tuple[str, str]:
    try:
        payload = json.loads(decrypt_camera_secret(ciphertext, settings))
        username = payload["username"]
        password = payload["password"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CameraSecretError("The stored camera credentials are invalid") from exc
    if not isinstance(username, str) or not isinstance(password, str):
        raise CameraSecretError("The stored camera credentials are invalid")
    return username, password


def resolved_camera_source(camera: Camera, settings: ApiSettings) -> str:
    """Return a source URI with credentials only for a trusted server/edge operation."""
    if camera.credential_encrypted is None:
        return camera.source_uri
    username, password = decrypt_camera_credentials(camera.credential_encrypted, settings)
    return inject_source_credentials(camera.source_uri, username, password)


async def migrate_legacy_camera_credentials(
    database: Database,
    settings: ApiSettings,
) -> int:
    """Move pre-0024 RTSP userinfo into encrypted columns during a safe startup."""
    if settings.camera_encryption_key is None and settings.alert_encryption_key is None:
        return 0
    migrated = 0
    async with database.session_factory() as session:
        cameras = (
            await session.scalars(
                select(Camera).where(
                    Camera.credential_encrypted.is_(None),
                    Camera.source_uri.contains("@"),
                )
            )
        ).all()
        for camera in cameras:
            clean_uri, username, password = split_source_credentials(camera.source_uri)
            if username is None:
                continue
            camera.source_uri = clean_uri
            camera.credential_encrypted = encrypt_camera_credentials(
                username,
                password or "",
                settings,
            )
            migrated += 1
        if migrated:
            await session.commit()
    return migrated

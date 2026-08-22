from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

TOKEN_VERSION = "vid1"


@dataclass(frozen=True, slots=True)
class GeneratedDeviceCredential:
    token: str
    token_hash: str
    fingerprint: str


def hash_device_token(token: str) -> str:
    """Hash a high-entropy device token so the original is never persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_device_credential(device_id: str) -> GeneratedDeviceCredential:
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_VERSION}.{device_id}.{secret}"
    token_hash = hash_device_token(token)
    return GeneratedDeviceCredential(
        token=token,
        token_hash=token_hash,
        fingerprint=token_hash[:16],
    )


def device_id_from_token(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION or len(parts[2]) < 32:
        return None
    try:
        return str(uuid.UUID(parts[1]))
    except ValueError:
        return None

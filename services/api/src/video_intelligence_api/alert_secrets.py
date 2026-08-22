from cryptography.fernet import Fernet, InvalidToken

from video_intelligence_api.config import ApiSettings


class AlertSecretError(RuntimeError):
    pass


def _fernet(settings: ApiSettings) -> Fernet:
    if settings.alert_encryption_key is None:
        raise AlertSecretError("VIDEO_INTEL_API_ALERT_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(settings.alert_encryption_key.get_secret_value().encode())
    except (ValueError, TypeError) as exc:
        raise AlertSecretError("The alert encryption key is not a valid Fernet key") from exc


def encrypt_alert_secret(secret: str, settings: ApiSettings) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def decrypt_alert_secret(ciphertext: str, settings: ApiSettings) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise AlertSecretError("The stored alert secret cannot be decrypted") from exc

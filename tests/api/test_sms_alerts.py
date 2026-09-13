from datetime import UTC, datetime
from types import SimpleNamespace

from cryptography.fernet import Fernet
from pydantic import SecretStr
from video_intelligence_api import sms_alerts
from video_intelligence_api.alert_secrets import encrypt_alert_secret
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.sms_alerts import send_caregiver_sms, valid_e164


def settings(**overrides) -> ApiSettings:
    return ApiSettings(
        environment="test",
        agent_key=SecretStr("test-agent-key-1234"),
        dashboard_key=SecretStr("test-dashboard-key"),
        **overrides,
    )


def test_valid_e164_rejects_ambiguous_or_local_numbers() -> None:
    assert valid_e164("+12065550142")
    assert not valid_e164("2065550142")
    assert not valid_e164("+1 (206) 555-0142")
    assert not valid_e164("+0123456789")


def test_sms_is_explicitly_not_configured_without_destination() -> None:
    config = settings(sms_enabled=True)
    result = send_caregiver_sms(
        encrypted_phone=None,
        event=SimpleNamespace(occurred_at=datetime.now(UTC)),
        camera=SimpleNamespace(name="Community room"),
        settings=config,
        oidc_token=None,
    )
    assert result == {"status": "not_configured", "provider": "aws_sns"}


def test_disabled_provider_never_attempts_delivery() -> None:
    config = settings(
        sms_enabled=False,
        alert_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    encrypted = encrypt_alert_secret("+12065550142", config)
    result = send_caregiver_sms(
        encrypted_phone=encrypted,
        event=SimpleNamespace(occurred_at=datetime.now(UTC)),
        camera=SimpleNamespace(name="Community room"),
        settings=config,
        oidc_token=None,
    )
    assert result == {"status": "provider_not_configured", "provider": "aws_sns"}


def test_sms_uses_transactional_aws_delivery_and_masks_destination(monkeypatch) -> None:
    class Client:
        def publish(self, **payload):
            assert payload["PhoneNumber"] == "+12065550142"
            assert payload["MessageAttributes"]["AWS.SNS.SMS.SMSType"]["StringValue"] == (
                "Transactional"
            )
            assert "A person fell beside the chair" in payload["Message"]
            assert "00:01:23" in payload["Message"]
            assert "watch for a fall" not in payload["Message"]
            return {"MessageId": "message-123"}

    class Session:
        def client(self, service, **_kwargs):
            assert service == "sns"
            return Client()

    config = settings(
        sms_enabled=True,
        alert_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    encrypted = encrypt_alert_secret("+12065550142", config)
    monkeypatch.setattr(sms_alerts, "bedrock_session", lambda *_args: Session())
    result = send_caregiver_sms(
        encrypted_phone=encrypted,
        event=SimpleNamespace(occurred_at=datetime.now(UTC), occurred_at_seconds=83,
                              details={"summary": "A person fell beside the chair",
                                       "conditions": [{"condition": "watch for a fall", "status": "match"}]}),
        camera=SimpleNamespace(name="Community room"),
        settings=config,
        oidc_token=None,
    )
    assert result == {
        "status": "accepted",
        "provider": "aws_sns",
        "destination": "••••0142",
        "provider_message_id": "message-123",
    }


def test_sms_error_reports_permission_failure_without_leaking_aws_details(monkeypatch):
    from botocore.exceptions import ClientError

    class Client:
        def publish(self, **_payload):
            raise ClientError({"Error": {"Code": "AuthorizationError", "Message": "private-account-secret"}}, "Publish")
    class Session:
        def client(self, *_args, **_kwargs):
            return Client()
    config = settings(sms_enabled=True, alert_encryption_key=SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(sms_alerts, "bedrock_session", lambda *_args: Session())
    receipt = send_caregiver_sms(encrypted_phone=encrypt_alert_secret("+12065550142", config),
                                event=None, camera=SimpleNamespace(name="Test"), settings=config,
                                oidc_token=None, test=True)
    assert receipt["status"] == "failed"
    assert "sns:Publish" in receipt["message"]
    assert "private-account-secret" not in str(receipt)


def test_connection_text_does_not_claim_an_incident(monkeypatch):
    class Client:
        def publish(self, **payload):
            assert payload["Message"].startswith("Artae test text:")
            assert "No fall was detected or reported by this test" in payload["Message"]
            return {"MessageId": "test-1"}
    class Session:
        def client(self, *_args, **_kwargs):
            return Client()
    config = settings(sms_enabled=True, alert_encryption_key=SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(sms_alerts, "bedrock_session", lambda *_args: Session())
    receipt = send_caregiver_sms(encrypted_phone=encrypt_alert_secret("+12065550142", config),
                                event=None, camera=SimpleNamespace(name="Test"), settings=config,
                                oidc_token=None, test=True)
    assert receipt["status"] == "accepted"

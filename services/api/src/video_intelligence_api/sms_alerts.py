"""Bounded AWS SMS delivery for account-owned caregiver alerts.

Phone numbers are encrypted in the browser-session rule and are never returned to
the browser or placed in event details. SMS is an additional notification path;
failure must never suppress the durable in-app incident.
"""

from __future__ import annotations

import re
from botocore.config import Config

from video_intelligence_api.alert_secrets import AlertSecretError, decrypt_alert_secret
from video_intelligence_api.bedrock_identity import bedrock_session
from video_intelligence_api.config import ApiSettings

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def valid_e164(value: str) -> bool:
    return bool(E164_PATTERN.fullmatch(value.strip()))


def _masked_destination(phone: str) -> str:
    return f"••••{phone[-4:]}"


def send_caregiver_sms(
    *,
    encrypted_phone: str | None,
    event,
    camera,
    settings: ApiSettings,
    oidc_token: str | None,
    test: bool = False,
) -> dict[str, object]:
    """Send one transactional alert and return an operator-safe receipt."""
    if not encrypted_phone:
        return {"status": "not_configured", "provider": "aws_sns"}
    if not settings.sms_enabled:
        return {"status": "provider_not_configured", "provider": "aws_sns"}
    try:
        phone = decrypt_alert_secret(encrypted_phone, settings).strip()
    except AlertSecretError:
        return {"status": "failed", "provider": "aws_sns", "error": "destination_unavailable"}
    if not valid_e164(phone):
        return {"status": "failed", "provider": "aws_sns", "error": "invalid_destination"}

    matched = next(
        (
            item.get("condition")
            for item in (getattr(event, "details", None) or {}).get("conditions", [])
            if item.get("status") == "match" and item.get("condition")
        ),
        "Possible fall detected",
    )
    details = getattr(event, "details", None) or {}
    summary = " ".join(str(details.get("summary") or matched).split())[:360]
    at = getattr(event, "occurred_at_seconds", None)
    timing = ""
    if isinstance(at, (float, int)) and at >= 0:
        seconds = int(at)
        timing = f" Around {seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d} in the video."
    message = (
        "Artae test text: Your alert connection works. No fall was detected or reported by this test."
        if test else
        f"Artae video alert: {summary}{timing} Review the footage and check whether help is needed."
    )
    try:
        boto_session = bedrock_session(settings.strands_role_arn, settings.sms_region, oidc_token)
        client = (
            boto_session.client("sns", region_name=settings.sms_region,
                                config=Config(connect_timeout=3, read_timeout=6, retries={"max_attempts": 0}))
            if boto_session is not None
            else __import__("boto3").client("sns", region_name=settings.sms_region,
                                           config=Config(connect_timeout=3, read_timeout=6, retries={"max_attempts": 0}))
        )
        attributes = {
            "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}
        }
        if settings.sms_sender_id:
            attributes["AWS.SNS.SMS.SenderID"] = {
                "DataType": "String",
                "StringValue": settings.sms_sender_id,
            }
        response = client.publish(
            PhoneNumber=phone,
            Message=message,
            MessageAttributes=attributes,
        )
        message_id = str(response.get("MessageId") or "")
        if not message_id:
            return {"status": "failed", "provider": "aws_sns", "error": "provider_no_receipt"}
        return {
            "status": "accepted",
            "provider": "aws_sns",
            "destination": _masked_destination(phone),
            "provider_message_id": message_id,
        }
    except Exception as exc:  # AWS errors are reflected in the incident, never promoted to success.
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        explanations = {
            "AuthorizationError": "AWS has not granted this app permission to send texts (sns:Publish).",
            "AccessDenied": "AWS has not granted this app permission to send texts (sns:Publish).",
            "AccessDeniedException": "AWS has not granted this app permission to send texts (sns:Publish).",
            "InvalidParameter": "AWS rejected this destination. Check the phone format and verify the number in the AWS SMS sandbox.",
            "OptedOut": "This phone has opted out of text messages.",
            "Throttled": "AWS is limiting text requests. Try again shortly.",
        }
        return {
            "status": "failed",
            "provider": "aws_sns",
            "destination": _masked_destination(phone),
            "error": code,
            "message": explanations.get(code, "AWS could not send this text. Check SMS permissions, the verified destination, and your sending limits."),
        }


__all__ = ["send_caregiver_sms", "valid_e164"]

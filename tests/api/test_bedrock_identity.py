from unittest.mock import Mock

import pytest
from video_intelligence_api import bedrock_identity


def test_no_role_keeps_native_credentials_and_missing_token_fails_closed(monkeypatch):
    client = Mock()
    monkeypatch.setattr(bedrock_identity.boto3, "client", client)
    assert bedrock_identity.bedrock_session(None, "us-east-1", None) is None
    with pytest.raises(RuntimeError, match="OIDC token"):
        bedrock_identity.bedrock_session("arn:aws:iam::123:role/demo", "us-east-1", None)
    client.assert_not_called()


def test_oidc_exchange_uses_short_lived_credentials_and_fixed_role(monkeypatch):
    sts, session_factory = Mock(), Mock()
    sts.assume_role_with_web_identity.return_value = {"Credentials": {
        "AccessKeyId": "test-id", "SecretAccessKey": "test-secret", "SessionToken": "test-session",
    }}
    monkeypatch.setattr(bedrock_identity.boto3, "client", Mock(return_value=sts))
    monkeypatch.setattr(bedrock_identity.boto3, "Session", session_factory)
    bedrock_identity.bedrock_session("arn:aws:iam::123:role/demo", "us-east-1", "synthetic-test-token")
    sts.assume_role_with_web_identity.assert_called_once_with(
        RoleArn="arn:aws:iam::123:role/demo", RoleSessionName="artae-incident",
        WebIdentityToken="synthetic-test-token", DurationSeconds=900,
    )
    session_factory.assert_called_once_with(
        aws_access_key_id="test-id", aws_secret_access_key="test-secret",
        aws_session_token="test-session", region_name="us-east-1",
    )

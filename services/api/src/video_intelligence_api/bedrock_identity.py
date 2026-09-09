"""Exchange the production platform's OIDC token for short-lived Bedrock credentials.

AWS verifies signature/issuer/audience/subject against the restricted IAM trust
policy. Never accept a role ARN from a client, log tokens, or persist credentials.
"""

import boto3
from botocore import UNSIGNED
from botocore.config import Config


def bedrock_session(role_arn: str | None, region: str, oidc_token: str | None):
    if not role_arn:
        return None  # Local/native deployments use boto3's standard credential chain.
    if not oidc_token:
        raise RuntimeError("The platform OIDC token is unavailable")
    sts = boto3.client(
        "sts", region_name=region,
        config=Config(signature_version=UNSIGNED, connect_timeout=5, read_timeout=10,
                      retries={"max_attempts": 1}),
    )
    credentials = sts.assume_role_with_web_identity(
        RoleArn=role_arn,
        RoleSessionName="artae-incident",
        WebIdentityToken=oidc_token,
        DurationSeconds=900,
    )["Credentials"]
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=region,
    )

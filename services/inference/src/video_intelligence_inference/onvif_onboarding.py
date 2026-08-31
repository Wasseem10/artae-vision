"""Authenticated ONVIF media-profile resolution and RTSP preview verification."""

from __future__ import annotations

import base64
import hashlib
import secrets
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit, urlunsplit
from xml.sax.saxutils import escape

import cv2
import httpx

_SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
_DEVICE_NS = "http://www.onvif.org/ver10/device/wsdl"
_MEDIA_NS = "http://www.onvif.org/ver10/media/wsdl"


class OnvifOnboardingError(RuntimeError):
    """Raised when a camera cannot be authenticated, resolved, or previewed."""


@dataclass(frozen=True, slots=True)
class OnvifMediaProfile:
    token: str
    name: str
    encoding: str | None
    width: int | None
    height: int | None
    frame_rate: float | None
    stream_uri: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OnvifOnboardingOutput:
    profiles: tuple[OnvifMediaProfile, ...]
    selected_profile_token: str
    stream_uri: str
    preview_jpeg: bytes


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element.iter() if _local_name(item.tag) == name), None)


def _text(element: ET.Element, name: str) -> str | None:
    child = _descendant(element, name)
    return child.text.strip() if child is not None and child.text else None


def _integer(element: ET.Element, name: str) -> int | None:
    value = _text(element, name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float(element: ET.Element, name: str) -> float | None:
    value = _text(element, name)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _ws_security(username: str, password: str) -> str:
    nonce = secrets.token_bytes(16)
    created = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + password.encode()).digest()
    ).decode()
    nonce_text = base64.b64encode(nonce).decode()
    return f"""
<wsse:Security s:mustUnderstand="1"
 xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
 xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
 <wsse:UsernameToken>
  <wsse:Username>{escape(username)}</wsse:Username>
  <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
  <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_text}</wsse:Nonce>
  <wsu:Created>{created}</wsu:Created>
 </wsse:UsernameToken>
</wsse:Security>"""


def _envelope(body: str, username: str, password: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{_SOAP_NS}">
 <s:Header>{_ws_security(username, password)}</s:Header>
 <s:Body>{body}</s:Body>
</s:Envelope>""".encode()


def _soap(
    client: httpx.Client,
    url: str,
    action: str,
    body: str,
    username: str,
    password: str,
) -> ET.Element:
    try:
        response = client.post(
            url,
            content=_envelope(body, username, password),
            headers={"Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"'},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise OnvifOnboardingError("Camera rejected the supplied credentials") from exc
        raise OnvifOnboardingError(
            f"Camera ONVIF service returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OnvifOnboardingError("Camera ONVIF service could not be reached") from exc
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise OnvifOnboardingError("Camera returned malformed ONVIF XML") from exc
    fault = _descendant(root, "Fault")
    if fault is not None:
        reason = _text(fault, "Text") or _text(fault, "Reason") or "Camera returned an ONVIF fault"
        raise OnvifOnboardingError(reason[:500])
    return root


def _media_service_url(
    client: httpx.Client,
    endpoint_url: str,
    username: str,
    password: str,
) -> str:
    root = _soap(
        client,
        endpoint_url,
        f"{_DEVICE_NS}/GetCapabilities",
        (
            f'<tds:GetCapabilities xmlns:tds="{_DEVICE_NS}">'
            "<tds:Category>Media</tds:Category></tds:GetCapabilities>"
        ),
        username,
        password,
    )
    capabilities = _descendant(root, "Capabilities")
    if capabilities is not None:
        for child in capabilities.iter():
            if _local_name(child.tag) == "Media":
                xaddr = _text(child, "XAddr")
                if xaddr:
                    parsed = urlsplit(xaddr)
                    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
                        return xaddr
    raise OnvifOnboardingError("Camera did not advertise an ONVIF Media service")


def _profile_rows(
    root: ET.Element,
) -> list[tuple[str, str, str | None, int | None, int | None, float | None]]:
    rows: list[tuple[str, str, str | None, int | None, int | None, float | None]] = []
    for profile in root.iter():
        if _local_name(profile.tag) != "Profiles":
            continue
        token = profile.attrib.get("token")
        if not token:
            continue
        encoder = _descendant(profile, "VideoEncoderConfiguration")
        if encoder is None:
            continue
        resolution = _descendant(encoder, "Resolution")
        rate_control = _descendant(encoder, "RateControl")
        rows.append(
            (
                token,
                _text(profile, "Name") or token,
                _text(encoder, "Encoding"),
                _integer(resolution, "Width") if resolution is not None else None,
                _integer(resolution, "Height") if resolution is not None else None,
                _float(rate_control, "FrameRateLimit") if rate_control is not None else None,
            )
        )
    return rows


def _clean_rtsp_uri(uri: str) -> str:
    parsed = urlsplit(uri.strip())
    if parsed.scheme.lower() not in {"rtsp", "rtsps"} or parsed.hostname is None:
        raise OnvifOnboardingError("Camera returned an invalid RTSP stream URI")
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    host = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _authenticated_rtsp_uri(uri: str, username: str, password: str) -> str:
    parsed = urlsplit(_clean_rtsp_uri(uri))
    credentials = f"{quote(username, safe='')}:{quote(password, safe='')}"
    return urlunsplit(
        (
            parsed.scheme,
            f"{credentials}@{parsed.netloc}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _read_preview(
    stream_uri: str,
    username: str,
    password: str,
    *,
    timeout_seconds: float,
    maximum_width: int = 960,
    jpeg_quality: int = 80,
) -> bytes:
    source = _authenticated_rtsp_uri(stream_uri, username, password)
    capture = cv2.VideoCapture()
    try:
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_seconds * 1000)
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_seconds * 1000)
        if not capture.open(source):
            raise OnvifOnboardingError(
                "RTSP stream could not be opened with the supplied credentials"
            )
        frame = None
        for _ in range(3):
            ok, candidate = capture.read()
            if ok and candidate is not None:
                frame = candidate
                break
        if frame is None:
            raise OnvifOnboardingError("RTSP stream opened but did not return a video frame")
        height, width = frame.shape[:2]
        if width > maximum_width:
            frame = cv2.resize(
                frame,
                (maximum_width, max(1, round(height * maximum_width / width))),
                interpolation=cv2.INTER_AREA,
            )
        encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        if not encoded:
            raise OnvifOnboardingError("Camera preview could not be encoded")
        return jpeg.tobytes()
    finally:
        capture.release()


def _profile_score(profile: OnvifMediaProfile) -> tuple[int, int, float]:
    encoding = (profile.encoding or "").upper()
    codec_score = {"H264": 3, "H265": 2, "MPEG4": 1}.get(encoding, 0)
    pixels = (profile.width or 0) * (profile.height or 0)
    return codec_score, pixels, profile.frame_rate or 0


def resolve_onvif_camera(
    *,
    endpoint_url: str,
    username: str,
    password: str,
    verify_tls: bool = True,
    timeout_seconds: float = 10,
    transport: httpx.BaseTransport | None = None,
    preview_reader: Callable[..., bytes] = _read_preview,
) -> OnvifOnboardingOutput:
    """Resolve media profiles, select a stream, and prove it by reading one frame."""
    auth = httpx.DigestAuth(username, password)
    with httpx.Client(
        timeout=timeout_seconds,
        verify=verify_tls,
        auth=auth,
        transport=transport,
    ) as client:
        media_url = _media_service_url(client, endpoint_url, username, password)
        profiles_root = _soap(
            client,
            media_url,
            f"{_MEDIA_NS}/GetProfiles",
            f'<trt:GetProfiles xmlns:trt="{_MEDIA_NS}"/>',
            username,
            password,
        )
        profile_rows = _profile_rows(profiles_root)
        if not profile_rows:
            raise OnvifOnboardingError("Camera did not return a usable video media profile")
        profiles: list[OnvifMediaProfile] = []
        for token, name, encoding, width, height, frame_rate in profile_rows[:50]:
            uri_root = _soap(
                client,
                media_url,
                f"{_MEDIA_NS}/GetStreamUri",
                (
                    f'<trt:GetStreamUri xmlns:trt="{_MEDIA_NS}" '
                    'xmlns:tt="http://www.onvif.org/ver10/schema">'
                    "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
                    "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
                    f"</trt:StreamSetup><trt:ProfileToken>{escape(token)}</trt:ProfileToken>"
                    "</trt:GetStreamUri>"
                ),
                username,
                password,
            )
            uri = _text(uri_root, "Uri")
            if uri is None:
                continue
            profiles.append(
                OnvifMediaProfile(
                    token=token,
                    name=name,
                    encoding=encoding,
                    width=width,
                    height=height,
                    frame_rate=frame_rate,
                    stream_uri=_clean_rtsp_uri(uri),
                )
            )
    if not profiles:
        raise OnvifOnboardingError("Camera did not return a usable RTSP stream URI")
    selected = max(profiles, key=_profile_score)
    preview = preview_reader(
        selected.stream_uri,
        username,
        password,
        timeout_seconds=timeout_seconds,
    )
    return OnvifOnboardingOutput(
        profiles=tuple(profiles),
        selected_profile_token=selected.token,
        stream_uri=selected.stream_uri,
        preview_jpeg=preview,
    )

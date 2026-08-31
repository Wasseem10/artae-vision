import httpx
from video_intelligence_inference.onvif_onboarding import resolve_onvif_camera

CAPABILITIES = b"""<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
 xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body><tds:GetCapabilitiesResponse>
 <tds:Capabilities><tt:Media><tt:XAddr>http://192.0.2.10/onvif/media_service</tt:XAddr>
 </tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse></s:Body></s:Envelope>"""

PROFILES = b"""<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
 xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body><trt:GetProfilesResponse>
 <trt:Profiles token="main"><tt:Name>Main stream</tt:Name><tt:VideoEncoderConfiguration>
 <tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height>
 </tt:Resolution><tt:RateControl><tt:FrameRateLimit>30</tt:FrameRateLimit></tt:RateControl>
 </tt:VideoEncoderConfiguration></trt:Profiles>
 <trt:Profiles token="sub"><tt:Name>Sub stream</tt:Name><tt:VideoEncoderConfiguration>
 <tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>640</tt:Width><tt:Height>360</tt:Height>
 </tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles>
 </trt:GetProfilesResponse></s:Body></s:Envelope>"""


def _stream_uri(token: str) -> bytes:
    return f"""<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:trt="http://www.onvif.org/ver10/media/wsdl"><s:Body><trt:GetStreamUriResponse>
 <trt:MediaUri><trt:Uri>rtsp://camera-user:camera-pass@192.0.2.10/{token}</trt:Uri>
 </trt:MediaUri></trt:GetStreamUriResponse></s:Body></s:Envelope>""".encode()


def test_resolves_profiles_selects_main_stream_and_verifies_preview() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.content
        if b"GetCapabilities" in body:
            return httpx.Response(200, content=CAPABILITIES)
        if b"GetProfiles" in body:
            return httpx.Response(200, content=PROFILES)
        if b"<trt:ProfileToken>main" in body:
            return httpx.Response(200, content=_stream_uri("main"))
        return httpx.Response(200, content=_stream_uri("sub"))

    def preview_reader(
        stream_uri: str,
        username: str,
        password: str,
        **kwargs: object,
    ) -> bytes:
        assert stream_uri == "rtsp://192.0.2.10/main"
        assert (username, password) == ("operator", "secret-password")
        assert kwargs["timeout_seconds"] == 5
        return b"\xff\xd8verified-preview\xff\xd9"

    output = resolve_onvif_camera(
        endpoint_url="http://192.0.2.10/onvif/device_service",
        username="operator",
        password="secret-password",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
        preview_reader=preview_reader,
    )

    assert output.selected_profile_token == "main"
    assert output.stream_uri == "rtsp://192.0.2.10/main"
    assert len(output.profiles) == 2
    assert output.profiles[0].width == 1920
    assert all(b"secret-password" not in request.content for request in requests)
    assert all(b"PasswordDigest" in request.content for request in requests)


def test_reports_authentication_failure_without_leaking_credentials() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    try:
        resolve_onvif_camera(
            endpoint_url="http://192.0.2.10/onvif/device_service",
            username="operator",
            password="do-not-leak",
            transport=httpx.MockTransport(handler),
        )
    except RuntimeError as exc:
        assert str(exc) == "Camera rejected the supplied credentials"
        assert "do-not-leak" not in str(exc)
    else:
        raise AssertionError("Expected authentication failure")

from video_intelligence_inference.onvif_discovery import (
    discover_onvif_devices,
    parse_probe_matches,
)

PROBE_MATCH = b"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
 <s:Body><d:ProbeMatches><d:ProbeMatch>
  <a:EndpointReference><a:Address>urn:uuid:camera-one</a:Address></a:EndpointReference>
  <d:Scopes>onvif://www.onvif.org/name/LoadingDock onvif://www.onvif.org/type/video_encoder</d:Scopes>
  <d:XAddrs>http://192.0.2.10/onvif/device_service ftp://ignored.test/file</d:XAddrs>
 </d:ProbeMatch></d:ProbeMatches></s:Body>
</s:Envelope>"""


class FakeSocket:
    def __init__(self, responses: list[tuple[bytes, tuple[str, int]]]) -> None:
        self.responses = responses
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.bound: tuple[str, int] | None = None
        self.closed = False

    def setsockopt(self, *_args: object) -> None:
        pass

    def bind(self, address: tuple[str, int]) -> None:
        self.bound = address

    def sendto(self, data: bytes, address: tuple[str, int]) -> None:
        self.sent.append((data, address))

    def settimeout(self, _timeout: float) -> None:
        pass

    def recvfrom(self, _maximum: int) -> tuple[bytes, tuple[str, int]]:
        if self.responses:
            return self.responses.pop(0)
        raise TimeoutError()

    def close(self) -> None:
        self.closed = True


def test_probe_parser_extracts_safe_onvif_service_addresses() -> None:
    devices = parse_probe_matches(PROBE_MATCH, "192.0.2.10")

    assert len(devices) == 1
    assert devices[0].endpoint_reference == "urn:uuid:camera-one"
    assert devices[0].xaddrs == ("http://192.0.2.10/onvif/device_service",)
    assert devices[0].remote_address == "192.0.2.10"
    assert len(devices[0].scopes) == 2


def test_discovery_is_bounded_and_deduplicates_responses() -> None:
    fake = FakeSocket(
        [
            (PROBE_MATCH, ("192.0.2.10", 3702)),
            (PROBE_MATCH, ("192.0.2.10", 3702)),
        ]
    )
    ticks = iter([0.0, 0.0, 0.1, 0.2, 2.0])

    devices = discover_onvif_devices(
        timeout_seconds=1,
        socket_factory=lambda *_args: fake,  # type: ignore[arg-type]
        monotonic=lambda: next(ticks),
    )

    assert len(devices) == 1
    assert fake.bound == ("0.0.0.0", 0)
    assert fake.sent[0][1] == ("239.255.255.250", 3702)
    assert b"NetworkVideoTransmitter" in fake.sent[0][0]
    assert fake.closed is True


def test_malformed_discovery_response_is_ignored() -> None:
    assert parse_probe_matches(b"not xml", "192.0.2.11") == []

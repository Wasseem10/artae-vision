"""Bounded ONVIF WS-Discovery probe for execution on an edge camera network."""

from __future__ import annotations

import logging
import socket
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_MULTICAST_ADDRESS = ("239.255.255.250", 3702)
_MAX_RESPONSE_BYTES = 65_535


@dataclass(frozen=True, slots=True)
class DiscoveredOnvifDevice:
    endpoint_reference: str
    xaddrs: tuple[str, ...]
    scopes: tuple[str, ...]
    remote_address: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _probe_message() -> bytes:
    message_id = f"uuid:{uuid.uuid4()}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
 <e:Header>
  <w:MessageID>{message_id}</w:MessageID>
  <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
  <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
 </e:Header>
 <e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>""".encode()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def parse_probe_matches(data: bytes, remote_address: str) -> list[DiscoveredOnvifDevice]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        logger.warning("Ignoring malformed WS-Discovery response from %s", remote_address)
        return []
    devices: list[DiscoveredOnvifDevice] = []
    for match in root.iter():
        if _local_name(match.tag) != "ProbeMatch":
            continue
        endpoint = ""
        for child in match.iter():
            if _local_name(child.tag) == "EndpointReference":
                endpoint = _child_text(child, "Address")
                break
        xaddrs = tuple(
            value
            for value in _child_text(match, "XAddrs").split()
            if urlsplit(value).scheme.lower() in {"http", "https"}
        )[:20]
        scopes = tuple(_child_text(match, "Scopes").split())[:200]
        if not endpoint and not xaddrs:
            continue
        devices.append(
            DiscoveredOnvifDevice(
                endpoint_reference=endpoint or xaddrs[0],
                xaddrs=xaddrs,
                scopes=scopes,
                remote_address=remote_address,
            )
        )
    return devices


def discover_onvif_devices(
    *,
    timeout_seconds: float = 3,
    maximum_devices: int = 100,
    interface_ip: str = "0.0.0.0",
    socket_factory: Callable[..., socket.socket] = socket.socket,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[DiscoveredOnvifDevice]:
    """Broadcast one probe and collect a bounded, deduplicated result set."""
    if not 0 < timeout_seconds <= 15:
        raise ValueError("Discovery timeout must be between zero and 15 seconds.")
    if not 1 <= maximum_devices <= 500:
        raise ValueError("Maximum discovery devices must be between 1 and 500.")
    client = socket_factory(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    discovered: dict[str, DiscoveredOnvifDevice] = {}
    try:
        client.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        client.bind((interface_ip, 0))
        client.sendto(_probe_message(), _MULTICAST_ADDRESS)
        deadline = monotonic() + timeout_seconds
        while len(discovered) < maximum_devices:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            client.settimeout(min(0.25, remaining))
            try:
                data, address = client.recvfrom(_MAX_RESPONSE_BYTES)
            except TimeoutError:
                continue
            remote = str(address[0])
            for device in parse_probe_matches(data, remote):
                key = device.endpoint_reference or "|".join(device.xaddrs)
                discovered.setdefault(key, device)
                if len(discovered) >= maximum_devices:
                    break
    finally:
        client.close()
    return list(discovered.values())

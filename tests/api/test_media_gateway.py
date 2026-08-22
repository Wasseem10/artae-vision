import asyncio

from video_intelligence_api.media_gateway import DisabledMediaGateway


def test_disabled_media_gateway_reports_honest_offline_state() -> None:
    gateway = DisabledMediaGateway()

    provisioned = asyncio.run(gateway.provision("camera-1", "publisher"))
    current = asyncio.run(gateway.state("camera-1"))
    asyncio.run(gateway.close())

    assert provisioned.configured is False
    assert provisioned.ready is False
    assert provisioned.readers == 0
    assert current == provisioned

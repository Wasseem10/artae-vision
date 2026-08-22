import asyncio

from video_intelligence_api.websockets import EventConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, object]) -> None:
        self.messages.append(message)


def test_websocket_broadcast_only_reaches_matching_organization() -> None:
    async def scenario() -> None:
        manager = EventConnectionManager()
        tenant_a = FakeWebSocket()
        tenant_b = FakeWebSocket()
        await manager.connect(tenant_a, "org-a")  # type: ignore[arg-type]
        await manager.connect(tenant_b, "org-b")  # type: ignore[arg-type]

        message = {"type": "event.created", "data": {"id": "event-1"}}
        await manager.broadcast(message, organization_id="org-a")

        assert tenant_a.accepted and tenant_b.accepted
        assert tenant_a.messages == [message]
        assert tenant_b.messages == []

    asyncio.run(scenario())

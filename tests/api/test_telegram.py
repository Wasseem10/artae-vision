import asyncio

import httpx
from video_intelligence_api.routes import actions as action_routes
from video_intelligence_api.telegram import discover_telegram_chats


def test_discovers_and_deduplicates_recent_telegram_chats() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getUpdates")
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {
                        "message": {
                            "chat": {
                                "id": 123,
                                "type": "private",
                                "first_name": "Wasseem",
                            }
                        }
                    },
                    {
                        "message": {
                            "chat": {
                                "id": 123,
                                "type": "private",
                                "first_name": "Wasseem",
                            }
                        }
                    },
                    {
                        "channel_post": {
                            "chat": {"id": -456, "type": "channel", "title": "Security"}
                        }
                    },
                ],
            },
        )

    chats = asyncio.run(
        discover_telegram_chats(
            "123456:telegram-test-token",
            transport=httpx.MockTransport(handler),
        )
    )

    assert chats == [
        {"chat_id": "123", "title": "Wasseem", "chat_type": "private"},
        {"chat_id": "-456", "title": "Security", "chat_type": "channel"},
    ]


def test_dashboard_can_discover_chats_without_returning_the_token(
    api_client, monkeypatch
) -> None:
    async def fake_discovery(token: str) -> list[dict[str, str]]:
        assert token == "123456:telegram-test-token"
        return [{"chat_id": "123", "title": "Wasseem", "chat_type": "private"}]

    monkeypatch.setattr(action_routes, "discover_telegram_chats", fake_discovery)
    response = api_client.post(
        "/api/v1/connectors/telegram/chats",
        json={"bot_token": "123456:telegram-test-token"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == [
        {"chat_id": "123", "title": "Wasseem", "chat_type": "private"}
    ]
    assert "telegram-test-token" not in response.text

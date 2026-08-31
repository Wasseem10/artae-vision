from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramDiscoveryError(RuntimeError):
    """A safe operator-facing Telegram discovery failure."""


def _chat_label(chat: dict[str, Any]) -> str:
    if title := chat.get("title"):
        return str(title)
    name = " ".join(
        str(part).strip() for part in (chat.get("first_name"), chat.get("last_name")) if part
    )
    if name:
        return name
    if username := chat.get("username"):
        return f"@{username}"
    return f"Telegram chat {chat.get('id')}"


async def discover_telegram_chats(
    bot_token: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, str]]:
    """Return recent destination chats without ever logging the URL-contained token."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/getUpdates",
                json={"allowed_updates": ["message", "channel_post"], "limit": 100},
            )
    except httpx.HTTPError as exc:
        logger.warning("Telegram chat discovery failed: error=%s", type(exc).__name__)
        raise TelegramDiscoveryError("Telegram could not be reached") from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise TelegramDiscoveryError("Telegram returned an invalid response") from exc
    if response.status_code < 200 or response.status_code >= 300 or result.get("ok") is not True:
        description = result.get("description")
        raise TelegramDiscoveryError(str(description or "Telegram rejected the bot token"))

    discovered: dict[str, dict[str, str]] = {}
    for update in result.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not isinstance(chat_id, (str, int)):
            continue
        normalized_id = str(chat_id)
        discovered[normalized_id] = {
            "chat_id": normalized_id,
            "title": _chat_label(chat),
            "chat_type": str(chat.get("type") or "unknown"),
        }
    return list(discovered.values())

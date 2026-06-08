import httpx
from loguru import logger

from app.config import get_settings


async def send_notification(title: str, message: str) -> None:
    settings = get_settings()
    text = f"[TimeRich] {title}: {message}"

    if settings.notify_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    settings.notify_webhook_url,
                    json={"text": text, "desp": message},
                )
        except Exception as exc:
            logger.warning("Server酱通知失败: {}", exc)

    if settings.notify_webhook_feishu:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    settings.notify_webhook_feishu,
                    json={"msg_type": "text", "content": {"text": text}},
                )
        except Exception as exc:
            logger.warning("飞书通知失败: {}", exc)

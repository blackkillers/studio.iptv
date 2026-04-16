import httpx
import os
import logging

logger = logging.getLogger("STUDIO.SocialPublisher")

async def publish_via_webhook(video_url: str, text: str, platforms: list):
    """
    Sends a publishing request to StudioAutomation or Make.com via Webhook.
    Cost-effective alternative to Ayrshare.
    """
    webhook_url = os.getenv("PUBLISH_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("[Social] PUBLISH_WEBHOOK_URL is missing. Skipping external publication.")
        return False

    import time
    payload = {
        "video_url": video_url,
        "description": text,
        "platforms": platforms,
        "timestamp": time.time()
    }

    headers = {}
    StudioAutomation_key = os.getenv("StudioAutomation_API_KEY")
    if StudioAutomation_key:
        headers["Authorization"] = f"Bearer {StudioAutomation_key}"

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"[Social] Sending Webhook to {webhook_url} for platforms: {platforms} (StudioAutomation mode)")
            resp = await client.post(webhook_url, json=payload, headers=headers, timeout=30)
            if resp.status_code in [200, 201]:
                logger.info("[Social] Webhook Success!")
                return True
            else:
                logger.error(f"[Social] Webhook Error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"[Social] Webhook Connection Failed: {e}")
        return False

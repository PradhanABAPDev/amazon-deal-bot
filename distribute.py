"""
Step 3: Multi-Channel Distribution.

Each function posts the processed deal to one channel and returns whatever
ID the platform gives back (message_id, post_id) — deal_tracker.py needs
those IDs to edit/expire posts later.
"""
import logging

import requests

import config

logger = logging.getLogger("distribute")


def post_to_telegram(deal: dict) -> str | None:
    """
    Posts the deal image + caption to a Telegram channel via the Bot API.
    Returns the Telegram message_id (needed later to edit the post when the
    deal expires or drops further).
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": config.TELEGRAM_CHANNEL_ID,
        "photo": deal["image_url"],
        "caption": deal["caption_with_disclosure"],
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        message_id = resp.json()["result"]["message_id"]
        logger.info("Posted to Telegram: message_id=%s", message_id)
        return message_id
    except requests.RequestException as exc:
        logger.error("Telegram post failed: %s", exc)
        return None


def edit_telegram_caption(message_id: int, new_caption: str) -> bool:
    """Used by deal_tracker.py to mark a previously posted deal as expired / price-dropped-further."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/editMessageCaption"
    payload = {
        "chat_id": config.TELEGRAM_CHANNEL_ID,
        "message_id": message_id,
        "caption": new_caption,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Telegram edit failed for message_id=%s: %s", message_id, exc)
        return False


def post_to_whatsapp(deal: dict) -> list[str]:
    """
    Sends the deal to each subscriber via the WhatsApp Cloud API.

    IMPORTANT: WhatsApp does not allow freeform marketing broadcasts. This
    sends a pre-approved Message Template (config.WHATSAPP_TEMPLATE_NAME)
    with the variable parts of the deal mapped to template placeholders.
    You must create and get that template approved in Meta Business
    Manager BEFORE this will work — see README caveat #4.

    Template example to submit for approval (category: MARKETING):
      "🚨 {{1}} price drop! {{2}} is now {{3}} ({{4}}% off). {{5}}"
      where {{1}}=headline, {{2}}=title, {{3}}=price, {{4}}=discount, {{5}}=link
    """
    url = (
        f"https://graph.facebook.com/{config.WHATSAPP_GRAPH_VERSION}/"
        f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}

    sent_message_ids = []
    for recipient in config.WHATSAPP_RECIPIENTS:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": config.WHATSAPP_TEMPLATE_NAME,
                "language": {"code": "en_US"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": deal["title"][:60]},
                            {"type": "text", "text": f"${deal['discounted_price']}"},
                            {"type": "text", "text": str(deal.get("discount_percent", "?"))},
                            {"type": "text", "text": deal["short_link"]},
                        ],
                    }
                ],
            },
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            sent_message_ids.append(resp.json()["messages"][0]["id"])
        except requests.RequestException as exc:
            logger.error("WhatsApp send failed for %s: %s", recipient, exc)

    logger.info("WhatsApp sent to %d/%d recipients", len(sent_message_ids), len(config.WHATSAPP_RECIPIENTS))
    return sent_message_ids


def post_to_facebook(deal: dict) -> str | None:
    """
    Publishes a photo post to a Facebook Page via the Graph API.
    Requires a Page Access Token with pages_manage_posts permission.
    """
    url = f"https://graph.facebook.com/{config.FACEBOOK_GRAPH_VERSION}/{config.FACEBOOK_PAGE_ID}/photos"
    payload = {
        "url": deal["image_url"],
        "caption": deal["caption_with_disclosure"],
        "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
    }
    try:
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
        post_id = resp.json().get("post_id") or resp.json().get("id")
        logger.info("Posted to Facebook: post_id=%s", post_id)
        return post_id
    except requests.RequestException as exc:
        logger.error("Facebook post failed: %s", exc)
        return None


def distribute_deal(deal: dict) -> dict:
    """
    Full Step 3 entry point. Posts to all three channels and returns the
    platform IDs needed for later monitoring/updates.
    """
    return {
        "telegram_message_id": post_to_telegram(deal),
        "whatsapp_message_ids": post_to_whatsapp(deal),
        "facebook_post_id": post_to_facebook(deal),
    }

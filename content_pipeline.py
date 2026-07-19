"""
Step 2: Data Processing & Formatting.

Takes a normalized deal dict from deal_scanner.py and adds:
  - a properly tagged Amazon affiliate link (if PA-API didn't already supply one)
  - a shortened Bitly link
  - an AI-generated caption (via the Anthropic API)
"""
import logging

import anthropic
import requests

import config

logger = logging.getLogger("content_pipeline")


def build_affiliate_link(deal: dict) -> str:
    """
    If PA-API already returned a tagged detail_page_url, use it (it's the
    most compliant/current option). Otherwise build the standard tagged
    link manually — equivalent to what SiteStripe generates.
    """
    if deal.get("affiliate_link"):
        return deal["affiliate_link"]
    return f"https://www.amazon.com/dp/{deal['asin']}?tag={config.AMAZON_ASSOCIATE_TAG}"


def shorten_link(long_url: str) -> str:
    """Shorten a URL via the Bitly API. Falls back to the long URL on failure."""
    try:
        resp = requests.post(
            "https://api-ssl.bitly.com/v4/shorten",
            headers={"Authorization": f"Bearer {config.BITLY_ACCESS_TOKEN}"},
            json={"long_url": long_url},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["link"]
    except requests.RequestException as exc:
        logger.warning("Bitly shortening failed (%s) — using long URL", exc)
        return long_url


CAPTION_SYSTEM_PROMPT = """You write short, high-urgency social captions for Amazon deal alerts.
Rules:
- Under 280 characters, emoji-rich but not spammy (2-4 emoji max).
- Lead with the discount, not the product category.
- Include the exact discounted price.
- End with a short urgency line (stock/time framing), not a hard CTA link (the link is added separately).
- Never invent claims about stock levels, ratings, or scarcity that weren't provided — use generic urgency
  language ("before this one's gone", "prices like this don't last") instead of fabricated specifics.
- Output only the caption text, nothing else."""


def generate_caption(deal: dict) -> str:
    """
    Uses the Anthropic API to generate a short, urgent caption for the deal.
    Requires ANTHROPIC_API_KEY in your environment.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_prompt = (
        f"Product: {deal['title']}\n"
        f"Original price: ${deal.get('original_price', 'N/A')}\n"
        f"Discounted price: ${deal['discounted_price']}\n"
        f"Discount: {deal.get('discount_percent', '?')}%"
    )

    message = client.messages.create(
        model=config.CAPTION_MODEL,
        max_tokens=200,
        system=CAPTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text.strip()


def process_deal(deal: dict) -> dict:
    """
    Full Step 2 entry point. Mutates and returns the deal dict with
    affiliate_link, short_link, and caption populated.
    """
    deal["affiliate_link"] = build_affiliate_link(deal)
    deal["short_link"] = shorten_link(deal["affiliate_link"])
    deal["caption"] = generate_caption(deal)
    # FTC / Amazon disclosure — required on every post, appended here so
    # every distribution channel gets it automatically rather than relying
    # on each poster function to remember.
    deal["caption_with_disclosure"] = (
        f"{deal['caption']}\n\n{deal['short_link']}\n\n"
        f"As an Amazon Associate I earn from qualifying purchases."
    )
    return deal


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from deal_scanner import scan_for_deals

    for d in scan_for_deals():
        print(process_deal(d))

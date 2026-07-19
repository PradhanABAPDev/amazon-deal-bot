"""
Step 1: Deal Hunting.

Discovery happens via Keepa's Deals API (no affiliate-sales prerequisite,
just a paid Keepa key). PA-API is used only for *enrichment* — pulling
Amazon-verified current price/title/image for the ASINs Keepa surfaced —
and only when your account currently has PA-API eligibility. If PA-API
calls fail (e.g. AssociateNotEligible), we fall back to the data Keepa
already returned and tag the link manually.

Run on a schedule every 15-30 minutes (see README for cron / Make.com setup).
"""
import logging
from typing import Optional

import keepa

import config

logger = logging.getLogger("deal_scanner")


def fetch_keepa_deals(min_discount_percent: int = None) -> list[dict]:
    """
    Query Keepa's Deals endpoint for products whose price just dropped by
    at least `min_discount_percent`. Returns Keepa's raw deal objects.
    """
    min_discount_percent = min_discount_percent or config.MIN_DISCOUNT_PERCENT
    api = keepa.Keepa(config.KEEPA_API_KEY)

    deal_parms = {
        "domainId": config.KEEPA_DOMAIN_ID,
        # priceTypes: 0 = Amazon price, 1 = New (3rd party), 2 = Used, 3 = Sales Rank
        "priceTypes": [0, 1],
        "isRangeEnabled": True,
        # deltaPercentRange filters on % drop between range start/end, e.g. 50-100%
        "deltaPercentRange": [min_discount_percent, 100],
        "isOutOfStock": False,
        "sortType": 4,  # sort by deal age, newest first — catches "newly added" drops
        "dateRange": 1,  # 1 = last 24h window Keepa considers for "new" deals
    }

    result = api.deals(deal_parms, domain="US")
    deals = result.get("dr", [])
    logger.info("Keepa returned %d deals >= %d%% off", len(deals), min_discount_percent)
    return deals


def normalize_keepa_deal(deal: dict) -> dict:
    """
    Keepa's raw deal object uses compact/encoded fields (prices in cents,
    current[] arrays keyed by priceType). Normalize into the flat shape the
    rest of the pipeline expects.
    """
    asin = deal.get("asin")
    title = deal.get("title", "Unknown product")
    image_suffix = deal.get("image", "")
    image_url = f"https://images-na.ssl-images-amazon.com/images/I/{image_suffix}" if image_suffix else None

    # current/avg arrays: index 0 = Amazon price, index 1 = New 3rd-party, in cents; -1 = unavailable
    current = deal.get("current", [])
    delta_pct = deal.get("deltaPercent", [])

    current_price_cents = next((p for p in current if p and p > 0), None)
    discount_percent = next((d for d in delta_pct if d and d > 0), 0)

    discounted_price = round(current_price_cents / 100, 2) if current_price_cents else None
    original_price = (
        round(discounted_price / (1 - discount_percent / 100), 2)
        if discounted_price and discount_percent
        else None
    )

    return {
        "asin": asin,
        "title": title,
        "image_url": image_url,
        "original_price": original_price,
        "discounted_price": discounted_price,
        "discount_percent": round(discount_percent, 1),
    }


def enrich_with_paapi(asin: str) -> Optional[dict]:
    """
    Best-effort PA-API enrichment for a single ASIN — pulls Amazon-verified
    price, title, and image, and generates a compliant tagged link via the
    SDK. Returns None (not raises) on any failure so the caller can fall
    back to Keepa-only data — this keeps a PA-API eligibility lapse from
    taking down the whole pipeline.
    """
    if not config.AMAZON_PAAPI_ACCESS_KEY or not config.AMAZON_PAAPI_SECRET_KEY:
        # PA-API is optional -- if it isn't configured, skip quietly instead
        # of throwing (and logging) an error on every single deal.
        return None

    try:
        from amazon_paapi import AmazonApi

        api = AmazonApi(
            config.AMAZON_PAAPI_ACCESS_KEY,
            config.AMAZON_PAAPI_SECRET_KEY,
            config.AMAZON_PAAPI_PARTNER_TAG,
            config.AMAZON_PAAPI_COUNTRY,
        )
        items = api.get_items([asin])
        if not items:
            return None
        item = items[0]

        return {
            "asin": asin,
            "title": item.item_info.title.display_value,
            "image_url": item.images.primary.large.url,
            "discounted_price": item.offers.listings[0].price.amount,
            "original_price": (
                item.offers.listings[0].price.amount
                + item.offers.listings[0].price.savings.amount
                if item.offers.listings[0].price.savings
                else None
            ),
            "discount_percent": (
                item.offers.listings[0].price.savings.percentage
                if item.offers.listings[0].price.savings
                else None
            ),
            "affiliate_link": item.detail_page_url,  # PA-API returns an already-tagged URL
        }
    except Exception as exc:  # noqa: BLE001 - intentionally broad; this is a soft fallback path
        logger.warning("PA-API enrichment failed for %s (%s) — falling back to Keepa data", asin, exc)
        return None


def scan_for_deals(min_discount_percent: int = None) -> list[dict]:
    """
    Full Step 1 entry point: discover deals, normalize, and enrich where
    possible. Returns a list of flat deal dicts ready for content_pipeline.py.
    """
    raw_deals = fetch_keepa_deals(min_discount_percent)
    results = []

    for raw in raw_deals:
        deal = normalize_keepa_deal(raw)
        if not deal["asin"] or not deal["discounted_price"]:
            continue  # skip incomplete records rather than posting bad data

        enriched = enrich_with_paapi(deal["asin"])
        if enriched:
            deal.update({k: v for k, v in enriched.items() if v is not None})

        results.append(deal)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for d in scan_for_deals():
        print(d)

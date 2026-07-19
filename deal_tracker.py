"""
Steps 4/5: Logging + Deal Expiration/Updates.

log_deal()      -> called once, right after a deal is first posted.
monitor_deals() -> run this on its own schedule (every 15-30 min) to re-check
                    every "Active" deal against current Keepa pricing and
                    edit the original Telegram post if the price dropped
                    further or the deal has expired.
"""
import argparse
import datetime
import logging

import keepa
from pyairtable import Table

import config
from distribute import edit_telegram_caption

logger = logging.getLogger("deal_tracker")

_table = Table(config.AIRTABLE_API_KEY, config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)


def log_deal(deal: dict, distribution_result: dict) -> str:
    """Creates the Airtable record for a newly posted deal. Returns the Airtable record ID."""
    fields = {
        "ASIN": deal["asin"],
        "Title": deal["title"],
        "OriginalPrice": deal.get("original_price"),
        "DiscountPrice": deal["discounted_price"],
        "DiscountPercent": deal.get("discount_percent"),
        "ImageURL": deal["image_url"],
        "AffiliateLink": deal["affiliate_link"],
        "ShortLink": deal["short_link"],
        "TelegramMessageID": distribution_result.get("telegram_message_id"),
        "FacebookPostID": distribution_result.get("facebook_post_id"),
        "Status": "Active",
        "LastChecked": datetime.datetime.utcnow().isoformat(),
    }
    record = _table.create(fields)
    logger.info("Logged deal %s to Airtable (record %s)", deal["asin"], record["id"])
    return record["id"]


def _get_current_price(asin: str) -> float | None:
    """Quick single-ASIN Keepa lookup for the monitor loop."""
    api = keepa.Keepa(config.KEEPA_API_KEY)
    # stats=1 is required here -- without it Keepa does not populate the
    # "stats"/"current" fields at all, and this would silently return None
    # for every deal, marking everything "Expired" on the very first check.
    products = api.query(asin, domain="US", history=False, stats=1)
    if not products:
        return None
    stats = products[0].get("stats", {})
    current = stats.get("current", [])
    price_cents = next((p for p in current if p and p > 0), None)
    return round(price_cents / 100, 2) if price_cents else None


def monitor_deals():
    """
    Re-checks every Active deal in Airtable. If price dropped further than
    what's logged, edits the Telegram post to flag it. If the item is out
    of stock / price crept back up above the discount threshold, marks it
    Expired and edits the Telegram post accordingly.
    """
    active_records = _table.all(formula="{Status} = 'Active'")
    logger.info("Monitoring %d active deals", len(active_records))

    for record in active_records:
        fields = record["fields"]
        asin = fields.get("ASIN")
        logged_price = fields.get("DiscountPrice")
        telegram_message_id = fields.get("TelegramMessageID")

        current_price = _get_current_price(asin)
        update_fields = {"LastChecked": datetime.datetime.utcnow().isoformat()}

        if current_price is None:
            # Couldn't find pricing at all — treat as expired/delisted.
            update_fields["Status"] = "Expired"
            if telegram_message_id:
                edit_telegram_caption(
                    telegram_message_id,
                    f"❌ <b>DEAL EXPIRED</b> — {fields.get('Title', 'This item')} is no longer available.",
                )

        elif current_price < logged_price:
            new_discount_pct = round(
                (1 - current_price / fields.get("OriginalPrice", current_price)) * 100, 1
            )
            update_fields.update(
                {
                    "Status": "PriceDroppedFurther",
                    "DiscountPrice": current_price,
                    "DiscountPercent": new_discount_pct,
                }
            )
            if telegram_message_id:
                edit_telegram_caption(
                    telegram_message_id,
                    f"🔥 <b>PRICE DROPPED FURTHER!</b> {fields.get('Title', 'This item')} "
                    f"is now just ${current_price} ({new_discount_pct}% off)!\n\n"
                    f"{fields.get('ShortLink', '')}",
                )

        elif current_price > fields.get("OriginalPrice", 0) * (1 - config.MIN_DISCOUNT_PERCENT / 100):
            # Price crept back up above the discount threshold — deal's over.
            update_fields["Status"] = "Expired"
            if telegram_message_id:
                edit_telegram_caption(
                    telegram_message_id,
                    f"❌ <b>DEAL EXPIRED</b> — price is back up on {fields.get('Title', 'this item')}.",
                )

        _table.update(record["id"], update_fields)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitor", action="store_true", help="Run the price/expiration monitor loop")
    args = parser.parse_args()

    if args.monitor:
        monitor_deals()
    else:
        print("Run with --monitor to check active deals, or import log_deal() from your pipeline.")

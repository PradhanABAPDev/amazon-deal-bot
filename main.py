"""
Orchestrator — one full cycle of the pipeline:
  scan (Keepa) -> process (tag/shorten/caption) -> distribute (TG/WA/FB) -> log (Airtable)

Trigger this every 15-30 minutes via cron, Task Scheduler, or a Make.com/
cloud-scheduler webhook. Run deal_tracker.py --monitor on a separate
schedule to handle price-drop/expiration updates for deals already posted.
"""
import logging

from pyairtable import Table

import config
from deal_scanner import scan_for_deals
from content_pipeline import process_deal
from distribute import distribute_deal
from deal_tracker import log_deal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

_table = Table(config.AIRTABLE_API_KEY, config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)


def already_posted(asin: str) -> bool:
    """Skip ASINs that already have an Active record so we don't double-post."""
    existing = _table.all(formula=f"AND({{ASIN}} = '{asin}', {{Status}} = 'Active')")
    return len(existing) > 0


def run_cycle():
    deals = scan_for_deals()
    logger.info("Scan complete: %d candidate deals >= %d%% off", len(deals), config.MIN_DISCOUNT_PERCENT)

    posted = 0
    for deal in deals:
        if already_posted(deal["asin"]):
            logger.info("Skipping %s — already actively posted", deal["asin"])
            continue

        try:
            deal = process_deal(deal)
            result = distribute_deal(deal)
            log_deal(deal, result)
            posted += 1
        except Exception:
            logger.exception("Failed to process/post deal for ASIN %s — skipping", deal.get("asin"))

    logger.info("Cycle complete: %d new deals posted", posted)


if __name__ == "__main__":
    run_cycle()

"""
Centralized configuration. All secrets come from environment variables /
.env — never hardcode credentials in the pipeline modules.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# --- Deal criteria ---
MIN_DISCOUNT_PERCENT = int(_env("MIN_DISCOUNT_PERCENT", "50"))

# --- Keepa ---
KEEPA_API_KEY = _env("KEEPA_API_KEY")
KEEPA_DOMAIN_ID = int(_env("KEEPA_DOMAIN_ID", "1"))  # 1 = amazon.com

# --- Amazon Associates / PA-API ---
AMAZON_ASSOCIATE_TAG = _env("AMAZON_ASSOCIATE_TAG")
AMAZON_PAAPI_ACCESS_KEY = _env("AMAZON_PAAPI_ACCESS_KEY")
AMAZON_PAAPI_SECRET_KEY = _env("AMAZON_PAAPI_SECRET_KEY")
AMAZON_PAAPI_PARTNER_TAG = _env("AMAZON_PAAPI_PARTNER_TAG", AMAZON_ASSOCIATE_TAG)
AMAZON_PAAPI_COUNTRY = _env("AMAZON_PAAPI_COUNTRY", "US")

# --- Bitly ---
BITLY_ACCESS_TOKEN = _env("BITLY_ACCESS_TOKEN")

# --- Anthropic (caption generation) ---
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
CAPTION_MODEL = _env("CAPTION_MODEL", "claude-sonnet-5")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = _env("TELEGRAM_CHANNEL_ID")

# --- WhatsApp Cloud API ---
WHATSAPP_ACCESS_TOKEN = _env("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_TEMPLATE_NAME = _env("WHATSAPP_TEMPLATE_NAME", "deal_alert")
WHATSAPP_RECIPIENTS = [
    n.strip() for n in _env("WHATSAPP_RECIPIENT_LIST").split(",") if n.strip()
]
WHATSAPP_GRAPH_VERSION = _env("WHATSAPP_GRAPH_VERSION", "v21.0")

# --- Facebook Page ---
FACEBOOK_PAGE_ACCESS_TOKEN = _env("FACEBOOK_PAGE_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = _env("FACEBOOK_PAGE_ID")
FACEBOOK_GRAPH_VERSION = _env("FACEBOOK_GRAPH_VERSION", "v21.0")

# --- Airtable ---
AIRTABLE_API_KEY = _env("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = _env("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = _env("AIRTABLE_TABLE_NAME", "Deals")

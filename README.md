# Amazon Deal Bot — Multi-Channel Affiliate Automation

An automated pipeline that finds Amazon deals ≥50% off, tags them with your
Associates ID, writes an AI caption, and posts to Telegram / WhatsApp /
Facebook — then monitors those deals for price changes or expiration.

```
┌─────────────┐   ┌──────────────────┐   ┌───────────────┐   ┌──────────────────┐   ┌─────────────┐
│  1. SCAN     │──▶│  2. ENRICH+TAG    │──▶│  3. CAPTION   │──▶│  4. DISTRIBUTE    │──▶│  5. LOG      │
│  Keepa Deals │   │  PA-API/SiteStripe│   │  Claude API   │   │  TG / WA / FB     │   │  Airtable    │
│  API         │   │  + Bitly shorten  │   │               │   │                   │   │              │
└─────────────┘   └──────────────────┘   └───────────────┘   └──────────────────┘   └──────┬───────┘
      ▲                                                                                     │
      │                     6. MONITOR (separate scheduled job, every 15-30 min)            │
      └─────────────────────── re-queries Keepa for tracked ASINs, edits Telegram msg ◀─────┘
```

Runs as five Python modules orchestrated by `main.py`, meant to be triggered by
cron / Task Scheduler / a Make.com scenario every 15–30 minutes.

---

## ⚠️ Read this before you build anything

**1. Amazon's Product Advertising API has a chicken-and-egg access gate.**
As of 2026, PA-API access requires an *already-approved* Associates account,
and Amazon is enforcing (unofficially — they haven't documented it, but it's
now widely reported) a requirement of **10 qualifying sales in the trailing
30 days** to keep your API credentials active — up from the older "3 sales in
180 days to join" rule. If your sales dip below that in any 30-day window, PA-API
calls start returning `AssociateNotEligible (403)` errors.

**Implication for this build:** you cannot use PA-API as your *discovery*
engine on day one, and if your channels go quiet for a month, your link-tagging
step can silently start failing. This blueprint uses:
- **Keepa** for discovery (no sales-history requirement, just a paid Keepa
  subscription) — this is the right tool for "find me everything down 50%+."
- **PA-API when eligible** for pulling verified live pricing and generating
  compliant links; **falls back to manual SiteStripe-style tagging** (just
  appending `?tag=yourtag-20` to a standard product URL) when PA-API isn't
  available. This fallback is compliant, just less automated (you don't get
  live-verified pricing/availability from Amazon on that call).

**2. PA-API does not have a "browse all deals ≥50% off" endpoint.**
It only returns data for ASINs you already give it (`GetItems`) or keyword
searches (`SearchItems`). It is not a deal-discovery tool — that's Keepa's job.

**3. Scraping Amazon directly (Apify or otherwise) violates Amazon's
Conditions of Use.** It can get your IPs blocked and, more importantly, can
get your *Associates account terminated* if it's linked to your scraping
activity. Keepa is a licensed third party that maintains its own independent
price-history database — it isn't scraping Amazon on your behalf. If you skip
Keepa for cost reasons, know that direct scraping is a real account-risk, not
just a technical inconvenience.

**4. WhatsApp Business API does not allow freeform broadcast/marketing
messages.** Any business-initiated message sent to a subscriber outside a
24-hour customer-service window must use a **pre-approved Message Template**
(Meta reviews and approves templates before you can send them). You cannot
dynamically stuff arbitrary AI-generated caption text into a marketing
broadcast — the template's structure has to be pre-approved, with variables
(`{{1}}`, `{{2}}`) for the parts that change (title, price, link). Budget time
for Meta's template review process; it's not instant.

**5. Facebook Graph API posting requires a Page Access Token** with
`pages_manage_posts` and `pages_read_engagement` permissions on a Page you
admin. If this app will ever be used by anyone other than you, Meta requires
App Review for those permissions at Advanced Access. For personal/single-page
use, a long-lived Page token is enough — generate it once via Graph API
Explorer and store it as a secret (Page tokens issued from a long-lived User
token don't expire on their own).

**6. Amazon disclosure/link rules still apply to every channel.** Every post
needs the "As an Amazon Associate I earn from qualifying purchases" (or
equivalent short-form FTC disclosure) visible on the post itself, and links
must use your real tag — not an obfuscated or unrelated shortener that hides
the Amazon destination. Bitly is fine as long as your bio/channel description
also carries the disclosure, since Amazon doesn't want the destination hidden
by the *shortener choice itself* — pair the shortened link with a caption that
makes clear it's an Amazon deal.

---

## Environment variables

Create a `.env` file (never commit it):

```
KEEPA_API_KEY=
AMAZON_ASSOCIATE_TAG=yourtag-20
AMAZON_PAAPI_ACCESS_KEY=
AMAZON_PAAPI_SECRET_KEY=
AMAZON_PAAPI_PARTNER_TAG=yourtag-20
BITLY_ACCESS_TOKEN=
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=@yourchannel
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_TEMPLATE_NAME=deal_alert
WHATSAPP_RECIPIENT_LIST=+15551234567,+15557654321
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_NAME=Deals
MIN_DISCOUNT_PERCENT=50
```

## Airtable schema (table: `Deals`)

| Field | Type |
|---|---|
| ASIN | Single line text (primary) |
| Title | Single line text |
| OriginalPrice | Number |
| DiscountPrice | Number |
| DiscountPercent | Number |
| ImageURL | URL |
| AffiliateLink | URL |
| ShortLink | URL |
| TelegramMessageID | Number |
| FacebookPostID | Single line text |
| Status | Single select (Active / PriceDroppedFurther / Expired) |
| LastChecked | Date |

## Running it locally

```bash
pip install -r requirements.txt
python main.py          # one full scan → process → distribute → log cycle
python deal_tracker.py --monitor   # run separately every 15-30 min to check for price drops/expiration
```

Schedule both with cron on a machine you control:
```
*/20 * * * * cd /path/to/amazon-deal-bot && python main.py >> scan.log 2>&1
*/20 * * * * cd /path/to/amazon-deal-bot && python deal_tracker.py --monitor >> monitor.log 2>&1
```

---

## Free 24/7 hosting: GitHub Actions

This repo includes `.github/workflows/deal-scan.yml` and
`.github/workflows/deal-monitor.yml`, which run the two scripts on a
schedule with **no server to manage and no cost**, as long as the repo is
public. (I checked current pricing across the usual free-tier options —
Render's cron jobs now start at $1/month, PythonAnywhere dropped free
scheduled tasks for new signups in January 2026 — GitHub Actions on a
public repo is the one that's actually still free and unlimited.)

**Setup:**
1. Push this folder to a new GitHub repository (public, so runner minutes
   stay uncapped — see the trade-off note below if you'd rather keep it
   private).
2. Go to **Settings → Secrets and variables → Actions → New repository
   secret**, and add every variable listed in the Environment Variables
   section above (`KEEPA_API_KEY`, `AMAZON_ASSOCIATE_TAG`, etc.) as a
   separate secret. Never commit a `.env` file to the repo.
3. The workflows are already scheduled — `deal-scan.yml` fires at :05/:25/:45
   past the hour, `deal-monitor.yml` at :15/:35/:55 (offset so they never
   race on the same Airtable record). Adjust the `cron:` lines if you want
   a different cadence.
4. To test immediately without waiting for the schedule, go to the
   **Actions** tab → select the workflow → **Run workflow** (this works
   because of the `workflow_dispatch` trigger already in the file).

**Things that will bite you if you don't know about them:**
- **Timing isn't exact.** GitHub's cron scheduler is best-effort; under
  platform load a job can fire 10-40 minutes late. Fine for a deal alert,
  not fine if you need it to the minute.
- **60-day auto-pause.** If nobody pushes a commit to the repo for 60 days,
  GitHub automatically disables scheduled workflows (silently — no email).
  A commit as trivial as updating the README resets the clock.
- **Public repo = public code, private secrets.** Your source is visible
  to anyone; your API keys are not (they only exist as encrypted repo
  secrets, injected as environment variables at runtime — they're never
  written into the workflow file or logs).
- **Private repo is possible but do the math first.** At a 20-minute
  cadence across both workflows you'll use roughly 4,000-4,500 runner
  minutes/month; the private-repo free allowance is 2,000/month. Either
  keep the repo public, drop to a 30-40 minute cadence, or accept a small
  monthly bill (~$0.006-0.008/minute over the free allowance).

---

## Make.com blueprint (no-code equivalent)

If you'd rather build this visually, here's the module-by-module scenario:

**Scenario A — Scan & Post (every 15–30 min, Scheduler trigger)**
1. **Schedule** module → every 20 minutes.
2. **HTTP → Make a request**: `POST https://api.keepa.com/deal?key={{KEEPA_API_KEY}}`
   with JSON body `selection` containing `deltaPercentRange: [50,100]`,
   `isRangeEnabled: true`, `priceTypes: [0]`, `domainId: 1`.
3. **Iterator** module → iterate over the returned `dr` (deals) array.
4. **Filter**: only continue if `deltaPercent >= 50` (belt-and-suspenders on
   top of the API filter) and ASIN not already `Active` in Airtable (use an
   **Airtable → Search Records** module here, then a Filter on "0 records
   found").
5. **HTTP** (conditional, only if PA-API eligible): call PA-API `GetItems` for
   verified price/title/image; otherwise use the fields Keepa already gave you.
6. **Text parser / Set variable**: build affiliate link as
   `https://www.amazon.com/dp/{{ASIN}}?tag={{AMAZON_ASSOCIATE_TAG}}`.
7. **HTTP → Bitly**: `POST https://api-ssl.bitly.com/v4/shorten` with
   `{"long_url": "{{affiliate_link}}"}`.
8. **HTTP → Anthropic Messages API**: `POST https://api.anthropic.com/v1/messages`
   with your prompt (see `content_pipeline.py` for the exact system prompt) to
   generate the caption text.
9. **Telegram Bot → Send a Photo** module: chat ID = your channel, photo =
   image URL, caption = generated text + short link. **Save the returned
   `message_id`.**
10. **HTTP → WhatsApp Cloud API**: `POST https://graph.facebook.com/v21.0/{{PHONE_NUMBER_ID}}/messages`
    sending a template message (see caveat #4 above — this must reference an
    approved template name, not freeform text) with the price/title/link as
    template variables. Use an **Iterator** here if broadcasting to multiple
    numbers.
11. **Facebook Pages → Create a Photo Post** module: page = your page, photo
    URL = product image, message = caption + short link.
12. **Airtable → Create a Record**: log ASIN, prices, discount %, links,
    `TelegramMessageID`, `FacebookPostID`, `Status = Active`, `LastChecked = now`.

**Scenario B — Monitor & Update (separate Scheduler, every 15–30 min)**
1. **Schedule** module.
2. **Airtable → Search Records**: `Status = Active`.
3. **Iterator** over those records.
4. **HTTP → Keepa** `GetItems`-equivalent (single ASIN lookup) to get current price.
5. **Router** with two branches:
   - Branch 1 (price dropped further than logged `DiscountPrice`): **Telegram
     → Edit Message Caption** using the stored `TelegramMessageID`, prefixing
     "🔥 PRICE DROPPED FURTHER!"; then **Airtable → Update Record** with new
     price and `Status = PriceDroppedFurther`.
   - Branch 2 (deal no longer meets ≥50% threshold / out of stock): **Telegram
     → Edit Message Caption** to "❌ Deal Expired"; **Airtable → Update Record**
     `Status = Expired`.

That's the entire no-code mapping — every HTTP module above corresponds
1:1 to a function in the Python files in this folder, so you can prototype
in Make.com and later port to code (or vice versa) without re-deriving logic.

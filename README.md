# 🕵️ Deal Hunter — Electronics deal-scraper Telegram bot

A Telegram bot that hunts for the best deals on electronics (iPhone, MacBook,
PS5, etc.) on **Carousell Singapore**, and pings you when new matches appear. It
runs on [Render](https://render.com) 24/7, scanning your saved searches every
few hours, and you can also ask it to search on demand right from the chat.

```
You:  /search iphone 15 pro
Bot:  🔎 Top matches for "iphone 15 pro":
      💰 S$1,050 — iPhone 15 Pro 256GB (Tampines · Lightly used)
      💰 S$1,150 — iPhone 15 Pro Max 256GB ...
```

---

## Features

- 🔎 **On-demand search** — `/search iphone 15` or just type what you want.
- 🔔 **Saved watches** — `/watch macbook air|1400|m2;m3` and get alerted when new
  matching listings show up (price cap + keyword filters).
- ⏰ **Scheduled scans** — runs every few hours (configurable) and messages all
  subscribers about *new* deals only (no repeats).
- 💸 **Smart filtering** — filter by max price and keywords; results ranked
  cheapest-first.
- 🧩 **Pluggable sources** — Carousell is built in; add more marketplaces by
  dropping in a new scraper (see below).
- ☁️ **Render-ready** — one web service, a health endpoint, and a `/scan`
  trigger for external cron.

---

## 1. Create your Telegram bot

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, pick a name and username. BotFather gives you a **token**
   like `123456789:AAE...`. Keep it secret.
3. (Optional) Send `/start` to your new bot; the bot replies with your **chat
   id**. You can also use [@userinfobot](https://t.me/userinfobot).

You don't strictly need the chat id — once the bot is running, send it
`/subscribe` and it remembers the chat. `TELEGRAM_CHAT_ID` is just a convenient
default recipient for scheduled alerts.

---

## 2. Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env and paste your TELEGRAM_BOT_TOKEN
python main.py
```

Now message your bot on Telegram:

| Command | What it does |
|---|---|
| `/start` | Subscribe this chat + show help |
| `/search <query>` | Search Carousell right now |
| `/watch query\|maxPrice\|kw1;kw2` | Save a recurring watch (price & keywords optional) |
| `/watches` | List built-in + your saved watches |
| `/unwatch <id>` | Remove a saved watch |
| `/scan` | Run all watches now, show new deals |
| `/app` | Open the visual deal browser (Mini App) |
| `/subscribe` / `/unsubscribe` | Toggle automatic alerts in this chat |
| `/help` | Show help |

Any plain text you send (not a command) is treated as a search query.

**Watch spec format:** `query|maxPrice|kw1;kw2`
- `query` — what to search (required)
- `maxPrice` — only alert below this price (optional)
- `kw1;kw2` — title must contain at least one of these keywords (optional)

Examples:
- `/watch iphone 15|900|256;pro` → iPhone 15 under $900 mentioning "256" or "pro"
- `/watch macbook air|1400|` → any MacBook Air under $1400
- `/watch airpods pro` → any AirPods Pro, any price

---

## 📱 The Mini App (in-Telegram web view)

Besides the text commands, the bot ships a **Telegram Mini App** — a real web
view that pops up *inside* Telegram with a card UI for browsing deals and a form
for managing watches. It's launched two ways:

- The **☰ menu button** next to the message box (set automatically on startup).
- The **/app** command, which sends an "Open Deal Hunter" button.

The page is served by the app itself at `/webapp`, and it talks to a small JSON
API (`/api/search`, `/api/watches`, `/api/scan`). Every API call is
authenticated by validating Telegram's signed
[`initData`](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)
against your bot token — no separate login, and requests can't be forged.

**Requirements:** a public **https** URL. On Render that's automatic
(`RENDER_EXTERNAL_URL`), so the Mini App just works once deployed — no extra
config. Locally you'd need an https tunnel (e.g. ngrok) and to set `WEBAPP_URL`
to it; set `WEBAPP_ALLOW_INSECURE=1` **only** for local testing to skip
`initData` validation (never in production).

## ⚡ Important: Carousell is behind Cloudflare

Carousell is protected by a **Cloudflare anti-bot challenge**, so a plain
request from a server (like Render) gets a "Just a moment…" page instead of
results — **Carousell searches return nothing without a backend that solves
it.** There are two options (and you can skip Carousell entirely and just use
[eBay](#-recommended-free-source-ebay-always-works)):

### Option A — Apify (recommended): handles Cloudflare *and* parsing

An Apify Actor runs a real browser (passing Cloudflare) and returns structured
listings, so there's no fragile HTML parsing.

1. Sign up at **[apify.com](https://apify.com)** (free plan = **$5 credits/mo**).
2. **Settings → Integrations → API token**, copy it → set as `APIFY_TOKEN`.
3. In the **Apify Store**, search "Carousell", pick a **free-to-use** Actor,
   copy its **Actor ID** (like `username~actor-name`) → set as `APIFY_ACTOR_ID`.

When both are set, Carousell is scraped via Apify automatically. Actors differ
in their input key for the search term — if results are empty, inspect the
Actor's real output and tune `APIFY_QUERY_FIELD` (try `search`, `keywords`, or
`queries`; set `APIFY_QUERY_AS_LIST=1` if it wants a list):
```
GET https://<your-url>/debug/apify?token=<SCAN_TOKEN>&q=iphone
```
That returns the input sent, the item count, and the **first raw item** so the
field names are visible.

### Option B — a scraping API (ScraperAPI / Scrape.do)

Route Carousell through a scraping API that solves Cloudflare. Set
`SCRAPER_API_KEY` (from [scraperapi.com](https://www.scraperapi.com)). Note:
Cloudflare bypass needs their **premium/ultra tier** — the free plan's
datacenter proxies usually still get blocked, so **Apify or eBay are the better
free choices**. Verify with:
```
GET https://<your-url>/debug/carousell?token=<SCAN_TOKEN>&q=iphone
```
Healthy = `"status": 200`, `"json_parsed": true`, non-zero `"extracted_listings"`.

**Budget note (both options):** keep watches few and `SCAN_INTERVAL_HOURS` high
(12 default) to stay within free credits.

## ✅ Recommended free source: eBay (always works)

Because Carousell's Cloudflare wall needs a *paid* scraping tier to beat
reliably, the bot also supports **eBay's official Browse API** — free,
legitimate, and never bot-walled. It's a **multi-source** setup: Carousell and
eBay run together, and results are merged. If you only set up eBay, the bot
works perfectly on its own.

**Setup (free):**
1. Sign up at **[developer.ebay.com](https://developer.ebay.com)** →
   **Application Keys** → create a keyset.
2. Copy the **Production App ID (Client ID)** and **Cert ID (Client Secret)**.
3. Set them as `EBAY_APP_ID` and `EBAY_CERT_ID` in your environment / Render.

That's it — the bot auto-enables eBay when both keys are present. Set
`EBAY_MARKETPLACE` (default `EBAY_SG`; use `EBAY_US` if SG errors for your
account). eBay is free and effectively unlimited for personal use, so it's the
dependable backbone; treat Carousell (via scraping API) as a bonus when you
have credits.

> Trade-off: eBay is a global catalogue (sellers worldwide, often shipping to
> SG) rather than the local Carousell second-hand market — great for "cheapest
> available," lighter on local used bargains.

## 3. Deploy to Render (24/7)

This repo includes a [`render.yaml`](./render.yaml) blueprint.

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at your repo. Render reads
   `render.yaml` and creates a **web service**.
3. In the service's **Environment** tab, set the secrets (`sync: false` means
   Render won't read them from the file):
   - `TELEGRAM_BOT_TOKEN` — your BotFather token (**required**)
   - `TELEGRAM_CHAT_ID` — optional default alert recipient
   - Tweak `DEFAULT_WATCHES`, `SCAN_INTERVAL_HOURS`, etc. as you like.
4. Deploy. The health check at `/healthz` should go green, and the bot starts
   polling Telegram.

### Keeping it awake on the free plan

Render's **free web service sleeps after ~15 min of no HTTP traffic**, which
would pause the scan job. Two ways to keep it alive 24/7:

- **Easiest:** use a free uptime pinger (e.g.
  [cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com))
  to `GET https://<your-app>.onrender.com/healthz` every 10 minutes.
- **Bonus — drive the scans externally:** point that same cron at
  `GET https://<your-app>.onrender.com/scan?token=<SCAN_TOKEN>` on your desired
  cadence. `SCAN_TOKEN` is auto-generated by `render.yaml`; copy its value from
  the Render dashboard. This both keeps the app awake *and* triggers a scan.

On a **paid** plan the service never sleeps, so the built-in scheduler alone is
enough — no pinger required.

### Persisting "already seen" history (optional)

Render's free filesystem is wiped on each redeploy, so the "seen listings"
database resets and you may get **one** repeat alert after a deploy. To avoid
that, attach a small **Render Disk** mounted at `./data` (uncomment the `disk:`
block in `render.yaml`; requires a paid plan).

---

## Configuration reference

All configuration is via environment variables (see [`.env.example`](./.env.example)):

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** BotFather token. |
| `TELEGRAM_CHAT_ID` | — | Optional default recipient for scheduled alerts. |
| `SCAN_INTERVAL_HOURS` | `3` | Hours between scheduled scans. |
| `DEFAULT_WATCHES` | — | Comma-separated built-in watches (`query\|maxPrice\|kw1;kw2`). |
| `CAROUSELL_HOST` | `www.carousell.sg` | Regional Carousell host. |
| `MAX_RESULTS` | `40` | Max listings fetched per query per source. |
| `SCRAPER_API_KEY` | — | Scraping-API key to bypass Carousell's Cloudflare. **Needed for results.** |
| `SCRAPER_PROVIDER` | `scraperapi`* | Backend: `scraperapi`, `scrapedo`, or `direct`. |
| `SCRAPER_ULTRA_PREMIUM` | `true` | Use premium proxies (needed for Cloudflare; costs more credits). |
| `SCRAPER_RENDER` | `true` | Execute JS on fetch. |
| `SCRAPER_COUNTRY` | `sg` | Proxy country. |

| `EBAY_APP_ID` | — | eBay Production App ID (Client ID). Enables the eBay source. |
| `EBAY_CERT_ID` | — | eBay Production Cert ID (Client Secret). |
| `EBAY_MARKETPLACE` | `EBAY_SG` | eBay marketplace (e.g. `EBAY_US`, `EBAY_GB`). |
| `EBAY_ENV` | `production` | `production` or `sandbox`. |
| `APIFY_TOKEN` | — | Apify API token. With `APIFY_ACTOR_ID`, routes Carousell via Apify. |
| `APIFY_ACTOR_ID` | — | Apify Carousell Actor id, e.g. `username~actor-name`. |
| `APIFY_QUERY_FIELD` | `search` | The Actor's input key for the search term. |
| `APIFY_QUERY_AS_LIST` | `false` | Wrap the query in a list if the Actor expects one. |
| `APIFY_MAX_FIELD` | `maxItems` | The Actor's input key for the result cap. |
| `APIFY_EXTRA_INPUT` | — | Extra Actor input merged in, as JSON. |

*`SCRAPER_PROVIDER` defaults to `scraperapi` when `SCRAPER_API_KEY` is set, otherwise `direct` (no proxy — Carousell will be blocked). The **eBay** source turns on automatically when both eBay keys are set; you can run eBay only, Carousell only, or both.
| `SCAN_TOKEN` | — | Shared secret guarding `GET /scan`. |
| `WEBAPP_URL` | *(RENDER_EXTERNAL_URL)* | Public https base URL for the Mini App. Auto on Render. |
| `WEBAPP_ALLOW_INSECURE` | `false` | Dev-only: skip Telegram initData validation. |
| `PORT` | `10000` | HTTP port (Render sets this automatically). |
| `DATA_DIR` | `data` | Where the SQLite DB lives. |

---

## How it works

```
                 ┌──────────────┐   every N hours (job queue)
   Telegram  ◄───┤ telegram_bot ├───────────────┐
   commands  ───►│  (handlers)  │                ▼
                 └──────┬───────┘         ┌──────────────┐
                        │                 │ DealService  │  run_scan()
                        ▼                 │  ┌────────────┴────────┐
                 ┌──────────────┐         │  │ ScraperRegistry     │
                 │  Flask /scan │────────►│  │  └► CarousellScraper │──► carousell.sg
                 │   /healthz   │         │  ├─ matcher (price/kw)  │
                 └──────────────┘         │  └─ Store (SQLite dedup)│
                                          └─────────────────────────┘
```

- **`app/scrapers/`** — one class per source. Carousell has two backends:
  `apify.py` (an Apify Actor that passes Cloudflare and returns structured
  data — recommended) and `carousell.py` (direct/scraping-API fetch + a
  tolerant `__NEXT_DATA__` extractor). `ebay.py` is the official-API source.
  `fetcher.py` routes non-Apify Carousell fetches through a scraping API.
  `registry.py` picks the Carousell backend from your env and merges sources.
- **`app/core/`** — the `Listing` model, price/keyword `matcher`, and a small
  SQLite `Store` (de-dup + saved watches + subscribers).
- **`app/service.py`** — orchestrates a scan: search → filter → keep only listings
  not seen before.
- **`app/bot/`** — Telegram command handlers + message formatting.
- **`app/webapp/`** — the Mini App: static page (`static/`), JSON API
  (`api.py`), and Telegram `initData` validation (`auth.py`).
- **`main.py`** — runs the bot (long polling) and a Flask server (health +
  Mini App) together.

### Adding another marketplace

1. Subclass `BaseScraper` in `app/scrapers/`, implement
   `search(query, limit) -> list[Listing]`. Never raise for network/parse
   errors — return `[]` and log.
2. Register it in `ScraperRegistry.default()`.

That's it — matching, de-dup, alerts and commands all work automatically.

---

## Development

```bash
source .venv/bin/activate
pytest -q          # run the test suite
```

Tests cover price/keyword matching, the SQLite store (dedup, re-pricing,
watches, subscribers), config parsing, and the Carousell JSON extractor against
a fixture.

---

## ⚠️ A note on scraping

Marketplaces change their markup and may rate-limit or block automated traffic;
scraping can also run up against a site's Terms of Service. This project is for
personal, low-volume use — keep `SCAN_INTERVAL_HOURS` reasonable (a few hours),
and if Carousell changes its page structure you may need to update
`app/scrapers/carousell.py` (`extract_listings` / `_looks_like_listing`).

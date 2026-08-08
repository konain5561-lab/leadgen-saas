# Google Maps Lead Scraper

Scrapes business listings from Google Maps search results (name, category,
rating, review count, address, phone, website), then optionally enriches
each lead with a contact email pulled from the business's own website.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Usage

**1. Scrape a search area:**

```bash
python scraper.py "dentists in Karachi" --limit 40 --out leads
```

This produces `leads.json` and `leads.csv` with one row per business.

Options:
- `--limit N` — how many listings to pull (default 20)
- `--out prefix` — output filename prefix
- `--headed` — run with a visible browser window (useful for debugging
  when Google changes its page layout and selectors stop matching)

**2. Enrich with emails (optional, slower):**

```bash
python enrich.py leads.json --out leads_enriched
```

This visits each business's website (home + `/contact`, `/about`, etc.)
and pulls a `mailto:` address or an email-shaped string from the page.
Many small business sites don't expose an email at all (contact-form
only) — those records will just have `email: ""`.

## Rate limiting & getting blocked

Google actively detects scraping traffic. To reduce the chance of getting
rate-limited or CAPTCHA'd:

- Don't run many searches back-to-back in a tight loop — the script
  already adds randomized delays between listings, but space out
  separate `scraper.py` runs by a few minutes.
- Consider running behind a residential proxy for higher volume (add
  `proxy={"server": "..."}` to the `chromium.launch()` call).
- If Google starts showing a CAPTCHA, run with `--headed` and solve it
  manually once — cookies/session state aren't persisted between runs
  in this basic version, so for heavy use you'd want to add a persistent
  browser context (`launch_persistent_context`) so you don't hit the
  CAPTCHA every single run.

## Selector maintenance

Google changes its Maps UI periodically, which breaks CSS selectors.
If fields start coming back empty, open Chrome DevTools on a Maps
listing page, inspect the relevant element, and update the `SEL_*`
constants at the top of `scraper.py`.

## Legal note

This scrapes Google's public web UI rather than an official API, which
is against Google's Terms of Service. This script is meant for your own
lead-research use — keep volume reasonable, and check the rules that
apply in your jurisdiction and Google's current ToS before relying on
this for a production/commercial service.

## Next steps in the pipeline

This is stage 1 of the SaaS system:

1. **Scraper (this)** → raw business data
2. Lead scoring — rate each business on "needs business development
   help" using rating, review count/recency, missing website, etc.
3. AI chat layer — ask questions over the scraped + scored leads
4. Outreach generator — AI drafts personalized email/WhatsApp messages
   per lead

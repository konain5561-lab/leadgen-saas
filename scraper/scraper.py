"""
Google Maps business scraper.

Given a search query like "dentists in Karachi", this drives a real
Chromium browser (via Playwright) through Google Maps, scrolls the
results feed to load listings, opens each listing, and extracts:

    name, category, rating, review_count, address, phone,
    website, google_maps_url

Output is written to a JSON file and a CSV file.

USAGE
-----
    pip install -r requirements.txt
    playwright install chromium
    python scraper.py "dentists in Karachi" --limit 40 --out leads

NOTES / CAVEATS
----------------
- This scrapes Google's public web UI, not an official API. Google's
  Terms of Service prohibit automated scraping, and Google actively
  detects and blocks bot traffic (rate limiting, CAPTCHAs, IP bans).
  Use conservative delays, don't hammer it in parallel, and expect to
  maintain the CSS selectors below over time as Google changes markup.
- Google Maps does not expose email addresses. If you need emails,
  run the separate `enrich.py` step against each business's `website`
  field to pull a contact email off their own site.
- Respect robots.txt / local law where you operate this. This tool is
  provided for legitimate business-development / lead research use.
"""

import argparse
import asyncio
import csv
import json
import random
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

GOOGLE_MAPS_URL = "https://www.google.com/maps/search/{query}"

# Selectors are based on Google Maps' current (2025-2026) DOM structure.
# Google changes these periodically -- if scraping breaks, inspect the
# page (F12) and update the selectors below.
SEL_RESULTS_FEED = 'div[role="feed"]'
SEL_RESULT_CARD = 'div[role="feed"] > div > div[jsaction]'
SEL_RESULT_LINK = "a.hfpxzc"
SEL_PANEL_NAME = "h1.DUwDvf"
SEL_PANEL_RATING = 'div.F7nice span[aria-hidden="true"]'
SEL_PANEL_REVIEW_COUNT = "div.F7nice span span"
SEL_PANEL_CATEGORY = "button.DkEaL"
SEL_PANEL_ADDRESS = 'button[data-item-id="address"]'
SEL_PANEL_PHONE = 'button[data-item-id^="phone"]'
SEL_PANEL_WEBSITE = 'a[data-item-id="authority"]'


@dataclass
class Business:
    name: str = ""
    category: str = ""
    rating: str = ""
    review_count: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    google_maps_url: str = ""
    search_query: str = ""


async def human_delay(a=0.4, b=1.2):
    await asyncio.sleep(random.uniform(a, b))


async def scroll_results(page: Page, target_count: int, max_scrolls: int = 40):
    """Scroll the results feed until we have ~target_count listings loaded."""
    feed = page.locator(SEL_RESULTS_FEED)
    await feed.wait_for(timeout=15000)

    seen = 0
    stagnant_rounds = 0
    for _ in range(max_scrolls):
        cards = page.locator(SEL_RESULT_LINK)
        count = await cards.count()
        if count >= target_count:
            break
        if count == seen:
            stagnant_rounds += 1
            if stagnant_rounds >= 3:
                # No new results after several scrolls -- likely end of list
                break
        else:
            stagnant_rounds = 0
        seen = count

        # Scroll the feed container, not the whole page
        await feed.evaluate("(el) => el.scrollBy(0, el.scrollHeight)")
        await human_delay(0.8, 1.6)


async def extract_listing_links(page: Page, limit: int) -> list[str]:
    links = page.locator(SEL_RESULT_LINK)
    count = min(await links.count(), limit)
    hrefs = []
    for i in range(count):
        href = await links.nth(i).get_attribute("href")
        if href:
            hrefs.append(href)
    return hrefs


async def safe_text(page: Page, selector: str) -> str:
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return ""
        return (await loc.inner_text()).strip()
    except PWTimeout:
        return ""


async def safe_attr(page: Page, selector: str, attr: str) -> str:
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return ""
        val = await loc.get_attribute(attr)
        return val or ""
    except PWTimeout:
        return ""


async def scrape_listing(page: Page, url: str, query: str) -> Business:
    biz = Business(google_maps_url=url, search_query=query)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await human_delay(0.6, 1.3)

    try:
        await page.locator(SEL_PANEL_NAME).first.wait_for(timeout=10000)
    except PWTimeout:
        return biz  # page didn't load the detail panel in time

    biz.name = await safe_text(page, SEL_PANEL_NAME)
    biz.rating = await safe_text(page, SEL_PANEL_RATING)

    review_raw = await safe_text(page, SEL_PANEL_REVIEW_COUNT)
    match = re.search(r"[\d,]+", review_raw)
    biz.review_count = match.group(0).replace(",", "") if match else ""

    biz.category = await safe_text(page, SEL_PANEL_CATEGORY)
    biz.address = await safe_text(page, SEL_PANEL_ADDRESS)
    biz.phone = await safe_text(page, SEL_PANEL_PHONE)
    biz.website = await safe_attr(page, SEL_PANEL_WEBSITE, "href")

    return biz


async def run(query: str, limit: int, headless: bool, out_prefix: str):
    results: list[Business] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()

        search_url = GOOGLE_MAPS_URL.format(query=query.replace(" ", "+"))
        print(f"[+] Opening: {search_url}", file=sys.stderr)
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await human_delay(1.0, 2.0)

        # Dismiss consent dialog if it appears (EU/first-run)
        try:
            consent_btn = page.locator('button:has-text("Accept all")').first
            if await consent_btn.count() > 0:
                await consent_btn.click(timeout=3000)
                await human_delay()
        except PWTimeout:
            pass

        print("[+] Scrolling results...", file=sys.stderr)
        await scroll_results(page, target_count=limit)

        links = await extract_listing_links(page, limit)
        print(f"[+] Found {len(links)} listing links", file=sys.stderr)

        detail_page = await context.new_page()
        for i, href in enumerate(links, 1):
            print(f"[{i}/{len(links)}] Scraping {href[:80]}...", file=sys.stderr)
            try:
                biz = await scrape_listing(detail_page, href, query)
                results.append(biz)
            except Exception as e:
                print(f"    ! failed: {e}", file=sys.stderr)
            await human_delay(1.0, 2.2)  # be gentle -- avoid rate limiting

        await browser.close()

    # Write outputs
    out_json = Path(f"{out_prefix}.json")
    out_csv = Path(f"{out_prefix}.csv")

    out_json.write_text(json.dumps([asdict(b) for b in results], indent=2), encoding="utf-8")

    if results:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            writer.writeheader()
            for b in results:
                writer.writerow(asdict(b))

    print(f"[+] Saved {len(results)} businesses -> {out_json} , {out_csv}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps business listings.")
    parser.add_argument("query", help='Search query, e.g. "dentists in Karachi"')
    parser.add_argument("--limit", type=int, default=20, help="Max listings to scrape")
    parser.add_argument("--out", default="leads", help="Output file prefix (leads.json/leads.csv)")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser (debugging)")
    args = parser.parse_args()

    asyncio.run(run(args.query, args.limit, headless=not args.headed, out_prefix=args.out))


if __name__ == "__main__":
    main()

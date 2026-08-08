"""
Email enrichment step.

Google Maps doesn't expose email addresses, so this takes the `website`
field from scraper.py's output and visits each business's site (home
page + common contact-page paths) looking for a mailto: link or an
email pattern in the page text.

USAGE
-----
    python enrich.py leads.json --out leads_enriched

This is best-effort: many small business sites hide emails behind
contact forms with no visible address, in which case `email` stays
empty for that record.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
CONTACT_PATHS = ["", "contact", "contact-us", "about", "about-us"]

# Skip obvious placeholder/tracking pixel addresses
IGNORE_DOMAINS = {"example.com", "sentry.io", "wixpress.com", "godaddy.com"}


def clean_emails(raw_emails: set[str]) -> list[str]:
    cleaned = []
    for e in raw_emails:
        domain = e.split("@")[-1].lower()
        if domain in IGNORE_DOMAINS:
            continue
        cleaned.append(e)
    return sorted(set(cleaned))


async def find_email_on_site(page, base_url: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.scheme:
        base_url = "https://" + base_url

    found: set[str] = set()
    for path in CONTACT_PATHS:
        url = urljoin(base_url + "/", path)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except (PWTimeout, Exception):
            continue

        # mailto: links first -- most reliable signal
        try:
            mailtos = await page.locator('a[href^="mailto:"]').all()
            for m in mailtos:
                href = await m.get_attribute("href") or ""
                addr = href.replace("mailto:", "").split("?")[0].strip()
                if addr:
                    found.add(addr)
        except Exception:
            pass

        # fallback: scan visible text for email-shaped strings
        try:
            text = await page.inner_text("body")
            found.update(EMAIL_RE.findall(text))
        except Exception:
            pass

        if found:
            break  # stop once we've found something on this site

    cleaned = clean_emails(found)
    return cleaned[0] if cleaned else ""


async def run(in_path: str, out_prefix: str):
    records = json.loads(Path(in_path).read_text(encoding="utf-8"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, rec in enumerate(records, 1):
            website = rec.get("website", "")
            if not website:
                rec["email"] = ""
                continue
            print(f"[{i}/{len(records)}] {website}", file=sys.stderr)
            try:
                rec["email"] = await find_email_on_site(page, website)
            except Exception as e:
                print(f"    ! failed: {e}", file=sys.stderr)
                rec["email"] = ""

        await browser.close()

    out_json = Path(f"{out_prefix}.json")
    out_json.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"[+] Saved -> {out_json}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Enrich scraped leads with contact emails.")
    parser.add_argument("input", help="Path to leads.json from scraper.py")
    parser.add_argument("--out", default="leads_enriched")
    args = parser.parse_args()
    asyncio.run(run(args.input, args.out))


if __name__ == "__main__":
    main()

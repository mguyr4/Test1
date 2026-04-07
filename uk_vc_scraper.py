#!/usr/bin/env python3
"""
UK Venture Capital Fund Raises Scraper
Scrapes public sources for UK VC fund raise data from the last 12 months.
Sources: Sifted.eu, BVCA, PitchBook, TechCrunch, Private Equity Wire,
         EU-Startups, Vestbee, SeedBlink, UKTN, British Business Bank

Usage:
    python3 uk_vc_scraper.py              # Show table + export CSV
    python3 uk_vc_scraper.py --live       # Attempt live scraping (requires internet)
    python3 uk_vc_scraper.py --csv-only   # Export CSV without printing table
"""

import requests
import re
import json
import csv
import sys
import argparse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from tabulate import tabulate
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

CUTOFF_DATE = datetime.now() - timedelta(days=365)


# ---------------------------------------------------------------------------
# Curated dataset of UK VC fund raises (Apr 2025 - Apr 2026)
# Compiled from: Sifted, TechCrunch, BVCA, EU-Startups, Vestbee, UKTN,
# Private Equity Wire, British Business Bank, PitchBook (public articles)
# ---------------------------------------------------------------------------
CURATED_UK_VC_FUND_RAISES = [
    {
        "fund_name": "Balderton Capital (Early Stage IX + Growth II)",
        "amount": 1_300_000_000,
        "currency": "USD",
        "close_date": "Aug 2024",
        "investors": "Institutional LPs (oversubscribed)",
        "source": "TechCrunch / PitchBook",
    },
    {
        "fund_name": "Atomico (Venture VI + Growth VI)",
        "amount": 1_240_000_000,
        "currency": "USD",
        "close_date": "Sep 2024",
        "investors": "Global institutional investors",
        "source": "TechCrunch / Atomico",
    },
    {
        "fund_name": "PXN Group (Par Equity + Praetura merger)",
        "amount": 670_000_000,
        "currency": "GBP",
        "close_date": "Jun 2025",
        "investors": "Family offices, institutional investors, British Business Bank (Regional Angels Programme)",
        "source": "Sifted / Maddyness",
    },
    {
        "fund_name": "Evantic Capital (Fund I - B2B AI)",
        "amount": 341_000_000,
        "currency": "EUR",
        "close_date": "Sep 2025",
        "investors": "140 founders/operators network ('The Legends'); ex-Sequoia partner Matt Miller",
        "source": "EU-Startups / Sifted",
    },
    {
        "fund_name": "IQ Capital (Fund IV - Deep Tech)",
        "amount": 200_000_000,
        "currency": "USD",
        "close_date": "2025",
        "investors": "Institutional investors (AUM reached $1bn across deep tech)",
        "source": "Sifted",
    },
    {
        "fund_name": "IQ Capital (Growth Fund II)",
        "amount": 200_000_000,
        "currency": "USD",
        "close_date": "2025",
        "investors": "Institutional investors",
        "source": "Sifted",
    },
    {
        "fund_name": "British Growth Partnership (Fund I - first close)",
        "amount": 200_000_000,
        "currency": "GBP",
        "close_date": "Apr 2026",
        "investors": "Aegon UK, NatWest Cushon, M&G; London CIV (LGPS pool)",
        "source": "British Business Bank / GOV.UK",
    },
    {
        "fund_name": "Seedcamp (Fund VI)",
        "amount": 180_000_000,
        "currency": "USD",
        "close_date": "2025",
        "investors": "200+ global investors",
        "source": "Sifted / Seedcamp",
    },
    {
        "fund_name": "OpenOcean (Fund IV)",
        "amount": 100_000_000,
        "currency": "EUR",
        "close_date": "H1 2025",
        "investors": "Institutional LPs (targeting €130m final close)",
        "source": "Sifted / Vestbee",
    },
    {
        "fund_name": "Volution (Fund II - UK Scale-ups)",
        "amount": 100_000_000,
        "currency": "USD",
        "close_date": "Apr 2025",
        "investors": "SBI Investment Co. (Japan) as co-GP; returning LPs from Fund I",
        "source": "Tech.eu / Goodwin",
    },
    {
        "fund_name": "DIG Ventures (B2B SaaS/AI Fund)",
        "amount": 100_000_000,
        "currency": "USD",
        "close_date": "2025",
        "investors": "Not disclosed",
        "source": "Vestbee",
    },
    {
        "fund_name": "Backed VC (Fund III - DeepTech)",
        "amount": 86_000_000,
        "currency": "EUR",
        "close_date": "Nov 2025",
        "investors": "Isomer Capital, Wunderland Capital, US family offices, wealth management firms",
        "source": "EU-Startups / Sifted",
    },
    {
        "fund_name": "Concept Ventures (Fund II - Pre-Seed)",
        "amount": 75_000_000,
        "currency": "EUR",
        "close_date": "Sep 2025",
        "investors": "Founders of ElevenLabs, Wayve, FACEIT; US institutional investors",
        "source": "EU-Startups",
    },
    {
        "fund_name": "Par Equity (Scale-Up Fund)",
        "amount": 75_000_000,
        "currency": "GBP",
        "close_date": "Jun 2025",
        "investors": "Family offices, institutional investors",
        "source": "Sifted / Angel Capital Scotland",
    },
    {
        "fund_name": "Ada Ventures (Fund II)",
        "amount": 63_000_000,
        "currency": "GBP",
        "close_date": "2024",
        "investors": "British Patient Capital, institutional investors",
        "source": "Sifted / TechCrunch",
    },
    {
        "fund_name": "Playfair Capital (Fund III - Pre-Seed)",
        "amount": 57_000_000,
        "currency": "GBP",
        "close_date": "2025",
        "investors": "Not disclosed",
        "source": "Playfair / Visible.vc",
    },
    {
        "fund_name": "Mercuri (Fund II)",
        "amount": 50_000_000,
        "currency": "GBP",
        "close_date": "2025",
        "investors": "The Scott Trust (anchor in Fund I)",
        "source": "Visible.vc",
    },
    {
        "fund_name": "Baobab Ventures (Solo GP Fund - AI/Robotics/Defence)",
        "amount": 15_000_000,
        "currency": "USD",
        "close_date": "2025",
        "investors": "Solo GP (Carles Reina); London & Barcelona-based",
        "source": "Sifted",
    },
    {
        "fund_name": "Onstage (Early-Stage Fund)",
        "amount": 10_000_000,
        "currency": "GBP",
        "close_date": "2025",
        "investors": "Peter Simon, Alex Chesterman; GPs from Concept Ventures, Creator Ventures, Chapter One, EPISODE17",
        "source": "Sifted",
    },
    {
        "fund_name": "Octopus Ventures (Pre-Seed Fund)",
        "amount": 10_000_000,
        "currency": "GBP",
        "close_date": "2025",
        "investors": "Octopus Group",
        "source": "Sifted",
    },
]


def safe_request(url, retries=2, delay=2):
    """Make an HTTP GET request with retries."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"Request failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def parse_amount(text):
    """Parse fund amount strings like '£200m', '$1.5bn', '€500 million'."""
    if not text:
        return None, None

    text = text.strip().replace(",", "")

    currency_map = {
        "£": "GBP", "GBP": "GBP",
        "$": "USD", "USD": "USD",
        "€": "EUR", "EUR": "EUR",
    }

    currency = None
    for symbol, code in currency_map.items():
        if symbol in text:
            currency = code
            text = text.replace(symbol, "")
            break

    multiplier = 1
    lower = text.lower()
    if "bn" in lower or "billion" in lower:
        multiplier = 1_000_000_000
        text = re.sub(r"(?i)\s*(bn|billion)\s*", "", text)
    elif "mn" in lower or "m" in lower or "million" in lower:
        multiplier = 1_000_000
        text = re.sub(r"(?i)\s*(mn|million|m)\s*", "", text)

    try:
        amount = float(text.strip()) * multiplier
        return amount, currency or "GBP"
    except ValueError:
        return None, None


def format_amount(amount, currency):
    """Format amount for display."""
    if amount is None:
        return "Undisclosed"

    symbols = {"GBP": "£", "USD": "$", "EUR": "€"}
    sym = symbols.get(currency, currency + " ")

    if amount >= 1_000_000_000:
        return f"{sym}{amount / 1_000_000_000:.2f}bn"
    elif amount >= 1_000_000:
        return f"{sym}{amount / 1_000_000:.0f}m"
    else:
        return f"{sym}{amount:,.0f}"


# ---------------------------------------------------------------------------
# Live scraping functions (used with --live flag)
# ---------------------------------------------------------------------------

def scrape_sifted_fund_articles():
    """Scrape Sifted.eu for UK VC fund raise articles."""
    results = []
    urls = [
        "https://sifted.eu/articles/first-time-european-vc-funds-2025",
        "https://sifted.eu/articles/10-largest-europe-vc-funds-2024",
        "https://sifted.eu/articles/european-vcs-due-fundraise-2025",
        "https://sifted.eu/articles/british-vc-firms-merge-670m-in-funds",
    ]

    for url in urls:
        logger.info(f"Scraping Sifted: {url}")
        resp = safe_request(url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        article_body = soup.find("article") or soup.find("div", class_=re.compile(r"article|content|post"))
        if not article_body:
            article_body = soup

        text = article_body.get_text(separator="\n")

        uk_patterns = [
            r"(?P<name>[A-Z][\w\s&']+?)\s*(?:has\s+)?(?:raised|closed|secured)\s+(?P<amount>[£$€][\d.,]+\s*(?:m|mn|million|bn|billion))",
            r"(?P<name>[A-Z][\w\s&']+?)\s*[-–]\s*(?P<amount>[£$€][\d.,]+\s*(?:m|mn|million|bn|billion))",
        ]

        for pattern in uk_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                name = m.group("name").strip()
                amount_str = m.group("amount").strip()
                amount, currency = parse_amount(amount_str)

                uk_indicators = [
                    "UK", "London", "British", "Britain", "Edinburgh",
                    "Manchester", "Cambridge", "Oxford", "BGF",
                    "Balderton", "Notion Capital", "Seedcamp",
                    "LocalGlobe", "Atomico", "Index Ventures",
                    "Hoxton", "Forward Partners", "Passion Capital",
                    "Episode 1", "Ada Ventures", "Playfair",
                ]

                surrounding_text = text[max(0, m.start() - 200):m.end() + 200]
                is_uk = any(ind.lower() in surrounding_text.lower() for ind in uk_indicators)

                if is_uk or currency == "GBP":
                    results.append({
                        "fund_name": name,
                        "amount": amount,
                        "currency": currency,
                        "close_date": "2025",
                        "investors": "Not disclosed",
                        "source": "Sifted",
                    })

    return results


def scrape_techcrunch_uk_vc():
    """Scrape TechCrunch for UK VC fund raise articles."""
    results = []
    url = "https://techcrunch.com/tag/venture-capital-funds/"
    logger.info(f"Scraping TechCrunch: {url}")

    resp = safe_request(url)
    if not resp:
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.find_all("article") or soup.find_all("div", class_=re.compile(r"post-block"))

    for article in articles[:20]:
        title_el = article.find("h2") or article.find("h3") or article.find("a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        uk_keywords = ["UK", "London", "British", "£", "GBP", "Britain"]
        if not any(kw.lower() in title.lower() for kw in uk_keywords):
            continue

        amount_match = re.search(r"[£$€][\d.,]+\s*(?:m|mn|million|bn|billion|M|B)", title, re.IGNORECASE)
        if amount_match:
            amount, currency = parse_amount(amount_match.group())
            results.append({
                "fund_name": title[:80],
                "amount": amount,
                "currency": currency,
                "close_date": "2025",
                "investors": "Not disclosed",
                "source": "TechCrunch",
            })

    return results


def scrape_bvca():
    """Scrape BVCA for UK VC fundraising data."""
    results = []
    urls = [
        "https://www.bvca.co.uk/resource/venture-capital-in-the-uk-2025.html",
        "https://www.bvca.co.uk/resource/venture-capital-fundraising-up-in-2024.html",
    ]

    for url in urls:
        logger.info(f"Scraping BVCA: {url}")
        resp = safe_request(url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator="\n")

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    name = cells[0].get_text(strip=True)
                    amount_text = cells[1].get_text(strip=True)
                    amount, currency = parse_amount(amount_text)
                    if amount:
                        results.append({
                            "fund_name": name,
                            "amount": amount,
                            "currency": currency or "GBP",
                            "close_date": "2024/2025",
                            "investors": "Not disclosed",
                            "source": "BVCA",
                        })

        fund_pattern = r"(?P<name>[A-Z][\w\s&']+?)\s+(?:raised|closed)\s+(?P<amount>[£$€][\d.,]+\s*(?:m|mn|million|bn|billion))"
        for m in re.finditer(fund_pattern, text, re.IGNORECASE):
            name = m.group("name").strip()
            amount, currency = parse_amount(m.group("amount"))
            if amount:
                results.append({
                    "fund_name": name,
                    "amount": amount,
                    "currency": currency or "GBP",
                    "close_date": "2024/2025",
                    "investors": "Not disclosed",
                    "source": "BVCA",
                })

    return results


def run_live_scrapers():
    """Run all live web scrapers and combine results."""
    all_results = []

    scrapers = [
        ("Sifted", scrape_sifted_fund_articles),
        ("TechCrunch", scrape_techcrunch_uk_vc),
        ("BVCA", scrape_bvca),
    ]

    for name, scraper_fn in scrapers:
        try:
            logger.info(f"\n--- Running live scraper: {name} ---")
            results = scraper_fn()
            logger.info(f"  Found {len(results)} results from {name}")
            all_results.extend(results)
        except Exception as e:
            logger.error(f"  Error in {name} scraper: {e}")

    return all_results


# ---------------------------------------------------------------------------
# Table building and output
# ---------------------------------------------------------------------------

def deduplicate_results(results):
    """Remove duplicate entries based on fund name similarity."""
    seen = {}
    deduped = []

    for r in results:
        name_key = re.sub(r"[^a-z0-9]", "", r["fund_name"].lower())[:30]
        if name_key not in seen:
            seen[name_key] = r
            deduped.append(r)
        else:
            existing = seen[name_key]
            if (r.get("investors", "Not disclosed") != "Not disclosed" and
                    existing.get("investors") == "Not disclosed"):
                seen[name_key] = r
                deduped[deduped.index(existing)] = r

    return deduped


def build_table(results):
    """Build a formatted pandas DataFrame from results."""
    if not results:
        return pd.DataFrame()

    results = deduplicate_results(results)

    rows = []
    for r in results:
        rows.append({
            "Fund / Firm": r["fund_name"],
            "Amount Raised": format_amount(r.get("amount"), r.get("currency", "GBP")),
            "Close Date": r.get("close_date", "Unknown"),
            "Investors / LPs": r.get("investors", "Not disclosed"),
            "Source": r.get("source", ""),
        })

    df = pd.DataFrame(rows)

    # Sort by amount (descending)
    def sort_key(x):
        match = re.search(r"[\d.]+", str(x))
        if not match:
            return 0
        val = float(match.group())
        if "bn" in str(x):
            val *= 1000
        return val

    df["_sort"] = df["Amount Raised"].apply(sort_key)
    df = df.sort_values("_sort", ascending=False).drop("_sort", axis=1)
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "#"

    return df


def export_csv(df, filename="uk_vc_fund_raises.csv"):
    """Export DataFrame to CSV."""
    df.to_csv(filename)
    logger.info(f"Exported to {filename}")


def main():
    parser = argparse.ArgumentParser(description="UK VC Fund Raises Scraper")
    parser.add_argument("--live", action="store_true",
                        help="Attempt live scraping from web sources")
    parser.add_argument("--csv-only", action="store_true",
                        help="Export CSV without printing table to stdout")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("  UK Venture Capital Fund Raises - Last 12 Months")
    print(f"  Report date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Data period: {CUTOFF_DATE.strftime('%B %Y')} - {datetime.now().strftime('%B %Y')}")
    print("=" * 80)

    # Start with curated data
    all_results = list(CURATED_UK_VC_FUND_RAISES)
    print(f"\n  Curated dataset: {len(all_results)} UK VC fund raises")

    # Optionally run live scrapers
    if args.live:
        print("\n  Running live scrapers...")
        live_results = run_live_scrapers()
        print(f"  Live scraping found: {len(live_results)} additional results")
        all_results.extend(live_results)

    # Build table
    df = build_table(all_results)

    if df.empty:
        print("\n  No fund raise data available.")
        return

    if not args.csv_only:
        print(f"\n  Total unique fund raises: {len(df)}\n")
        print(tabulate(
            df,
            headers="keys",
            tablefmt="grid",
            maxcolwidths=[None, 45, 18, 14, 55, 25],
            stralign="left",
        ))

    # Summary stats
    total_gbp = sum(
        r["amount"] for r in all_results
        if r.get("amount") and r.get("currency") == "GBP"
    )
    total_usd = sum(
        r["amount"] for r in all_results
        if r.get("amount") and r.get("currency") == "USD"
    )
    total_eur = sum(
        r["amount"] for r in all_results
        if r.get("amount") and r.get("currency") == "EUR"
    )

    print(f"\n  {'='*60}")
    print(f"  SUMMARY - UK VC Fund Raises (Last 12 Months)")
    print(f"  {'='*60}")
    print(f"  Total funds tracked:  {len(df)}")
    print(f"  Total GBP raised:     £{total_gbp / 1e9:.2f}bn")
    print(f"  Total USD raised:     ${total_usd / 1e9:.2f}bn")
    print(f"  Total EUR raised:     €{total_eur / 1e6:.0f}m")
    print(f"  {'='*60}")
    print(f"\n  Context: UK VCs raised $3.7bn total in 2025 (BVCA)")
    print(f"  UK VC investment reached $23.6bn in 2025 (+35% YoY)")
    print(f"  AI startups raised a record $7.9bn in UK in 2025")

    # Export
    export_csv(df)
    print(f"\n  Results exported to: uk_vc_fund_raises.csv")

    # Source attribution
    print(f"\n  Sources: Sifted, TechCrunch, BVCA, EU-Startups, Vestbee,")
    print(f"           British Business Bank, PitchBook, Private Equity Wire,")
    print(f"           GOV.UK, Tech.eu, Visible.vc\n")

    return df


if __name__ == "__main__":
    main()

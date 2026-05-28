#!/usr/bin/env python3
"""
LinkedIn Job Search Script
Searches LinkedIn's public job listings for roles matching
biotech/pharma strategic accounts and site enablement criteria.
Filters to jobs posted in the last 24 hours (daily deposits).
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Search configuration
# ---------------------------------------------------------------------------

# Track 1: Strategy (GTM, market development, platform strategy)
GTM_ROLE_KEYWORDS = [
    "GTM strategy",
    "go-to-market strategy",
    "market development",
    "platform strategy",
    "commercial strategy",
    "launch strategy",
    "market access strategy",
]

# Track 2: Business Development (BD, partnerships, alliances only)
BD_ROLE_KEYWORDS = [
    "business development",
    "strategic alliances",
    "partnerships director",
    "VP partnerships",
    "alliance management",
    "corporate development",
    "BD director",
]

# Track 3: Commercial Operations (RevOps, CRM, sales ops only)
COMOPS_ROLE_KEYWORDS = [
    "commercial operations",
    "revenue operations",
    "sales operations",
    "CRM director",
    "RevOps",
    "sales enablement director",
    "forecast operations",
]

INDUSTRY_KEYWORDS = [
    "biotech",
    "biopharma",
    "pharma",
    "life sciences",
    "cell and gene",
    "genomics",
    "CRO",
    "CDMO",
]

ROLE_KEYWORDS = GTM_ROLE_KEYWORDS + BD_ROLE_KEYWORDS + COMOPS_ROLE_KEYWORDS

# LinkedIn time filter values (f_TPR parameter)
TIME_FILTERS = {
    "24h": "r86400",
    "week": "r604800",
    "month": "r2592000",
}

# LinkedIn experience level codes (f_E parameter)
EXPERIENCE_LEVELS = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def build_query(role_kw: List[str], industry_kw: List[str]) -> str:
    """Build a Boolean search query string.

    Produces:
        ("kw1" OR "kw2" ...) AND ("kw3" OR "kw4" ...)
    """
    def _or_group(terms: List[str]) -> str:
        quoted = [f'"{t}"' for t in terms]
        return "(" + " OR ".join(quoted) + ")"

    return f"{_or_group(role_kw)} AND {_or_group(industry_kw)}"


def build_url(query: str, time_filter: str = "24h",
              location: str = "United States",
              start: int = 0) -> str:
    """Build a LinkedIn public job search URL."""
    params = {
        "keywords": query,
        "location": location,
        "f_TPR": TIME_FILTERS.get(time_filter, TIME_FILTERS["24h"]),
        "start": str(start),
    }
    base = "https://www.linkedin.com/jobs/search/?"
    return base + urllib.parse.urlencode(params)


def fetch_page(url: str, retries: int = 3, delay: float = 2.0) -> Optional[str]:
    """Fetch a page with retries and exponential backoff."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = delay * (2 ** attempt)
                print(f"  Rate-limited. Waiting {wait:.0f}s ...", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            wait = delay * (2 ** attempt)
            print(f"  Request error ({exc}). Retrying in {wait:.0f}s ...",
                  file=sys.stderr)
            time.sleep(wait)
    return None


def parse_jobs(html: str) -> List[Dict]:
    """Extract job cards from LinkedIn public search results HTML."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # LinkedIn public pages use <ul class="jobs-search__results-list">
    cards = soup.select("li div.base-card")
    if not cards:
        # Fallback: try alternate selectors
        cards = soup.select("li div.base-search-card")
    if not cards:
        cards = soup.select("ul.jobs-search__results-list > li")

    for card in cards:
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle a")
        location_el = card.select_one("span.job-search-card__location")
        link_el = card.select_one("a.base-card__full-link")
        date_el = card.select_one("time")

        title = title_el.get_text(strip=True) if title_el else "N/A"
        company = company_el.get_text(strip=True) if company_el else "N/A"
        location = location_el.get_text(strip=True) if location_el else "N/A"
        link = link_el["href"].split("?")[0] if link_el and link_el.get("href") else "N/A"
        posted = date_el.get_text(strip=True) if date_el else "N/A"

        if title == "N/A" and company == "N/A":
            continue

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "posted": posted,
            "url": link,
        })

    return jobs


def search_linkedin(query: str, time_filter: str = "24h",
                    location: str = "United States",
                    max_pages: int = 5) -> List[Dict]:
    """Run a paginated LinkedIn public job search."""
    all_jobs = []
    per_page = 25

    for page in range(max_pages):
        start = page * per_page
        url = build_url(query, time_filter=time_filter,
                        location=location, start=start)
        print(f"Fetching page {page + 1} (start={start}) ...", file=sys.stderr)

        html = fetch_page(url)
        if html is None:
            print("  Failed to fetch page. Stopping.", file=sys.stderr)
            break

        jobs = parse_jobs(html)
        if not jobs:
            print("  No more results found.", file=sys.stderr)
            break

        all_jobs.extend(jobs)
        print(f"  Found {len(jobs)} jobs on this page.", file=sys.stderr)

        # Be polite between requests
        time.sleep(1.5)

    return all_jobs


def deduplicate(jobs: List[Dict]) -> List[Dict]:
    """Remove duplicate listings by URL."""
    seen = set()  # type: Set[str]
    unique = []  # type: List[Dict]
    for job in jobs:
        key = job["url"]
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def output_results(jobs: List[Dict], fmt: str = "table",
                   outfile: Optional[str] = None) -> None:
    """Print or save results in the chosen format."""
    if not jobs:
        print("\nNo jobs found matching your criteria.")
        return

    if fmt == "json":
        payload = json.dumps(jobs, indent=2)
        if outfile:
            with open(outfile, "w") as f:
                f.write(payload)
            print(f"\nSaved {len(jobs)} jobs to {outfile}")
        else:
            print(payload)

    elif fmt == "csv":
        fieldnames = ["title", "company", "location", "posted", "url"]
        dest = outfile or "linkedin_jobs.csv"
        with open(dest, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(jobs)
        print(f"\nSaved {len(jobs)} jobs to {dest}")

    else:  # table (default)
        header = f"{'#':<4} {'Title':<45} {'Company':<30} {'Location':<25} {'Posted':<12}"
        sep = "-" * len(header)
        print(f"\n{header}")
        print(sep)
        for i, j in enumerate(jobs, 1):
            title = j["title"][:43]
            company = j["company"][:28]
            loc = j["location"][:23]
            posted = j["posted"][:10]
            print(f"{i:<4} {title:<45} {company:<30} {loc:<25} {posted:<12}")
        print(sep)
        print(f"Total: {len(jobs)} jobs found")

        # Always print URLs below the table for easy clicking
        print("\nJob Links:")
        for i, j in enumerate(jobs, 1):
            print(f"  {i}. {j['url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search LinkedIn public job listings (daily deposits)."
    )
    parser.add_argument(
        "--time", choices=["24h", "week", "month"], default="24h",
        help="Time filter for job postings (default: 24h = daily deposits)",
    )
    parser.add_argument(
        "--location", default="United States",
        help="Job location filter (default: 'United States')",
    )
    parser.add_argument(
        "--pages", type=int, default=5,
        help="Max pages to fetch, 25 results per page (default: 5)",
    )
    parser.add_argument(
        "--format", choices=["table", "json", "csv"], default="table",
        dest="fmt", help="Output format (default: table)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path (for json/csv formats)",
    )
    parser.add_argument(
        "--extra-roles", nargs="*", default=[],
        help="Additional role keywords to include in the search",
    )
    parser.add_argument(
        "--extra-industries", nargs="*", default=[],
        help="Additional industry keywords to include in the search",
    )
    args = parser.parse_args()

    role_kw = args.extra_roles if args.extra_roles else ROLE_KEYWORDS
    industry_kw = args.extra_industries if args.extra_industries else INDUSTRY_KEYWORDS

    query = build_query(role_kw, industry_kw)

    print("=" * 70, file=sys.stderr)
    print("LinkedIn Job Search — Daily Deposits", file=sys.stderr)
    print(f"Time filter : {args.time}", file=sys.stderr)
    print(f"Location    : {args.location}", file=sys.stderr)
    print(f"Query       : {query}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    jobs = search_linkedin(
        query,
        time_filter=args.time,
        location=args.location,
        max_pages=args.pages,
    )
    jobs = deduplicate(jobs)

    output_results(jobs, fmt=args.fmt, outfile=args.output)


if __name__ == "__main__":
    main()

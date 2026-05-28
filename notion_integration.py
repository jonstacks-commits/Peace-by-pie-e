#!/usr/bin/env python3
"""
Notion Integration — Push LinkedIn job search results to a Notion database.
Creates one page per job listing, matching the Opportunity board template.

Setup:
  1. Create a Notion integration at https://www.notion.so/my-integrations
  2. Share your Opportunity database with the integration
  3. Create ~/.linkedin_notion_config.json with your credentials (see setup_config())
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

CONFIG_PATH = os.path.expanduser("~/.linkedin_notion_config.json")

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("ERROR: Config file not found at %s" % CONFIG_PATH, file=sys.stderr)
        print("Run: python3 notion_integration.py --setup", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    missing = [k for k in ("notion_api_key", "database_id") if not cfg.get(k)]
    if missing:
        print("ERROR: Missing config keys: %s" % ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    return cfg


def setup_config():
    print("=== Notion Integration Setup ===")
    print()
    print("You'll need:")
    print("  1. A Notion Internal Integration Secret (starts with ntn_)")
    print("     Create one at: https://www.notion.so/my-integrations")
    print("  2. Your Notion database ID (from the board URL)")
    print()
    api_key = input("Paste your Notion API key: ").strip()
    db_id = input("Paste your database ID: ").strip()

    db_id = db_id.replace("-", "")
    if len(db_id) > 32:
        db_id = db_id[:32]

    cfg = {
        "notion_api_key": api_key,
        "database_id": db_id,
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_PATH, 0o600)

    print()
    print("Config saved to %s" % CONFIG_PATH)
    print("Now share your Notion database with the integration and you're set.")


def notion_headers(api_key):
    return {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def query_existing_urls(api_key, database_id):
    """Query existing pages to avoid creating duplicates."""
    headers = notion_headers(api_key)
    existing = set()
    start_cursor = None

    while True:
        body = {"page_size": 100}  # type: Dict[str, Any]
        if start_cursor:
            body["start_cursor"] = start_cursor

        resp = requests.post(
            "%s/databases/%s/query" % (NOTION_API, database_id),
            headers=headers,
            json=body,
            timeout=30,
        )
        if resp.status_code != 200:
            print("  Warning: could not query existing pages (%s)" % resp.status_code,
                  file=sys.stderr)
            break

        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            url_prop = props.get("Job URL", {})
            if url_prop.get("url"):
                existing.add(url_prop["url"])

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")

    return existing


EXCLUDE_TITLE_KEYWORDS = [
    "product manager",
    "account executive",
    "area sales",
    "national sales manager",
    "sales representative",
    "sales exec",
    "marketing manager",
    "presales",
    "pre-sales",
    "recruiter",
    "talent acquisition",
    "financial advisor",
    "investment",
    "advertising sales",
    "ecommerce",
    "retail",
    "cybersecurity",
    "banking",
    "insurance",
    "real estate",
    "chief of staff",
    "data analyst",
    "software engineer",
]

def is_excluded(job):
    title = job.get("title", "").lower()
    return any(kw.lower() in title for kw in EXCLUDE_TITLE_KEYWORDS)

ALLOWED_LOCATION_KEYWORDS = [
    "remote",
    "hybrid",
    "denver",
    "colorado",
    "united states",
    "anywhere",
    "co,",
    ", co",
]

def is_location_match(job):
    location = job.get("location", "").lower()
    title = job.get("title", "").lower()
    if not location or location == "n/a":
        return True
    if "remote" in title:
        return True
    return any(kw in location for kw in ALLOWED_LOCATION_KEYWORDS)

def build_page_properties(job, database_id, resume_version=None):
    """Build Notion page properties matching the Opportunity board template."""
    title_text = "%s - %s" % (job["company"], job["title"])

    properties = {
        "Company Opportunity Role Title": {
            "title": [
                {
                    "text": {
                        "content": title_text
                    }
                }
            ]
        },
        "Company": {
            "rich_text": [
                {
                    "text": {
                        "content": job.get("company", "N/A")
                    }
                }
            ]
        },
        "Source": {
            "select": {
                "name": "LinkedIn"
            }
        },
        "Job URL": {
            "url": job.get("url", None)
        },
        **({"Resume Version": {"select": {"name": resume_version}}} if resume_version else {}),
        "Status": {
            "select": {
                "name": "Research"
            }
        }
    }

    return properties


def build_page_body():
    """Build the page body with template sections as headings."""
    sections = [
        "Job Description",
        "Top Keywords",
        "Gap Notes",
        "Tailored Resume Version",
        "Cover Letter Draft",
        "Connection Targets",
        "Next Actions / Notes",
    ]

    children = []
    for section in sections:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": section}}]
            }
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": []
            }
        })

    return children


def create_notion_page(api_key, database_id, job, resume_version=None):
    """Create a single Notion page for a job listing."""
    headers = notion_headers(api_key)

    payload = {
        "parent": {"database_id": database_id},
        "properties": build_page_properties(job, database_id, resume_version=resume_version),
        "children": build_page_body(),
    }

    resp = requests.post(
        "%s/pages" % NOTION_API,
        headers=headers,
        json=payload,
        timeout=30,
    )

    return resp.status_code, resp.json()


def push_jobs_to_notion(jobs, config=None, resume_version=None):
    """Push a list of job dicts to Notion. Returns (created, skipped, failed) counts."""
    if config is None:
        config = load_config()

    api_key = config["notion_api_key"]
    database_id = config["database_id"]

    print("Checking for existing entries...", file=sys.stderr)
    existing_urls = query_existing_urls(api_key, database_id)
    print("  Found %d existing entries in Notion" % len(existing_urls), file=sys.stderr)

    created = 0
    skipped = 0
    failed = 0

    for i, job in enumerate(jobs):
        url = job.get("url", "")
        title = "%s - %s" % (job.get("company", ""), job.get("title", ""))

        if url in existing_urls:
            print("  [SKIP] %s (already exists)" % title, file=sys.stderr)
            skipped += 1
            continue

        if is_excluded(job):
            print("  [EXCL] %s (title excluded)" % title, file=sys.stderr)
            failed += 1
            continue

        if not is_location_match(job):
            print("  [LOC]  %s (%s)" % (title, job.get("location", "")), file=sys.stderr)
            failed += 1
            continue

        status_code, resp_data = create_notion_page(api_key, database_id, job, resume_version=resume_version)

        if status_code == 200:
            print("  [OK]   %s" % title, file=sys.stderr)
            created += 1
            existing_urls.add(url)
        elif status_code == 429:
            retry_after = float(resp_data.get("retry_after", 1))
            print("  [WAIT] Rate limited, waiting %.0fs..." % retry_after, file=sys.stderr)
            time.sleep(retry_after)
            status_code, resp_data = create_notion_page(api_key, database_id, job, resume_version=resume_version)
            if status_code == 200:
                created += 1
                existing_urls.add(url)
            else:
                print("  [FAIL] %s — %s" % (title, resp_data.get("message", "")),
                      file=sys.stderr)
                failed += 1
        else:
            msg = resp_data.get("message", "Unknown error")
            print("  [FAIL] %s — %s" % (title, msg), file=sys.stderr)
            failed += 1

        # Respect Notion rate limits (3 requests/sec)
        time.sleep(0.4)

    return created, skipped, failed


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Push LinkedIn job results to Notion board."
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="Interactive setup wizard to configure Notion API credentials",
    )
    parser.add_argument(
        "--csv", default=None,
        help="Path to a CSV file from linkedin_job_search.py to import",
    )
    parser.add_argument(
        "--resume-version", default=None,
        help="Resume track label (e.g. GTM Strategy, Business Development, Commercial Operations)",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test the Notion connection without creating any pages",
    )
    args = parser.parse_args()

    if args.setup:
        setup_config()
        return

    config = load_config()

    if args.test:
        headers = notion_headers(config["notion_api_key"])
        resp = requests.get(
            "%s/databases/%s" % (NOTION_API, config["database_id"]),
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            db_info = resp.json()
            title_parts = db_info.get("title", [])
            db_title = title_parts[0]["plain_text"] if title_parts else "(untitled)"
            print("Connection successful!")
            print("  Database: %s" % db_title)
            props = list(db_info.get("properties", {}).keys())
            print("  Properties: %s" % ", ".join(props))
        else:
            print("Connection failed: %s" % resp.json().get("message", resp.status_code))
        return

    if args.csv:
        import csv as csv_mod
        with open(args.csv) as f:
            reader = csv_mod.DictReader(f)
            jobs = list(reader)
        print("Loaded %d jobs from %s" % (len(jobs), args.csv), file=sys.stderr)
    else:
        print("Reading jobs from stdin (JSON)...", file=sys.stderr)
        jobs = json.load(sys.stdin)

    created, skipped, failed = push_jobs_to_notion(jobs, config, resume_version=args.resume_version)

    print(file=sys.stderr)
    print("=== Notion Sync Complete ===", file=sys.stderr)
    print("  Created: %d" % created, file=sys.stderr)
    print("  Skipped: %d (already existed)" % skipped, file=sys.stderr)
    print("  Failed:  %d" % failed, file=sys.stderr)


if __name__ == "__main__":
    main()

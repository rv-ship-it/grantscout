"""
Fetch funding opportunity announcements from the NIH Guide for Grants and Contracts.

Strategy:
  1. Use the NIH Guide RSS feed for active funding opportunities (FOAs).
     Feed URL: https://grants.nih.gov/funding/searchguide/rss/actnotices.xml
  2. Also try the NIH Reporter API for open opportunities if the RSS feed fails.
  3. Save raw payloads to data/raw/ for auditability.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from grant_scout.normalize import Opportunity, normalize_nih
from grant_scout.utils import DATA_RAW_DIR, get_logger, now_utc

log = get_logger(__name__)

# NIH Guide RSS feeds for active notices
NIH_RSS_URLS = [
    # Active RFAs (Requests for Applications)
    "https://grants.nih.gov/funding/searchguide/rss/actnotices_rfa.xml",
    # Active PAs (Program Announcements)
    "https://grants.nih.gov/funding/searchguide/rss/actnotices_pa.xml",
    # Active NOSIs (Notices of Special Interest)
    "https://grants.nih.gov/funding/searchguide/rss/actnotices_nosi.xml",
]

# Fallback: NIH RePORTER API for open funding opportunities
REPORTER_API_URL = "https://api.reporter.nih.gov/v2/projects/search"

TIMEOUT = 30  # seconds


def fetch_nih_rss() -> list[dict]:
    """Fetch opportunities from NIH Guide RSS feeds."""
    all_items: list[dict] = []

    for url in NIH_RSS_URLS:
        log.info(f"Fetching NIH Guide RSS: {url}")
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Failed to fetch {url}: {e}")
            continue

        # Save raw XML
        ts = now_utc().strftime("%Y%m%d_%H%M%S")
        feed_name = url.split("/")[-1].replace(".xml", "")
        raw_path = DATA_RAW_DIR / f"nih_guide_{feed_name}_{ts}.xml"
        raw_path.write_text(resp.text, encoding="utf-8")
        log.info(f"Saved raw feed to {raw_path}")

        items = _parse_rss_xml(resp.text)
        all_items.extend(items)

    log.info(f"NIH Guide RSS: found {len(all_items)} items total")
    return all_items


def _parse_rss_xml(xml_text: str) -> list[dict]:
    """Parse RSS XML into a list of raw dicts."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning(f"XML parse error: {e}")
        return items

    # Handle RSS 2.0 (<rss><channel><item>) and Atom (<feed><entry>)
    # NIH Guide typically uses RSS 2.0
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Try RSS 2.0 first
    for item in root.iter("item"):
        raw = {}
        for child in item:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            raw[tag.lower()] = (child.text or "").strip()
        # Map common RSS fields
        raw.setdefault("title", raw.get("title", ""))
        raw.setdefault("link", raw.get("link", ""))
        raw.setdefault("description", raw.get("description", ""))
        raw.setdefault("summary", raw.get("description", ""))
        # Try to extract opportunity number from title or link
        if not raw.get("docnum"):
            title = raw.get("title", "")
            for prefix in ("RFA-", "PA-", "PAR-", "NOT-", "OTA-"):
                if prefix in title:
                    idx = title.index(prefix)
                    raw["docnum"] = title[idx:].split()[0].rstrip(":")
                    break
        items.append(raw)

    # If no RSS items, try Atom
    if not items:
        for entry in root.findall("atom:entry", ns):
            raw = {}
            for child in entry:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "link":
                    raw["link"] = child.get("href", child.text or "")
                else:
                    raw[tag.lower()] = (child.text or "").strip()
            raw.setdefault("summary", raw.get("content", raw.get("description", "")))
            items.append(raw)

    return items


def fetch_nih_opportunities() -> list[Opportunity]:
    """Main entry point: fetch and normalize NIH Guide opportunities."""
    raw_items = fetch_nih_rss()

    # Normalize each item
    opportunities = []
    for raw in raw_items:
        try:
            opp = normalize_nih(raw)
            if opp.title:  # skip empty entries
                opportunities.append(opp)
        except Exception as e:
            log.warning(f"Failed to normalize NIH item: {e}")

    log.info(f"NIH Guide: {len(opportunities)} normalized opportunities")
    return opportunities

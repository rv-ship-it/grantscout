"""
Fetch funding opportunities from the Grants.gov API.

Strategy:
  Use the Grants.gov REST API to search for posted/forecasted opportunities
  from NIH / HHS filtered by medical and biotech keywords.

  API docs: https://www.grants.gov/web/grants/s2s/grantor/schemas/grants-funding-synopsis.html
  Search endpoint: https://api.grants.gov/v1/api/search2
"""

from __future__ import annotations

import json
from datetime import datetime

import requests

from grant_scout.normalize import Opportunity, normalize_grants_gov
from grant_scout.utils import DATA_RAW_DIR, get_logger, now_utc

log = get_logger(__name__)

# Grants.gov search API (public, no key needed)
SEARCH_URL = "https://api.grants.gov/v1/api/search2"
DETAIL_URL = "https://api.grants.gov/v1/api/fetchOppDetails"

TIMEOUT = 45  # seconds

# Keywords to search for – we run one query per keyword group to stay
# within API limits and get broad coverage.
KEYWORD_GROUPS = [
    "ulcerative colitis IBD",
    "gut microbiome intestinal",
    "mucin glycobiology goblet cell",
    "mucosal immunology mucosal health",
    "vaginal microbiome bacterial vaginosis women's health",
    "biomanufacturing live biotherapeutic",
    "Crohn's disease inflammatory bowel",
    "intestinal barrier epithelial",
]

# Agencies of interest
AGENCIES = ["NIH", "HHS", "NSF", "DOD", "ARPA-H"]

# Max results per query (Grants.gov caps at 1000)
PAGE_SIZE = 100


def fetch_grants_gov_search(keyword: str) -> list[dict]:
    """Run a single keyword search against the Grants.gov API."""
    params = {
        "keyword": keyword,
        "oppStatuses": "posted|forecasted",
        "sortBy": "postedDate|desc",
        "rows": PAGE_SIZE,
        "startRecordNum": 0,
    }

    log.info(f"Grants.gov search: '{keyword}'")
    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.warning(f"Grants.gov API error for '{keyword}': {e}")
        return []
    except json.JSONDecodeError as e:
        log.warning(f"Grants.gov JSON decode error: {e}")
        return []

    # Save raw response
    ts = now_utc().strftime("%Y%m%d_%H%M%S")
    safe_kw = keyword.replace(" ", "_")[:30]
    raw_path = DATA_RAW_DIR / f"grants_gov_{safe_kw}_{ts}.json"
    raw_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    # Extract opportunity list – API nests them under various keys
    opps = (
        data.get("oppHits", [])
        or data.get("opportunities", [])
        or data.get("searchResult", {}).get("oppHits", [])
        or data.get("data", [])
        or []
    )

    if isinstance(opps, dict):
        opps = opps.get("oppHits", [])

    log.info(f"  -> {len(opps)} results")
    return opps


def fetch_grants_gov_opportunities() -> list[Opportunity]:
    """Main entry point: search Grants.gov and normalize results."""
    seen_ids: set[str] = set()
    opportunities: list[Opportunity] = []

    for keyword in KEYWORD_GROUPS:
        raw_items = fetch_grants_gov_search(keyword)
        for raw in raw_items:
            # Dedupe within this source by opportunity number or id
            opp_key = raw.get("opportunityNumber", raw.get("id", ""))
            if opp_key and opp_key in seen_ids:
                continue
            seen_ids.add(opp_key)

            try:
                opp = normalize_grants_gov(raw)
                if opp.title:
                    opportunities.append(opp)
            except Exception as e:
                log.warning(f"Failed to normalize Grants.gov item: {e}")

    log.info(f"Grants.gov: {len(opportunities)} normalized opportunities")
    return opportunities

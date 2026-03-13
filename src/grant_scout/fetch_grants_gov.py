"""
Fetch funding opportunities from the Grants.gov API.

Strategy:
  Use the Grants.gov REST API to search for posted/forecasted opportunities
  across all major US agencies that fund biomedical and health research.

  API docs: https://www.grants.gov/web/grants/s2s/grantor/schemas/grants-funding-synopsis.html
  Search endpoint: https://api.grants.gov/v1/api/search2
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import requests

from grant_scout.normalize import Opportunity, normalize_grants_gov
from grant_scout.utils import DATA_RAW_DIR, get_logger, now_utc

log = get_logger(__name__)

# Grants.gov search API (public, no key needed)
SEARCH_URL = "https://api.grants.gov/v1/api/search2"
DETAIL_URL = "https://api.grants.gov/v1/api/fetchOppDetails"

TIMEOUT = 45  # seconds
REQUEST_DELAY = 1  # seconds between API calls to avoid rate limiting

# Keywords to search for – we run one query per keyword group to stay
# within API limits and get broad coverage.
KEYWORD_GROUPS = [
    # --- June Bio core focus (high relevance) ---
    "ulcerative colitis IBD",
    "gut microbiome intestinal",
    "mucin glycobiology goblet cell",
    "mucosal immunology mucosal health",
    "vaginal microbiome bacterial vaginosis women's health",
    "biomanufacturing live biotherapeutic",
    "Crohn's disease inflammatory bowel",
    "intestinal barrier epithelial",
    # --- Broad biomedical & health coverage ---
    "cancer oncology tumor",
    "cardiovascular heart disease stroke",
    "neuroscience brain neurological disorders",
    "infectious disease pathogen antimicrobial resistance",
    "diabetes obesity metabolic syndrome",
    "aging geriatrics Alzheimer dementia",
    "genomics precision medicine personalized",
    "artificial intelligence machine learning health",
    "digital health telehealth mHealth",
    "medical device biomedical engineering",
    "mental health behavioral health psychiatry",
    "rare disease orphan drug genetic disorder",
    "immunology autoimmune vaccine immunotherapy",
    "health equity health disparities underserved",
    "clinical trial translational research drug development",
    "biomarker diagnostics point-of-care",
    "regenerative medicine stem cell tissue engineering",
    "public health epidemiology population health",
    "maternal child health pediatric neonatal",
    "substance abuse addiction opioid",
    "respiratory pulmonary lung disease",
    "kidney renal nephrology",
    "environmental health toxicology exposure",
    "nutrition food safety dietary",
    "rehabilitation disability assistive technology",
    "health informatics electronic health records data science",
    "surgical innovation minimally invasive",
    "imaging radiology MRI ultrasound",
    "pain management palliative care",
    "oral health dental craniofacial",
]

# Agencies of interest – all major US funders of biomedical/health research
AGENCIES = [
    "NIH", "HHS", "NSF", "DOD", "ARPA-H",
    "CDC", "FDA", "VA", "HRSA", "SAMHSA",
    "AHRQ", "EPA", "USDA", "ED",
]

# Max results per query (Grants.gov caps at 1000)
PAGE_SIZE = 100
MAX_RESULTS_PER_QUERY = 1000


def fetch_grants_gov_search(keyword: str) -> list[dict]:
    """Run a single keyword search against the Grants.gov API with pagination."""
    all_opps: list[dict] = []
    start = 0

    while start < MAX_RESULTS_PER_QUERY:
        payload = {
            "keyword": keyword,
            "oppStatuses": "posted|forecasted",
            "sortBy": "openDate|desc",
            "rows": PAGE_SIZE,
            "startRecordNum": start,
        }

        log.info(f"Grants.gov search: '{keyword}' (offset {start})")
        try:
            resp = requests.post(SEARCH_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.warning(f"Grants.gov API error for '{keyword}': {e}")
            break
        except json.JSONDecodeError as e:
            log.warning(f"Grants.gov JSON decode error: {e}")
            break

        # Save raw response (only first page to avoid excessive disk usage)
        if start == 0:
            ts = now_utc().strftime("%Y%m%d_%H%M%S")
            safe_kw = keyword.replace(" ", "_")[:30]
            raw_path = DATA_RAW_DIR / f"grants_gov_{safe_kw}_{ts}.json"
            raw_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        # Extract opportunity list – API nests results under data.oppHits
        opps = (
            data.get("data", {}).get("oppHits", [])
            or data.get("oppHits", [])
            or data.get("opportunities", [])
            or data.get("searchResult", {}).get("oppHits", [])
            or []
        )

        if isinstance(opps, dict):
            opps = opps.get("oppHits", [])

        log.info(f"  -> {len(opps)} results (page starting at {start})")
        all_opps.extend(opps)

        # Stop if we got fewer results than requested (no more pages)
        if len(opps) < PAGE_SIZE:
            break

        start += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    return all_opps


def fetch_grants_gov_category_search() -> list[dict]:
    """Search Grants.gov by Health funding category to catch opportunities
    that may not match specific keyword searches."""
    all_opps: list[dict] = []
    start = 0

    while start < MAX_RESULTS_PER_QUERY:
        payload = {
            "fundingCategories": "HL",  # Health
            "oppStatuses": "posted|forecasted",
            "sortBy": "openDate|desc",
            "rows": PAGE_SIZE,
            "startRecordNum": start,
        }

        log.info(f"Grants.gov category search: Health (offset {start})")
        try:
            resp = requests.post(SEARCH_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.warning(f"Grants.gov category search error: {e}")
            break
        except json.JSONDecodeError as e:
            log.warning(f"Grants.gov JSON decode error: {e}")
            break

        if start == 0:
            ts = now_utc().strftime("%Y%m%d_%H%M%S")
            raw_path = DATA_RAW_DIR / f"grants_gov_category_health_{ts}.json"
            raw_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        opps = (
            data.get("oppHits", [])
            or data.get("opportunities", [])
            or data.get("searchResult", {}).get("oppHits", [])
            or data.get("data", [])
            or []
        )

        if isinstance(opps, dict):
            opps = opps.get("oppHits", [])

        log.info(f"  -> {len(opps)} results (category search, offset {start})")
        all_opps.extend(opps)

        if len(opps) < PAGE_SIZE:
            break

        start += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    return all_opps


def fetch_grants_gov_opportunities() -> list[Opportunity]:
    """Main entry point: search Grants.gov and normalize results."""
    seen_ids: set[str] = set()
    opportunities: list[Opportunity] = []

    def _add_raw_items(raw_items: list[dict]) -> None:
        for raw in raw_items:
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

    # 1. Keyword-based searches
    for keyword in KEYWORD_GROUPS:
        raw_items = fetch_grants_gov_search(keyword)
        _add_raw_items(raw_items)
        time.sleep(REQUEST_DELAY)

    # 2. Category-based search (Health) to catch anything keywords missed
    log.info("Running category-based search for Health opportunities...")
    category_items = fetch_grants_gov_category_search()
    _add_raw_items(category_items)

    log.info(f"Grants.gov: {len(opportunities)} normalized opportunities")
    return opportunities

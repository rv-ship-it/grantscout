"""
Fetch funding opportunities from the EU Funding & Tenders Portal.

Strategy:
  Use the SEDIA search API to find open/upcoming calls for proposals
  across Horizon Europe, EU4Health, EIC, ERC, MSCA, and other EU
  programmes relevant to biomedical and health research.

  API: https://api.tech.ec.europa.eu/search-api/prod/rest/search
  Requires POST with apiKey=SEDIA as query param. No authentication needed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import requests

from grant_scout.normalize import Opportunity, normalize_eu
from grant_scout.utils import DATA_RAW_DIR, get_logger, now_utc, parse_date, format_date

log = get_logger(__name__)

# EU SEDIA search API (public, no auth needed)
SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_KEY = "SEDIA"

TIMEOUT = 30  # seconds
REQUEST_DELAY = 1  # seconds between API calls

PAGE_SIZE = 50
MAX_PAGES = 4  # cap at 200 results per keyword to keep runtime reasonable

# Keyword groups for EU health/biomedical search
EU_KEYWORD_GROUPS = [
    "HORIZON-HLTH health biomedical",
    "HORIZON-HLTH disease clinical",
    "EIC Accelerator health biotech",
    "ERC health biomedical",
    "EU4Health",
    "MSCA health biomedical",
    "IHI health innovation",
    "cancer oncology",
    "infectious disease antimicrobial",
    "neuroscience brain disorders",
    "cardiovascular",
    "rare disease orphan",
    "digital health artificial intelligence",
    "medical device diagnostics",
    "precision medicine genomics",
    "vaccine immunology",
    "mental health",
    "biotechnology pharmaceutical",
    "clinical trials",
    "regenerative medicine cell therapy gene therapy",
    "public health epidemiology",
    "aging geriatrics dementia",
    "microbiome gut health",
    "biomanufacturing",
    "health data interoperability",
]


def _extract_metadata_field(metadata: dict, key: str) -> str:
    """Extract a single string value from SEDIA metadata (values are lists)."""
    val = metadata.get(key, [])
    if isinstance(val, list) and val:
        return str(val[0])
    if isinstance(val, str):
        return val
    return ""


def _is_future_deadline(deadline_str: str) -> bool:
    """Check if a deadline string is in the future (or empty = upcoming)."""
    if not deadline_str:
        return True  # no deadline = probably upcoming/forecasted
    dt = parse_date(deadline_str)
    if dt is None:
        return True
    return dt > now_utc()


def _extract_programme(metadata: dict) -> str:
    """Determine the EU programme from metadata fields."""
    call_id = _extract_metadata_field(metadata, "callIdentifier")
    call_title = _extract_metadata_field(metadata, "callTitle")
    combined = f"{call_id} {call_title}".upper()

    if "HORIZON-HLTH" in combined:
        return "Horizon Europe - Health"
    if "HORIZON-CL" in combined:
        return "Horizon Europe"
    if "HORIZON-EIC" in combined or "EIC" in combined:
        return "EIC"
    if "ERC" in combined:
        return "ERC"
    if "MSCA" in combined or "MARIE" in combined:
        return "MSCA"
    if "EU4HEALTH" in combined or "EU4H" in combined:
        return "EU4Health"
    if "IHI" in combined:
        return "IHI"
    if "DIGITAL" in combined:
        return "Digital Europe"
    if "EURATOM" in combined:
        return "Euratom"
    if "HORIZON" in combined:
        return "Horizon Europe"
    return "EU Programme"


def fetch_eu_search(keyword: str) -> list[dict]:
    """Run a single keyword search against the SEDIA API with pagination."""
    all_results: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        url = (
            f"{SEARCH_URL}?apiKey={API_KEY}"
            f"&text={requests.utils.quote(keyword)}"
            f"&pageSize={PAGE_SIZE}"
            f"&pageNumber={page}"
            f"&type=1"  # calls for proposals
            f"&sortBy=deadlineDate&sortOrder=DESC"
        )

        log.info(f"EU search: '{keyword}' (page {page})")
        try:
            resp = requests.post(url, headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.warning(f"EU API error for '{keyword}': {e}")
            break
        except json.JSONDecodeError as e:
            log.warning(f"EU JSON decode error: {e}")
            break

        # Save raw response (first page only)
        if page == 1:
            ts = now_utc().strftime("%Y%m%d_%H%M%S")
            safe_kw = keyword.replace(" ", "_")[:30]
            raw_path = DATA_RAW_DIR / f"eu_portal_{safe_kw}_{ts}.json"
            # Only save non-result metadata + first few results to keep file small
            save_data = {k: v for k, v in data.items() if k != "results"}
            save_data["results_sample"] = data.get("results", [])[:5]
            raw_path.write_text(json.dumps(save_data, indent=2, default=str), encoding="utf-8")

        results = data.get("results", [])
        if not results:
            break

        # Filter: only keep results with future deadlines
        for r in results:
            md = r.get("metadata", {})
            deadline = _extract_metadata_field(md, "deadlineDate")
            if _is_future_deadline(deadline):
                all_results.append(r)

        # If all results on this page have past deadlines (sorted DESC),
        # no point continuing
        if results:
            last_deadline = _extract_metadata_field(
                results[-1].get("metadata", {}), "deadlineDate"
            )
            if last_deadline and not _is_future_deadline(last_deadline):
                break

        if len(results) < PAGE_SIZE:
            break

        time.sleep(REQUEST_DELAY)

    return all_results


def fetch_eu_opportunities() -> list[Opportunity]:
    """Main entry point: search EU F&T Portal and normalize results."""
    seen_ids: set[str] = set()
    opportunities: list[Opportunity] = []

    for keyword in EU_KEYWORD_GROUPS:
        raw_results = fetch_eu_search(keyword)
        for raw in raw_results:
            md = raw.get("metadata", {})
            # Dedupe by ccm2Id or callIdentifier + topic combination
            opp_key = (
                _extract_metadata_field(md, "ccm2Id")
                or _extract_metadata_field(md, "identifier")
                or raw.get("reference", "")
            )
            if opp_key and opp_key in seen_ids:
                continue
            seen_ids.add(opp_key)

            try:
                opp = normalize_eu(raw)
                if opp.title:
                    opportunities.append(opp)
            except Exception as e:
                log.warning(f"Failed to normalize EU item: {e}")

        time.sleep(REQUEST_DELAY)

    log.info(f"EU Portal: {len(opportunities)} normalized opportunities")
    return opportunities

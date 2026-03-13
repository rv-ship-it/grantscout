"""
Normalize raw opportunity data from different sources into a unified schema.

Canonical fields:
  id, source, agency, title, opportunity_number, posted_date, close_date,
  deadline, url, summary, eligibility, cost_share, contact, raw_tags
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime

from grant_scout.utils import parse_date, format_date


@dataclass
class Opportunity:
    """One normalized funding opportunity."""
    id: str = ""
    source: str = ""
    agency: str = ""
    title: str = ""
    opportunity_number: str = ""
    posted_date: str = ""
    close_date: str = ""
    deadline: str = ""          # human-friendly deadline string
    url: str = ""
    summary: str = ""
    eligibility: str = ""
    cost_share: str = ""
    contact: str = ""
    raw_tags: str = ""

    # Scoring fields (populated later)
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    matched_topics: str = ""
    rationale: str = ""
    high_priority: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_nih(raw: dict) -> Opportunity:
    """Normalize a single NIH Guide opportunity from the RSS/XML feed."""
    # NIH Guide RSS items have varying field names; handle gracefully.
    doc_num = raw.get("docnum", raw.get("opportunity_number", ""))
    opp_id = f"nih-{doc_num}" if doc_num else f"nih-{hash(raw.get('title', ''))}"

    close_raw = raw.get("expirationdate", raw.get("close_date", ""))
    posted_raw = raw.get("reldate", raw.get("posted_date", ""))

    close_dt = parse_date(close_raw)
    posted_dt = parse_date(posted_raw)

    return Opportunity(
        id=opp_id,
        source="NIH Guide",
        agency=raw.get("agency", "NIH"),
        title=raw.get("title", "").strip(),
        opportunity_number=doc_num,
        posted_date=format_date(posted_dt),
        close_date=format_date(close_dt),
        deadline=format_date(close_dt),
        url=raw.get("link", raw.get("url", "")),
        summary=raw.get("summary", raw.get("description", "")),
        eligibility=raw.get("eligibility", ""),
        cost_share=raw.get("cost_share", ""),
        contact=raw.get("contact", ""),
        raw_tags=raw.get("raw_tags", ""),
    )


def normalize_eu(raw: dict) -> Opportunity:
    """Normalize a single EU Funding & Tenders Portal opportunity from the SEDIA API."""
    md = raw.get("metadata", {})

    def _field(key: str) -> str:
        val = md.get(key, [])
        if isinstance(val, list) and val:
            return str(val[0])
        return str(val) if val else ""

    call_id = _field("callIdentifier")
    ccm2_id = _field("ccm2Id") or _field("identifier") or raw.get("reference", "")
    opp_id = f"eu-{ccm2_id}" if ccm2_id else f"eu-{hash(raw.get('summary', ''))}"

    deadline_raw = _field("deadlineDate")
    close_dt = parse_date(deadline_raw)

    # Determine programme name
    call_title = _field("callTitle")
    combined = f"{call_id} {call_title}".upper()
    if "HORIZON-HLTH" in combined:
        programme = "Horizon Europe - Health"
    elif "HORIZON-EIC" in combined or "EIC" in combined:
        programme = "EIC"
    elif "ERC" in combined:
        programme = "ERC"
    elif "MSCA" in combined or "MARIE" in combined:
        programme = "MSCA"
    elif "EU4HEALTH" in combined or "EU4H" in combined:
        programme = "EU4Health"
    elif "IHI" in combined:
        programme = "IHI"
    elif "DIGITAL" in combined:
        programme = "Digital Europe"
    elif "HORIZON" in combined:
        programme = "Horizon Europe"
    else:
        programme = "EU Programme"

    # Build URL
    url = raw.get("url", "")
    if not url and call_id:
        url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{call_id}"

    # Extract budget info if available
    budget_raw = _field("budgetOverview")
    budget = ""
    if budget_raw:
        try:
            budget_data = __import__("json").loads(budget_raw)
            # Try to extract total budget
            budget = str(budget_data)[:200]
        except Exception:
            budget = budget_raw[:200]

    title = call_title or raw.get("summary", "")[:200]

    return Opportunity(
        id=opp_id,
        source="EU Portal",
        agency=programme,
        title=title.strip(),
        opportunity_number=call_id,
        posted_date="",
        close_date=format_date(close_dt),
        deadline=format_date(close_dt),
        url=url,
        summary=raw.get("summary", raw.get("content", "")),
        eligibility=_field("eligibility") or "See call details",
        cost_share=budget,
        contact=_field("contact"),
        raw_tags=_field("keywords"),
    )


def normalize_grants_gov(raw: dict) -> Opportunity:
    """Normalize a single Grants.gov opportunity from the API response."""
    opp_num = raw.get("opportunityNumber", raw.get("number", ""))
    opp_id = f"ggov-{raw.get('id', opp_num)}"

    close_raw = raw.get("closeDate", raw.get("close_date", ""))
    posted_raw = raw.get("postedDate", raw.get("posted_date", ""))

    close_dt = parse_date(close_raw)
    posted_dt = parse_date(posted_raw)

    # Build a Grants.gov URL
    ggov_id = raw.get("id", raw.get("opportunityId", ""))
    url = raw.get("url", "")
    if not url and ggov_id:
        url = f"https://www.grants.gov/search-results-detail/{ggov_id}"

    return Opportunity(
        id=opp_id,
        source="Grants.gov",
        agency=raw.get("agencyCode", raw.get("agency", "HHS")),
        title=raw.get("title", raw.get("opportunityTitle", "")).strip(),
        opportunity_number=opp_num,
        posted_date=format_date(posted_dt),
        close_date=format_date(close_dt),
        deadline=format_date(close_dt),
        url=url,
        summary=raw.get("synopsis", raw.get("description", raw.get("summary", ""))),
        eligibility=raw.get("eligibility", raw.get("eligibleApplicants", "")),
        cost_share=raw.get("costSharing", raw.get("cost_share", "")),
        contact=raw.get("agencyContactEmail", raw.get("contact", "")),
        raw_tags=raw.get("categoryOfFundingActivity", raw.get("raw_tags", "")),
    )

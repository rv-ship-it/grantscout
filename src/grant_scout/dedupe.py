"""
Deduplicate opportunities across sources by opportunity_number or fuzzy title match.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from grant_scout.normalize import Opportunity
from grant_scout.utils import get_logger

log = get_logger(__name__)

# Threshold for fuzzy title matching (0.0–1.0)
FUZZY_THRESHOLD = 0.85


def deduplicate(opportunities: list[Opportunity]) -> list[Opportunity]:
    """
    Remove duplicate opportunities.

    Dedup strategy:
      1. Exact match on opportunity_number (if non-empty).
      2. Fuzzy match on title for remaining items.
    When duplicates are found, keep the one with more information (longer summary).
    """
    # Pass 1: exact match on opportunity_number
    by_number: dict[str, Opportunity] = {}
    no_number: list[Opportunity] = []

    for opp in opportunities:
        num = opp.opportunity_number.strip()
        if num:
            if num in by_number:
                existing = by_number[num]
                # Keep the one with more information
                if len(opp.summary) > len(existing.summary):
                    by_number[num] = opp
            else:
                by_number[num] = opp
        else:
            no_number.append(opp)

    deduped = list(by_number.values())
    initial_dupes = len(opportunities) - len(deduped) - len(no_number)

    # Pass 2: fuzzy title match for items without opportunity_number
    # Also check against items that already passed pass 1
    existing_titles = [o.title.lower().strip() for o in deduped]

    for opp in no_number:
        title_lower = opp.title.lower().strip()
        is_dup = False
        for existing in existing_titles:
            ratio = SequenceMatcher(None, title_lower, existing).ratio()
            if ratio >= FUZZY_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            deduped.append(opp)
            existing_titles.append(title_lower)

    fuzzy_dupes = len(no_number) - (len(deduped) - len(by_number))
    total_removed = len(opportunities) - len(deduped)

    log.info(
        f"Dedup: {len(opportunities)} -> {len(deduped)} "
        f"(removed {initial_dupes} by number, {fuzzy_dupes} by fuzzy title)"
    )
    return deduped

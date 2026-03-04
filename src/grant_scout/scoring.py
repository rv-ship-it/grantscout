"""
Score and rank opportunities based on keyword matching and optional
Claude-powered semantic scoring.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import requests

from grant_scout.normalize import Opportunity
from grant_scout.utils import (
    get_env,
    get_logger,
    has_claude_key,
    load_topics_config,
    now_utc,
    parse_date,
)

log = get_logger(__name__)

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------------------
# Keyword scoring
# ---------------------------------------------------------------------------

def keyword_score(opp: Opportunity, config: dict) -> tuple[float, list[str]]:
    """
    Score an opportunity by weighted keyword matching.

    Returns (score 0–100, list of matched topic labels).
    """
    topic_groups = config.get("topic_groups", {})
    text = f"{opp.title} {opp.summary}".lower()

    total_weight = 0.0
    matched_weight = 0.0
    matched_labels: list[str] = []

    for _key, group in topic_groups.items():
        weight = group.get("weight", 0.5)
        total_weight += weight
        keywords = group.get("keywords", [])
        label = group.get("label", _key)

        # Check if any keyword in this group matches
        for kw in keywords:
            if kw.lower() in text:
                matched_weight += weight
                matched_labels.append(label)
                break  # one match per group is enough

    if total_weight == 0:
        return 0.0, []

    # Normalize to 0–100
    score = (matched_weight / total_weight) * 100
    return round(score, 2), matched_labels


# ---------------------------------------------------------------------------
# Semantic scoring (optional – requires CLAUDE_API_KEY)
# ---------------------------------------------------------------------------

SEMANTIC_PROMPT_TEMPLATE = """You are evaluating a funding opportunity for June Bio, a biotech company focused on:
- Gut health: ulcerative colitis, IBD, Crohn's, gut microbiome, intestinal barrier
- Mucins, mucus layer, goblet cells, glycobiology
- Mucosal immunology (GI, respiratory, urogenital)
- Vaginal health: vaginal microbiome, BV, VVC, STIs, women's health
- Biomanufacturing of live biotherapeutics, mucosal delivery, diagnostics

Opportunity title: {title}
Opportunity summary: {summary}

Score this opportunity's relevance to June Bio from 0 to 100.
Also assign 1-3 topic tags from: GI/IBD, Microbiome, Mucins/Glycobiology, Mucosal Immunology, Vaginal Health, Biomanufacturing, Therapeutics, Diagnostics, Delivery.
Give a 2-sentence rationale.

Respond in JSON only:
{{"score": <int>, "tags": [<strings>], "rationale": "<string>"}}
"""


def semantic_score(opp: Opportunity) -> tuple[float, list[str], str]:
    """
    Call Claude API to get a relevance score, tags, and rationale.

    Returns (score 0–100, tags, rationale).
    Falls back to (0, [], "") on error.
    """
    api_key = get_env("CLAUDE_API_KEY")
    if not api_key:
        return 0.0, [], ""

    prompt = SEMANTIC_PROMPT_TEMPLATE.format(
        title=opp.title[:200],
        summary=(opp.summary or "")[:1000],
    )

    try:
        resp = requests.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]

        # Parse JSON from response (Claude may wrap it in markdown)
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return (
                float(result.get("score", 0)),
                result.get("tags", []),
                result.get("rationale", ""),
            )
    except Exception as e:
        log.warning(f"Semantic scoring failed for '{opp.title[:50]}': {e}")

    return 0.0, [], ""


# ---------------------------------------------------------------------------
# Combined scoring
# ---------------------------------------------------------------------------

def score_opportunities(
    opportunities: list[Opportunity],
) -> list[Opportunity]:
    """
    Score all opportunities using keyword matching and optionally semantic scoring.
    Mutates each Opportunity in place and returns the list sorted by final_score desc.
    """
    config = load_topics_config()
    scoring_cfg = config.get("scoring", {})
    kw_weight = scoring_cfg.get("keyword_weight", 0.6)
    sem_weight = scoring_cfg.get("semantic_weight", 0.4)
    hp_threshold = scoring_cfg.get("high_priority_score_threshold", 40)
    hp_days = scoring_cfg.get("high_priority_deadline_days", 60)

    use_semantic = has_claude_key()
    if use_semantic:
        log.info("CLAUDE_API_KEY found – semantic scoring enabled")
    else:
        log.info("No CLAUDE_API_KEY – using keyword scoring only (set key for AI scoring)")

    now = now_utc()
    deadline_cutoff = now + timedelta(days=hp_days)

    for i, opp in enumerate(opportunities):
        # 1) Keyword score
        kw_sc, kw_topics = keyword_score(opp, config)
        opp.keyword_score = kw_sc

        # 2) Semantic score (optional)
        if use_semantic and kw_sc > 0:
            sem_sc, sem_tags, rationale = semantic_score(opp)
            opp.semantic_score = sem_sc
            opp.rationale = rationale
            # Merge tags
            all_topics = list(dict.fromkeys(kw_topics + sem_tags))
        else:
            opp.semantic_score = 0.0
            all_topics = kw_topics

        opp.matched_topics = ", ".join(all_topics)

        # 3) Final score
        if use_semantic:
            opp.final_score = round(kw_weight * kw_sc + sem_weight * opp.semantic_score, 2)
        else:
            # Keyword-only mode: score is just the keyword score
            opp.final_score = kw_sc

        # 4) High priority flag
        deadline_dt = parse_date(opp.close_date)
        opp.high_priority = (
            opp.final_score >= hp_threshold
            and deadline_dt is not None
            and now <= deadline_dt <= deadline_cutoff
        )

        if (i + 1) % 20 == 0:
            log.info(f"  Scored {i + 1}/{len(opportunities)} opportunities...")

    # Sort by final_score descending
    opportunities.sort(key=lambda o: o.final_score, reverse=True)
    log.info(f"Scoring complete. Top score: {opportunities[0].final_score if opportunities else 0}")
    return opportunities

"""
Export scored opportunities to CSV, Markdown, and JSON.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime

import pandas as pd

from grant_scout.normalize import Opportunity
from grant_scout.utils import OUTPUTS_DIR, get_logger, now_utc, format_date

log = get_logger(__name__)


def export_csv(opportunities: list[Opportunity], path=None) -> str:
    """Write all opportunities to a CSV file. Returns the file path."""
    path = path or OUTPUTS_DIR / "opportunities.csv"

    if not opportunities:
        log.warning("No opportunities to export to CSV.")
        return str(path)

    rows = [opp.to_dict() for opp in opportunities]
    df = pd.DataFrame(rows)

    # Order columns nicely
    desired_order = [
        "id", "source", "agency", "title", "opportunity_number",
        "posted_date", "close_date", "deadline", "url",
        "final_score", "keyword_score", "semantic_score",
        "matched_topics", "high_priority", "rationale",
        "summary", "eligibility", "cost_share", "contact", "raw_tags",
    ]
    cols = [c for c in desired_order if c in df.columns]
    extra = [c for c in df.columns if c not in desired_order]
    df = df[cols + extra]

    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL)
    log.info(f"Wrote {len(df)} opportunities to {path}")
    return str(path)


def export_markdown(opportunities: list[Opportunity], top_n: int = 25, path=None) -> str:
    """Write top N opportunities to a Markdown report. Returns the file path."""
    path = path or OUTPUTS_DIR / "top_opportunities.md"

    now_str = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Top {top_n} Funding Opportunities for June Bio",
        f"_Generated: {now_str}_\n",
    ]

    if not opportunities:
        lines.append("No matching opportunities found.\n")
        _write(path, "\n".join(lines))
        return str(path)

    top = opportunities[:top_n]

    for rank, opp in enumerate(top, 1):
        priority_badge = " **HIGH PRIORITY**" if opp.high_priority else ""
        lines.append(f"## {rank}. {opp.title}{priority_badge}")
        lines.append("")
        lines.append(f"- **Score:** {opp.final_score} (keyword: {opp.keyword_score}, semantic: {opp.semantic_score})")
        lines.append(f"- **Source:** {opp.source} | **Agency:** {opp.agency}")
        lines.append(f"- **Opportunity #:** {opp.opportunity_number}")
        lines.append(f"- **Deadline:** {opp.deadline or 'Not specified'}")
        lines.append(f"- **Topics:** {opp.matched_topics or 'N/A'}")
        if opp.url:
            lines.append(f"- **Link:** {opp.url}")
        if opp.rationale:
            lines.append(f"- **AI Rationale:** {opp.rationale}")
        if opp.summary:
            # Truncate long summaries
            summary = opp.summary[:500]
            if len(opp.summary) > 500:
                summary += "..."
            lines.append(f"- **Summary:** {summary}")
        lines.append("")

    # Footer
    total = len(opportunities)
    hp_count = sum(1 for o in opportunities if o.high_priority)
    lines.append("---")
    lines.append(f"*Total matched: {total} | High priority: {hp_count} | Showing top {min(top_n, total)}*")

    _write(path, "\n".join(lines))
    log.info(f"Wrote top {min(top_n, len(opportunities))} opportunities to {path}")
    return str(path)


def export_json(opportunities: list[Opportunity], path=None) -> str:
    """Write a machine-readable weekly summary JSON. Returns the file path."""
    path = path or OUTPUTS_DIR / "weekly_summary.json"

    now = now_utc()
    total = len(opportunities)
    hp = [o for o in opportunities if o.high_priority]
    top25 = opportunities[:25]

    summary = {
        "generated_at": now.isoformat(),
        "total_opportunities": total,
        "high_priority_count": len(hp),
        "top_25": [
            {
                "rank": i + 1,
                "title": opp.title,
                "opportunity_number": opp.opportunity_number,
                "agency": opp.agency,
                "source": opp.source,
                "deadline": opp.deadline,
                "final_score": opp.final_score,
                "matched_topics": opp.matched_topics,
                "high_priority": opp.high_priority,
                "url": opp.url,
            }
            for i, opp in enumerate(top25)
        ],
        "high_priority_opportunities": [
            {
                "title": opp.title,
                "opportunity_number": opp.opportunity_number,
                "deadline": opp.deadline,
                "final_score": opp.final_score,
                "url": opp.url,
            }
            for opp in hp
        ],
    }

    _write(path, json.dumps(summary, indent=2, default=str))
    log.info(f"Wrote weekly summary to {path}")
    return str(path)


def _write(path, content: str):
    """Write string content to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

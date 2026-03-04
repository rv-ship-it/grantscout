"""
CLI entry point for June Bio Grant Scout.

Usage:
    python -m grant_scout fetch      # Fetch opportunities from all sources
    python -m grant_scout score      # Score fetched opportunities
    python -m grant_scout export     # Export scored opportunities to outputs/
    python -m grant_scout run        # Run the full pipeline (fetch → score → export)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from grant_scout.utils import DATA_RAW_DIR, OUTPUTS_DIR, get_logger

log = get_logger("grant_scout")

# Intermediate file for passing data between steps
FETCHED_FILE = DATA_RAW_DIR / "fetched_opportunities.json"
SCORED_FILE = DATA_RAW_DIR / "scored_opportunities.json"


def cmd_fetch() -> list[dict]:
    """Fetch opportunities from all configured sources."""
    from grant_scout.fetch_nih_guide import fetch_nih_opportunities
    from grant_scout.fetch_grants_gov import fetch_grants_gov_opportunities
    from grant_scout.dedupe import deduplicate

    log.info("=" * 60)
    log.info("STEP 1: Fetching opportunities")
    log.info("=" * 60)

    all_opps = []

    # NIH Guide
    try:
        nih = fetch_nih_opportunities()
        all_opps.extend(nih)
    except Exception as e:
        log.error(f"NIH Guide fetch failed: {e}")

    # Grants.gov
    try:
        ggov = fetch_grants_gov_opportunities()
        all_opps.extend(ggov)
    except Exception as e:
        log.error(f"Grants.gov fetch failed: {e}")

    if not all_opps:
        log.warning("No opportunities fetched from any source.")
        log.info("This may be due to API rate limits or network issues.")
        log.info("Check the data/raw/ folder for any partial downloads.")

    # Deduplicate
    all_opps = deduplicate(all_opps)

    log.info(f"Total unique opportunities after dedup: {len(all_opps)}")

    # Save intermediate results
    data = [opp.to_dict() for opp in all_opps]
    FETCHED_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    log.info(f"Saved fetched data to {FETCHED_FILE}")

    return data


def cmd_score() -> list[dict]:
    """Score previously fetched opportunities."""
    from grant_scout.normalize import Opportunity
    from grant_scout.scoring import score_opportunities

    log.info("=" * 60)
    log.info("STEP 2: Scoring opportunities")
    log.info("=" * 60)

    if not FETCHED_FILE.exists():
        log.error(f"No fetched data found at {FETCHED_FILE}")
        log.error("Run 'python -m grant_scout fetch' first.")
        sys.exit(1)

    data = json.loads(FETCHED_FILE.read_text(encoding="utf-8"))
    log.info(f"Loaded {len(data)} opportunities to score")

    # Reconstruct Opportunity objects
    opps = []
    for d in data:
        opp = Opportunity(**{k: v for k, v in d.items() if k in Opportunity.__dataclass_fields__})
        opps.append(opp)

    # Score
    scored = score_opportunities(opps)

    # Filter: only keep opportunities with score > 0
    relevant = [o for o in scored if o.final_score > 0]
    log.info(f"Relevant opportunities (score > 0): {len(relevant)} of {len(scored)}")

    # Save scored results
    data = [opp.to_dict() for opp in relevant]
    SCORED_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    log.info(f"Saved scored data to {SCORED_FILE}")

    return data


def cmd_export() -> None:
    """Export scored opportunities to final output files."""
    from grant_scout.normalize import Opportunity
    from grant_scout.report import export_csv, export_markdown, export_json

    log.info("=" * 60)
    log.info("STEP 3: Exporting outputs")
    log.info("=" * 60)

    if not SCORED_FILE.exists():
        log.error(f"No scored data found at {SCORED_FILE}")
        log.error("Run 'python -m grant_scout score' first.")
        sys.exit(1)

    data = json.loads(SCORED_FILE.read_text(encoding="utf-8"))
    log.info(f"Loaded {len(data)} scored opportunities")

    opps = []
    for d in data:
        opp = Opportunity(**{k: v for k, v in d.items() if k in Opportunity.__dataclass_fields__})
        opps.append(opp)

    # Sort by score (should already be sorted, but ensure it)
    opps.sort(key=lambda o: o.final_score, reverse=True)

    # Export all three formats
    csv_path = export_csv(opps)
    md_path = export_markdown(opps)
    json_path = export_json(opps)

    hp_count = sum(1 for o in opps if o.high_priority)

    log.info("=" * 60)
    log.info("EXPORT COMPLETE")
    log.info(f"  CSV:      {csv_path}")
    log.info(f"  Markdown: {md_path}")
    log.info(f"  JSON:     {json_path}")
    log.info(f"  Total:    {len(opps)} opportunities")
    log.info(f"  High priority: {hp_count}")
    log.info("=" * 60)


def cmd_run() -> None:
    """Run the full pipeline: fetch → score → export."""
    log.info("*" * 60)
    log.info("  June Bio Grant Scout – Full Pipeline")
    log.info("*" * 60)

    cmd_fetch()
    cmd_score()
    cmd_export()

    log.info("")
    log.info("Pipeline complete! Check the outputs/ folder.")


def main():
    parser = argparse.ArgumentParser(
        prog="grant_scout",
        description="June Bio Grant Scout – Find and rank funding opportunities.",
    )
    parser.add_argument(
        "command",
        choices=["fetch", "score", "export", "run"],
        help="Command to run: fetch, score, export, or run (full pipeline).",
    )
    args = parser.parse_args()

    commands = {
        "fetch": cmd_fetch,
        "score": cmd_score,
        "export": cmd_export,
        "run": cmd_run,
    }

    commands[args.command]()


if __name__ == "__main__":
    main()

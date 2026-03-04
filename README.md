# June Bio Grant Scout

Automated AI-powered workflow that finds and ranks **active funding opportunities** relevant to June Bio's research areas: gut health, microbiome, mucins/glycobiology, mucosal immunology, vaginal health, and biomanufacturing.

## What It Does

1. **Fetches** open funding opportunities from NIH Guide and Grants.gov
2. **Scores** each opportunity using keyword matching (+ optional Claude AI semantic scoring)
3. **Deduplicates** across sources
4. **Exports** ranked results to CSV, Markdown, and JSON

## Quick Start (VS Code)

### 1. Open the project

```bash
cd june-bio-grant-scout
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Enable AI-powered scoring

Copy the example env file and add your Claude API key:

```bash
cp .env.example .env
# Edit .env and set CLAUDE_API_KEY=sk-ant-...
```

Without a key, the tool uses keyword-only scoring — still fully functional!
Get a key at: https://console.anthropic.com/

To load the env file before running:

```bash
export $(grep -v '^#' .env | xargs)
```

### 5. Run the pipeline

```bash
PYTHONPATH=src python -m grant_scout run
```

### 6. View outputs

```
outputs/
  opportunities.csv         # All matched opportunities with scores
  top_opportunities.md      # Top 25 with bullets, deadlines, links
  weekly_summary.json       # Machine-readable summary
```

## CLI Commands

All commands are run from the project root with `PYTHONPATH=src`:

| Command | Description |
|---------|-------------|
| `python -m grant_scout fetch` | Fetch opportunities from all sources |
| `python -m grant_scout score` | Score fetched opportunities |
| `python -m grant_scout export` | Export scored results to outputs/ |
| `python -m grant_scout run` | Full pipeline (fetch → score → export) |

## Running Weekly via GitHub Actions (Recommended)

The repo includes `.github/workflows/weekly.yml` that runs every Monday at 8 AM UTC.

**Setup:**

1. Push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add a secret named `CLAUDE_API_KEY` with your Anthropic API key (optional)
4. The workflow will automatically fetch, score, and commit results weekly

You can also trigger it manually from the **Actions** tab → **Weekly Grant Scout** → **Run workflow**.

## Local Cron (macOS)

To run weekly on your Mac, add this to your crontab (`crontab -e`):

```cron
# Run Grant Scout every Monday at 8 AM local time
0 8 * * 1 cd /path/to/june-bio-grant-scout && source .venv/bin/activate && PYTHONPATH=src python -m grant_scout run >> /tmp/grant-scout.log 2>&1
```

## Data Sources

| Source | Method | Notes |
|--------|--------|-------|
| NIH Guide for Grants | RSS feeds (RFAs, PAs, NOSIs) | Official XML feeds, no API key needed |
| Grants.gov | REST API v1 | Public API, keyword search |

Raw API responses are saved to `data/raw/` with timestamps for auditability.

## Scoring

Each opportunity is scored 0–100 based on relevance to June Bio's areas:

- **Keyword score** (always active): Weighted keyword matching across title + summary
- **Semantic score** (requires `CLAUDE_API_KEY`): Claude AI rates relevance 0–100 with rationale

**Final score** = 0.6 × keyword + 0.4 × semantic (or keyword-only if no API key)

**High priority** = score above threshold AND deadline within 60 days.

Topics and weights are configured in `config/topics.yml`.

## Project Structure

```
june-bio-grant-scout/
  README.md
  requirements.txt
  .env.example
  config/
    topics.yml              # Topic keywords and weights
  src/
    grant_scout/
      __init__.py
      __main__.py           # python -m entry point
      main.py               # CLI commands
      fetch_nih_guide.py    # NIH Guide RSS fetcher
      fetch_grants_gov.py   # Grants.gov API fetcher
      normalize.py          # Unified opportunity schema
      scoring.py            # Keyword + semantic scoring
      dedupe.py             # Deduplication logic
      report.py             # CSV, Markdown, JSON exporters
      utils.py              # Shared utilities
  data/
    raw/                    # Raw API responses (timestamped)
  outputs/                  # Generated reports
  .github/
    workflows/
      weekly.yml            # GitHub Actions weekly automation
```

## Troubleshooting

### "No opportunities fetched from any source"

- **Check your internet connection** — the tool needs to reach NIH and Grants.gov APIs
- **API rate limits** — if you run many times quickly, APIs may temporarily block you. Wait a few minutes.
- **Check `data/raw/`** — raw responses are saved there even on partial failures, which helps debug

### "ModuleNotFoundError: No module named 'grant_scout'"

Make sure you set `PYTHONPATH=src` before the command:

```bash
PYTHONPATH=src python -m grant_scout run
```

### "No scored data found" / "Run fetch first"

Commands must be run in order: `fetch` → `score` → `export`. Or just use `run` to do all three.

### Semantic scoring not working

- Verify `CLAUDE_API_KEY` is set: `echo $CLAUDE_API_KEY`
- Make sure the key starts with `sk-ant-`
- Check you have API credits at https://console.anthropic.com/

### Empty or few results

- The tool only returns opportunities that match at least one keyword group
- Edit `config/topics.yml` to add more keywords if needed
- NIH Guide RSS feeds may have fewer items during certain periods

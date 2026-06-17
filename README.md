# 🇦🇺 Australian and International News Intelligence Agent

A multi-agent AI system that monitors Australian and international primary source feeds, analyses news for newsworthiness, and queues post drafts for human review before publishing to X (Twitter). Runs entirely on a local LLM via [Ollama](https://ollama.com) — no cloud API required.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Orchestrator                          │
│              (Coordinates pipeline & scheduling)             │
└──────────┬──────────────────────────────────────────────────┘
           │
    ┌──────▼──────┐
    │  Feed Agent  │  → Fetches RSS feeds and APIs (AU + International)
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │Summary Agent │  → Summarises content, extracts key facts & entities
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │Analysis Agent│  → Cross-references items, finds corroborations & contradictions
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  News Judge  │  → Scores newsworthiness (0–10), filters below threshold
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  Post Agent  │  → Drafts X post (≤280 chars)
    └──────┬──────┘
           │
    ┌──────▼──────────────────┐
    │ Pre-Post Review (Web UI) │  → Human reviews, edits, approves before publishing
    └─────────────────────────┘
```

## Feeds Monitored

### Australia
| Source | Category | Priority |
|--------|----------|----------|
| PM's Office (pm.gov.au) | Executive | High |
| Dept of PM & Cabinet (pmc.gov.au) | Executive | Medium |
| DFAT | Foreign Affairs | Medium |
| Dept of Infrastructure | Infrastructure | Medium |
| Reserve Bank of Australia | Economy | High |
| ABC News | General | Medium |
| ABS Data API (CPI, Labour Force, GDP) | Statistics | High |

### United States
| Source | Category | Priority |
|--------|----------|----------|
| White House News | Executive | High |
| Federal Reserve | Economy / Monetary Policy | High |
| Dept of Justice | Justice / Enforcement | Medium |

### International
| Source | Category | Priority |
|--------|----------|----------|
| United Nations News | International Affairs | Medium |
| CDC Recalls & Alerts | Health | Medium |

## Quick Start

```bash
# 1. Install Ollama and pull a model
#    https://ollama.com
ollama pull llama3

# 2. Clone and set up the project
git clone https://github.com/xandrew67/news.git
cd news
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Copy environment file
cp .env.example .env

# 4. Run the pipeline (fetches feeds, scores items, queues posts for review)
python main.py

# 5. Open the review UI to approve/edit posts before publishing
python main.py --serve
# → http://localhost:8080
```

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally with `llama3:latest` (or `llama3.2:latest`)
- No cloud API keys required

## Configuration

**`config/feeds.yaml`** — Add, remove, or adjust feed sources and priorities.

**`config/settings.yaml`** — Tune scoring thresholds, pipeline limits, and model selection.

Key settings:
```yaml
agent:
  model: llama3:latest        # Any Ollama model

scoring:
  min_newsworthy_score: 6     # 0–10, items below this are dropped
  max_items_per_run: 5        # Max posts queued per pipeline run

pipeline:
  poll_interval_minutes: 120  # Scheduling interval (--loop mode)
  max_feed_items: 20          # Items processed per run
```

## Review UI

After running the pipeline, open `http://localhost:8080` to review queued posts:

- **Pending** — AI-drafted posts awaiting your review
- **Approved** — Posts you've approved (ready to publish to X)
- **Rejected** — Dismissed items

Each card shows the item's score, source, summary, key facts, and an editable post draft with a live character counter.

## Usage

```bash
python main.py            # Run pipeline once
python main.py --loop     # Run continuously (every 2 hours by default)
python main.py --serve    # Start review web UI on port 8080
```

## Development

```bash
make install    # Install dependencies
make dev        # Run locally with debug logging
make test       # Run test suite
make lint       # Lint with ruff
```

## Project Structure

```
news/
├── agents/
│   ├── feed_agent.py                    # RSS + API fetching
│   ├── summary_agent.py                 # LLM summarisation
│   ├── analysis_agent.py                # Cross-reference analysis
│   ├── news_judge.py                    # Newsworthiness scoring
│   ├── post_agent.py                    # X post generation
│   ├── pre_post_review_edit_publish.py  # Review queue
│   ├── orchestrator.py                  # Pipeline coordinator
│   └── models.py                        # Shared data models
├── config/
│   ├── feeds.yaml                       # Feed configuration
│   └── settings.yaml                    # App settings
├── templates/
│   └── index.html                       # Review web UI
├── main.py                              # Entry point
└── web_app.py                           # Flask review server
```

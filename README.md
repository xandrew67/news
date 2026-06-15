# 🇦🇺 Australian News Intelligence Agent

A multi-agent AI system that monitors Australian primary source feeds, analyses news for newsworthiness, and generates X (Twitter) posts using Claude AI.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Orchestrator Agent                  │
│          (Coordinates pipeline & scheduling)          │
└──────────┬──────────────────────────────────────────┘
           │
    ┌──────▼──────┐
    │  Feed Agent  │  → Parses RSS/API feeds from aph.gov.au, ABS, data.gov.au
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │Summary Agent │  → Summarises raw feed content
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │Analysis Agent│  → Cross-references, finds corroborations/contradictions
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  News Judge  │  → Scores newsworthiness, filters regurgitation
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  Post Agent  │  → Generates X post (≤280 chars)
    └─────────────┘
```

## Feeds Monitored

- **Parliament (aph.gov.au):** Senate inquiries, committee reports, hearings, Hansard
- **PM's Office (pm.gov.au):** Statements, transcripts, speeches
- **ABS Data API:** Economic, social, and Census statistics
- **data.gov.au:** Open government datasets
- **Federal Court (fedcourt.gov.au):** Judgments and announcements
- **Ministerial/Departmental RSS:** Health, Foreign Affairs, Defence, Industry

## Quick Start

```bash
# 1. Copy environment file and add your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# 2. Run with Docker
make run

# 3. Or run locally (requires Python 3.11+)
make install
make run-local
```

## Requirements

- Docker Desktop for Mac
- Anthropic API key (set in `.env`)

## Configuration

Edit `config/feeds.yaml` to add/remove feeds.
Edit `config/settings.yaml` to tune scoring thresholds.

## Output

Posts are written to `output/posts.jsonl` (one JSON per line) and printed to stdout.

## Development

```bash
make dev        # Run in dev mode with auto-reload
make test       # Run test suite
make lint       # Lint code
make logs       # Tail Docker logs
```

#!/usr/bin/env bash
# Creates and pushes the project to GitHub under xandrew67/au-news-agent
# Requires: git, gh (GitHub CLI) installed and authenticated
set -e

REPO="au-news-agent"
OWNER="xandrew67"
DESC="Multi-agent AI system for monitoring Australian government primary source feeds and generating X posts"

echo "==> Initialising git repo..."
git init
git add .
git commit -m "feat: initial multi-agent AU news intelligence system

- FeedAgent: parses RSS (Parliament, RBA, PM, Health, Courts) and APIs (ABS, data.gov.au)
- SummaryAgent: Claude-powered summarisation with key facts and entity extraction
- AnalysisAgent: cross-references items for corroborations and contradictions
- NewsJudge: scores newsworthiness 0-10, filters regurgitation
- PostAgent: generates ≤280-char X posts
- Orchestrator: full pipeline with scheduling, deduplication, and state management
- Docker + Makefile for Mac-local and cloud deployment"

echo "==> Creating GitHub repo at $OWNER/$REPO..."
gh repo create "$OWNER/$REPO" \
  --public \
  --description "$DESC" \
  --source=. \
  --remote=origin \
  --push

echo ""
echo "✅ Repo created and pushed: https://github.com/$OWNER/$REPO"
echo ""
echo "Next steps:"
echo "  1. cd au-news-agent"
echo "  2. cp .env.example .env && edit .env (add ANTHROPIC_API_KEY)"
echo "  3. make run-once"

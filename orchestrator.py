"""
Orchestrator
Coordinates the full pipeline:
  FeedAgent → SummaryAgent → AnalysisAgent → NewsJudge → PostAgent

Manages state (seen IDs), deduplication, scheduling, and output.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic
import yaml

from agents.feed_agent import FeedAgent
from agents.summary_agent import SummaryAgent
from agents.analysis_agent import AnalysisAgent
from agents.news_judge import NewsJudge
from agents.post_agent import PostAgent
from agents.models import XPost

logger = logging.getLogger(__name__)


class Orchestrator:
    """Runs the full AU News Intelligence pipeline."""

    def __init__(self, settings_path: str = "config/settings.yaml",
                 feeds_path: str = "config/feeds.yaml"):
        with open(settings_path) as f:
            self.settings = yaml.safe_load(f)

        # Load env overrides
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        model = self.settings["agent"]["model"]
        max_tokens = self.settings["agent"]["max_tokens"]

        # Initialise agents
        self.feed_agent = FeedAgent(
            feeds_config_path=feeds_path,
            timeout=self.settings["pipeline"]["request_timeout_seconds"],
        )
        self.summary_agent = SummaryAgent(self.client, model, max_tokens=512)
        self.analysis_agent = AnalysisAgent(self.client, model, max_tokens=1024)
        self.news_judge = NewsJudge(
            self.client, model, max_tokens=1024,
            min_score=float(os.environ.get(
                "MIN_NEWSWORTHY_SCORE",
                self.settings["scoring"]["min_newsworthy_score"]
            )),
        )
        self.post_agent = PostAgent(self.client, model, max_tokens=128)

        # Paths
        self.post_file = Path(self.settings["output"]["post_file"])
        self.state_file = Path(self.settings["output"]["state_file"])
        self.max_items = self.settings["pipeline"]["max_feed_items"]
        self.max_posts = self.settings["scoring"]["max_items_per_run"]
        dedup_hours = self.settings["scoring"]["dedup_window_hours"]
        self.dedup_window = timedelta(hours=dedup_hours)

        # Post to X?
        self.post_to_x = (
            os.environ.get("X_API_KEY") and
            self.settings["output"].get("post_to_x", False)
        )

        # Ensure output dirs exist
        self.post_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  State management                                                    #
    # ------------------------------------------------------------------ #

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"seen_ids": [], "last_run": None}

    def _save_state(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))

    # ------------------------------------------------------------------ #
    #  Pipeline                                                            #
    # ------------------------------------------------------------------ #

    def run_once(self) -> list[XPost]:
        """Execute one full pipeline run. Returns generated posts."""
        logger.info("=" * 60)
        logger.info("Pipeline run starting at %s", datetime.utcnow().isoformat())

        state = self._load_state()
        seen_ids: set[str] = set(state.get("seen_ids", []))

        # Step 1: Fetch feeds
        feed_items = self.feed_agent.fetch_all(seen_ids)
        if not feed_items:
            logger.info("No new feed items. Pipeline done.")
            state["last_run"] = datetime.utcnow().isoformat()
            self._save_state(state)
            return []

        # Cap items per run
        feed_items = feed_items[:self.max_items]

        # Step 2: Summarise
        summarised = self.summary_agent.summarise_batch(feed_items)
        if not summarised:
            logger.info("No summaries produced. Pipeline done.")
            return []

        # Step 3: Analyse (cross-reference)
        analysed = self.analysis_agent.analyse(summarised)

        # Step 4: Score and filter
        scored = self.news_judge.score_batch(analysed)
        scored = sorted(scored, key=lambda x: x.score, reverse=True)
        scored = scored[:self.max_posts]

        # Step 5: Generate posts
        posts = self.post_agent.generate_batch(scored)

        # Step 6: Persist posts
        self._write_posts(posts)

        # Step 7: (Optional) post to X
        if self.post_to_x:
            self._post_to_x(posts)

        # Step 8: Update state
        new_ids = [fi.id for fi in feed_items]
        state["seen_ids"] = list(seen_ids | set(new_ids))
        # Prune old IDs (keep last 5000)
        state["seen_ids"] = state["seen_ids"][-5000:]
        state["last_run"] = datetime.utcnow().isoformat()
        self._save_state(state)

        logger.info("Pipeline complete. %d posts generated.", len(posts))
        for p in posts:
            logger.info("  [%.1f] %s", p.score, p.text[:100])
        return posts

    def run_loop(self) -> None:
        """Run the pipeline in a loop, sleeping between runs."""
        interval = int(os.environ.get(
            "POLL_INTERVAL_MINUTES",
            self.settings["pipeline"]["poll_interval_minutes"]
        )) * 60
        logger.info("Starting scheduler (interval: %ds)", interval)
        while True:
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Pipeline run failed: %s", exc, exc_info=True)
            logger.info("Sleeping %d seconds until next run...", interval)
            time.sleep(interval)

    # ------------------------------------------------------------------ #
    #  Output helpers                                                      #
    # ------------------------------------------------------------------ #

    def _write_posts(self, posts: list[XPost]) -> None:
        """Append posts to the JSONL output file."""
        with self.post_file.open("a") as f:
            for post in posts:
                f.write(json.dumps(post.to_dict()) + "\n")
        logger.debug("Wrote %d posts to %s", len(posts), self.post_file)

    def _post_to_x(self, posts: list[XPost]) -> None:
        """Post to X using tweepy. Only called when credentials are present."""
        try:
            import tweepy  # type: ignore
            client = tweepy.Client(
                consumer_key=os.environ["X_API_KEY"],
                consumer_secret=os.environ["X_API_SECRET"],
                access_token=os.environ["X_ACCESS_TOKEN"],
                access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
            )
            for post in posts:
                try:
                    client.create_tweet(text=post.text)
                    logger.info("Posted to X: %s", post.text[:80])
                except Exception as exc:
                    logger.warning("X post failed: %s", exc)
        except ImportError:
            logger.warning("tweepy not installed — cannot post to X")

"""
Feed Agent
Parses Australian primary source RSS feeds and APIs.
Returns a list of FeedItem objects for downstream processing.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import Optional

import feedparser
import requests
import yaml

from agents.models import FeedItem

logger = logging.getLogger(__name__)


def _make_id(url: str, title: str) -> str:
    """Stable ID from URL + title hash."""
    raw = f"{url}::{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_date(entry) -> Optional[datetime]:
    """Best-effort date extraction from a feedparser entry."""
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6])
    except Exception:
        pass
    return None


class FeedAgent:
    """Fetches and normalises all configured feeds."""

    def __init__(self, feeds_config_path: str = "config/feeds.yaml",
                 timeout: int = 30):
        with open(feeds_config_path) as f:
            self.config = yaml.safe_load(f)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "AUNewsAgent/0.1 (+https://github.com/xandrew67/au-news-agent)"
        )

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def fetch_all(self, seen_ids: set[str]) -> list[FeedItem]:
        """Fetch every configured feed and return unseen FeedItems."""
        items: list[FeedItem] = []
        for feed_cfg in self.config.get("rss_feeds", []):
            try:
                items.extend(self._fetch_rss(feed_cfg, seen_ids))
            except Exception as exc:
                logger.warning("RSS feed %s failed: %s", feed_cfg["name"], exc)

        for api_cfg in self.config.get("api_feeds", []):
            try:
                if api_cfg["type"] == "abs":
                    items.extend(self._fetch_abs(api_cfg, seen_ids))
                elif api_cfg["type"] == "ckan":
                    items.extend(self._fetch_ckan(api_cfg, seen_ids))
            except Exception as exc:
                logger.warning("API feed %s failed: %s", api_cfg["name"], exc)

        logger.info("Feed agent fetched %d new items", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  RSS feeds                                                           #
    # ------------------------------------------------------------------ #

    def _fetch_rss(self, cfg: dict, seen_ids: set[str]) -> list[FeedItem]:
        logger.debug("Fetching RSS: %s", cfg["url"])
        feed = feedparser.parse(cfg["url"], request_headers={
            "User-Agent": self.session.headers["User-Agent"]
        })
        items = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            url = entry.get("link", "")
            content = (
                entry.get("summary", "")
                or entry.get("content", [{}])[0].get("value", "")
            ).strip()

            item_id = entry.get("id") or _make_id(url, title)
            if item_id in seen_ids:
                continue

            items.append(FeedItem(
                id=item_id,
                title=title,
                content=content,
                url=url,
                source_name=cfg["name"],
                category=cfg.get("category", "general"),
                published_at=_parse_date(entry),
            ))

        logger.debug("  → %d new items from %s", len(items), cfg["name"])
        return items

    # ------------------------------------------------------------------ #
    #  ABS Data API                                                        #
    # ------------------------------------------------------------------ #

    def _fetch_abs(self, cfg: dict, seen_ids: set[str]) -> list[FeedItem]:
        """
        Polls the ABS REST API for recent dataflow releases.
        Endpoint: /rest/{dataflow}/{key}/all?startPeriod=...
        We use the dataflow-level 'all' endpoint with a recent start period
        to detect when new data has been published.
        """
        items = []
        base_url = cfg["base_url"].rstrip("/")
        for dataflow in cfg.get("dataflows", []):
            url = f"{base_url}/data/{dataflow}/all/all?detail=serieskeysonly&format=jsondata"
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    item_id = _make_id(url, dataflow)
                    if item_id not in seen_ids:
                        data = resp.json()
                        # Extract release header info
                        header = data.get("header", {})
                        prepared = header.get("prepared", "")
                        sender = header.get("sender", {}).get("name", "ABS")
                        title = f"ABS Data Release: {dataflow} ({prepared[:10] if prepared else 'recent'})"
                        content = (
                            f"New ABS data published for dataflow '{dataflow}' "
                            f"by {sender}. Prepared: {prepared}. "
                            f"Check ABS Data Explorer for details."
                        )
                        items.append(FeedItem(
                            id=item_id,
                            title=title,
                            content=content,
                            url=f"https://www.abs.gov.au/statistics",
                            source_name=cfg["name"],
                            category=cfg.get("category", "statistics"),
                            extra={"dataflow": dataflow},
                        ))
            except Exception as exc:
                logger.debug("ABS dataflow %s error: %s", dataflow, exc)
            time.sleep(0.5)  # Be polite to the ABS API

        logger.debug("  → %d new items from ABS", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  data.gov.au CKAN API                                                #
    # ------------------------------------------------------------------ #

    def _fetch_ckan(self, cfg: dict, seen_ids: set[str]) -> list[FeedItem]:
        """Fetches recently changed packages from the CKAN API."""
        params = cfg.get("params", {})
        resp = self.session.get(cfg["url"], params=params, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json().get("result", [])

        items = []
        for activity in result:
            data = activity.get("data", {})
            pkg = data.get("package", {})
            title = pkg.get("title", "Unknown dataset")
            pkg_id = pkg.get("id", "")
            item_id = _make_id(cfg["url"], pkg_id or title)

            if item_id in seen_ids:
                continue

            notes = pkg.get("notes", "No description available.")
            org = (pkg.get("organization") or {}).get("title", "Unknown org")
            url = f"https://data.gov.au/dataset/{pkg.get('name', '')}"

            items.append(FeedItem(
                id=item_id,
                title=f"[data.gov.au] {title}",
                content=f"Organisation: {org}\n\n{notes}",
                url=url,
                source_name=cfg["name"],
                category=cfg.get("category", "open_data"),
            ))

        logger.debug("  → %d new items from data.gov.au", len(items))
        return items

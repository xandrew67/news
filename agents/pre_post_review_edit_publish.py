"""
Pre-Post Review, Edit & Publish
Sits between PostAgent and X publishing. Queues generated post drafts
for human review in the browser before any external publishing occurs.

Stores state in output/review_queue.json as a list of post entries:
  - pending:  awaiting review
  - approved: user approved (ready to publish to X)
  - rejected: user dismissed
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.models import XPost, ScoredItem

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_FILE = Path("output/review_queue.json")


class PrePostReviewEditPublish:
    """Manages the pre-publish review queue."""

    def __init__(self, queue_file: Path = DEFAULT_QUEUE_FILE):
        self.queue_file = queue_file
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Persistence                                                         #
    # ------------------------------------------------------------------ #

    def _load(self) -> list[dict]:
        if self.queue_file.exists():
            try:
                return json.loads(self.queue_file.read_text())
            except Exception:
                return []
        return []

    def _save(self, items: list[dict]) -> None:
        self.queue_file.write_text(json.dumps(items, indent=2))

    # ------------------------------------------------------------------ #
    #  Pipeline interface (called by Orchestrator)                        #
    # ------------------------------------------------------------------ #

    def enqueue(self, posts: list[XPost], scored_items: list[ScoredItem]) -> int:
        """
        Add PostAgent-generated drafts to the review queue.
        Enriches each entry with scored item metadata for the review UI.
        Returns the number of new items added.
        """
        scored_by_id = {
            s.analysed_item.summarised_item.feed_item.id: s
            for s in scored_items
        }

        items = self._load()
        existing_feed_ids = {item["feed_item_id"] for item in items}
        added = 0

        for post in posts:
            if post.feed_item_id in existing_feed_ids:
                continue

            entry: dict = {
                "id": str(uuid.uuid4()),
                "feed_item_id": post.feed_item_id,
                "draft_text": post.text,
                "source_url": post.source_url,
                "source_name": post.source_name,
                "score": post.score,
                "generated_at": post.generated_at.isoformat(),
                "queued_at": datetime.utcnow().isoformat(),
                "status": "pending",
                "reviewed_at": None,
                "final_text": None,
                # Metadata filled in below
                "title": "",
                "category": "",
                "summary": "",
                "key_facts": [],
                "entities": [],
                "corroborations": [],
                "contradictions": [],
                "context_notes": "",
                "score_rationale": "",
            }

            scored = scored_by_id.get(post.feed_item_id)
            if scored:
                si = scored.analysed_item.summarised_item
                ai = scored.analysed_item
                entry.update({
                    "title": si.feed_item.title,
                    "category": si.feed_item.category,
                    "summary": si.summary,
                    "key_facts": si.key_facts,
                    "entities": si.entities,
                    "corroborations": ai.corroborations,
                    "contradictions": ai.contradictions,
                    "context_notes": ai.context_notes,
                    "score_rationale": scored.score_rationale,
                })

            items.append(entry)
            added += 1

        self._save(items)
        logger.info(
            "Review queue: +%d items (%d total, %d pending)",
            added, len(items),
            sum(1 for i in items if i["status"] == "pending"),
        )
        return added

    # ------------------------------------------------------------------ #
    #  Query interface (called by web app)                                #
    # ------------------------------------------------------------------ #

    def get_all(self) -> list[dict]:
        return self._load()

    def get_by_status(self, status: str) -> list[dict]:
        return [i for i in self._load() if i["status"] == status]

    # ------------------------------------------------------------------ #
    #  Action interface (called by web app)                               #
    # ------------------------------------------------------------------ #

    def approve(self, item_id: str, final_text: Optional[str] = None) -> bool:
        """
        Approve a post for publishing.
        final_text overrides the draft; if omitted, draft_text is used.
        """
        return self._set_status(item_id, "approved", final_text)

    def reject(self, item_id: str) -> bool:
        return self._set_status(item_id, "rejected")

    def _set_status(self, item_id: str, status: str,
                    final_text: Optional[str] = None) -> bool:
        items = self._load()
        for item in items:
            if item["id"] == item_id:
                item["status"] = status
                item["reviewed_at"] = datetime.utcnow().isoformat()
                if status == "approved":
                    item["final_text"] = final_text if final_text is not None else item["draft_text"]
                self._save(items)
                logger.info("Review queue: %s → %s", item_id[:8], status)
                return True
        return False

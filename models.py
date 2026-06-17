"""Shared data models for the AU News Agent pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FeedItem:
    """A raw item fetched from a feed."""
    id: str                          # Unique identifier (URL or hash)
    title: str
    content: str                     # Raw body text
    url: str
    source_name: str
    category: str
    published_at: Optional[datetime] = None
    extra: dict = field(default_factory=dict)


@dataclass
class SummarisedItem:
    """A feed item with an AI-generated summary."""
    feed_item: FeedItem
    summary: str
    key_facts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # People, orgs, topics


@dataclass
class AnalysedItem:
    """A summarised item with cross-reference analysis."""
    summarised_item: SummarisedItem
    corroborations: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    context_notes: str = ""


@dataclass
class ScoredItem:
    """An analysed item with a newsworthiness score."""
    analysed_item: AnalysedItem
    score: float                     # 0–10
    score_rationale: str
    is_original: bool = True         # False if it's regurgitation


@dataclass
class XPost:
    """A ready-to-publish X post."""
    text: str                        # ≤280 chars
    source_url: str
    source_name: str
    score: float
    generated_at: datetime = field(default_factory=datetime.utcnow)
    feed_item_id: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "score": self.score,
            "generated_at": self.generated_at.isoformat(),
            "feed_item_id": self.feed_item_id,
        }

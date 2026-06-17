"""
Summary Agent
Uses Claude to summarise each FeedItem and extract key facts and entities.
"""
from __future__ import annotations

import logging
from typing import Optional

import anthropic

from agents.models import FeedItem, SummarisedItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a specialist Australian political and economic analyst.
You summarise official Australian government announcements, parliamentary proceedings,
statistical releases, and judicial decisions concisely and accurately.

Always output ONLY valid JSON in this exact structure:
{
  "summary": "2-3 sentence plain-English summary",
  "key_facts": ["fact 1", "fact 2", "fact 3"],
  "entities": ["entity1", "entity2"]
}

Rules:
- summary: factual, neutral, 2-3 sentences, no opinion
- key_facts: 3-5 specific, verifiable claims from the content
- entities: people, organisations, legislation, policies, or topics mentioned
- No preamble, no markdown, no trailing text — raw JSON only
"""


class SummaryAgent:
    """Summarises FeedItems using Claude."""

    def __init__(self, client: anthropic.Anthropic, model: str,
                 max_tokens: int = 512):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def summarise(self, item: FeedItem) -> Optional[SummarisedItem]:
        """
        Summarise a single FeedItem.
        Returns None if the item has insufficient content.
        """
        text = f"TITLE: {item.title}\n\nSOURCE: {item.source_name}\nURL: {item.url}\n\nCONTENT:\n{item.content}"

        if len(item.content.strip()) < 20:
            logger.debug("Skipping item '%s' — too short", item.title)
            return None

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = response.content[0].text.strip()
            parsed = _safe_json(raw)

            return SummarisedItem(
                feed_item=item,
                summary=parsed.get("summary", item.title),
                key_facts=parsed.get("key_facts", []),
                entities=parsed.get("entities", []),
            )
        except Exception as exc:
            logger.warning("Summary failed for '%s': %s", item.title, exc)
            return None

    def summarise_batch(self, items: list[FeedItem]) -> list[SummarisedItem]:
        """Summarise a list of FeedItems, skipping failures."""
        results = []
        for item in items:
            result = self.summarise(item)
            if result:
                results.append(result)
        logger.info("Summary agent produced %d summaries from %d items",
                    len(results), len(items))
        return results


def _safe_json(text: str) -> dict:
    """Parse JSON, stripping markdown fences if present."""
    import json
    # Strip ```json fences
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.debug("JSON parse failed, returning empty dict")
        return {}

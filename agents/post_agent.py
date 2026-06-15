"""
Post Agent
Generates X (Twitter) posts from ScoredItems.
Posts are ≤280 chars, factual, and include a source URL.
"""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from agents.models import ScoredItem, XPost

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write factual, punchy X (Twitter) posts about Australian government
news for an informed Australian audience.

Rules:
- TOTAL length including URL must be ≤260 characters (leave room for URL)
- No hashtags unless they are official (e.g. #Budget2025)
- No emojis
- Start with the most important fact — no "BREAKING:" prefix
- Plain language, active voice
- End with a space (the caller will append the URL)
- Do not fabricate statistics — only use what is in the facts provided
- Never editorialize or express opinion

Output ONLY the post text, nothing else. No quotes around it.
"""


class PostAgent:
    """Generates X posts from ScoredItems."""

    def __init__(self, client: OpenAI, model: str,
                 max_tokens: int = 128):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, item: ScoredItem) -> Optional[XPost]:
        """Generate an X post for a single scored item."""
        fi = item.analysed_item.summarised_item.feed_item
        si = item.analysed_item.summarised_item
        ai = item.analysed_item

        context = f"""SOURCE: {fi.source_name}
TITLE: {fi.title}
SUMMARY: {si.summary}
KEY FACTS: {'; '.join(si.key_facts)}
"""
        if ai.corroborations:
            context += f"CORROBORATED BY: {'; '.join(ai.corroborations)}\n"
        if ai.contradictions:
            context += f"CONTRADICTS: {'; '.join(ai.contradictions)}\n"
        if ai.context_notes:
            context += f"CONTEXT: {ai.context_notes}\n"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
            )
            post_text = response.choices[0].message.content.strip()

            # Append URL — trim post if needed
            url = fi.url
            full = f"{post_text} {url}"
            if len(full) > 280:
                # Trim post text to fit
                allowed = 280 - len(url) - 2  # space + buffer
                post_text = post_text[:allowed].rsplit(" ", 1)[0] + "…"
                full = f"{post_text} {url}"

            logger.debug("Generated post (%d chars): %s", len(full), full[:80])
            return XPost(
                text=full,
                source_url=url,
                source_name=fi.source_name,
                score=item.score,
                feed_item_id=fi.id,
            )
        except Exception as exc:
            logger.warning("Post generation failed for '%s': %s", fi.title, exc)
            return None

    def generate_batch(self, items: list[ScoredItem]) -> list[XPost]:
        """Generate posts for a list of scored items."""
        posts = []
        for item in items:
            post = self.generate(item)
            if post:
                posts.append(post)
        logger.info("Post agent generated %d posts", len(posts))
        return posts

"""
Analysis Agent
Cross-references summarised items against each other to find:
- Corroborations (multiple sources confirming the same fact)
- Contradictions (conflicting data or claims)
- Context (related background from the same batch)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from agents.models import AnalysedItem, SummarisedItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an investigative analyst specialising in Australian politics,
economics, and public policy. You examine multiple news summaries and identify
relationships between them.

For each item, check the OTHER items and identify:
1. Corroborations: other items that confirm or strengthen this story
2. Contradictions: other items whose data or claims conflict with this one
3. Context: relevant background from other items that adds meaning

Output ONLY a JSON array with one object per input item (same order):
[
  {
    "corroborations": ["description of corroborating item"],
    "contradictions": ["description of contradicting item"],
    "context_notes": "1-2 sentence context note, or empty string"
  },
  ...
]

Rules:
- Empty arrays/strings are fine when nothing applies
- Be specific: cite the source names when noting relationships
- Raw JSON only, no markdown, no preamble
"""


class AnalysisAgent:
    """Cross-references SummarisedItems to find links and contradictions."""

    def __init__(self, client: anthropic.Anthropic, model: str,
                 max_tokens: int = 1024):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def analyse(self, items: list[SummarisedItem]) -> list[AnalysedItem]:
        """
        Analyse a batch of summarised items together.
        Falls back to empty analysis if the API call fails.
        """
        if not items:
            return []

        if len(items) == 1:
            # Single item — no cross-referencing possible
            return [AnalysedItem(summarised_item=items[0])]

        # Build a compact representation for the LLM
        items_text = json.dumps([
            {
                "index": i,
                "source": s.feed_item.source_name,
                "title": s.feed_item.title,
                "summary": s.summary,
                "key_facts": s.key_facts,
                "entities": s.entities,
            }
            for i, s in enumerate(items)
        ], indent=2)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Analyse these {len(items)} items:\n\n{items_text}"
                }],
            )
            raw = response.content[0].text.strip()
            analyses = _safe_json_list(raw)

            results = []
            for i, s_item in enumerate(items):
                ana = analyses[i] if i < len(analyses) else {}
                results.append(AnalysedItem(
                    summarised_item=s_item,
                    corroborations=ana.get("corroborations", []),
                    contradictions=ana.get("contradictions", []),
                    context_notes=ana.get("context_notes", ""),
                ))
            logger.info("Analysis agent processed %d items", len(results))
            return results

        except Exception as exc:
            logger.warning("Analysis failed: %s — using empty analysis", exc)
            return [AnalysedItem(summarised_item=s) for s in items]


def _safe_json_list(text: str) -> list[dict]:
    """Parse a JSON array, stripping markdown fences."""
    import json
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        logger.debug("Analysis JSON parse failed")
        return []

"""
News Judge Agent
Scores each AnalysedItem for newsworthiness (0–10) and filters regurgitation.

Scoring criteria:
- Policy/legislative impact (high weight)
- Statistical significance / new data release (high weight)
- Originality vs. known/recurring topic (penalty for regurgitation)
- Cross-source corroboration bonus
- Contradiction bonus (conflict = newsworthy)
- Timeliness
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from agents.models import AnalysedItem, ScoredItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior Australian news editor deciding what is genuinely
newsworthy. You evaluate items from official government sources and score them.

Score each item 0–10 using these criteria:
- 8-10: Breaking policy, law passed, major stat shift, unexpected announcement
- 6-7:  New inquiry, confirmed data trend, significant departmental announcement
- 4-5:  Routine update, minor policy detail, procedural notice
- 2-3:  Scheduled/expected, low-impact update
- 0-1:  Pure regurgitation of known facts, ceremonial, no new information

Penalise items that:
- Repeat information widely reported already (regurgitation)
- Are calendar/scheduling notices with no substantive content
- Are purely administrative (appointments to minor committees, etc.)

Bonus for items that:
- Are corroborated by another source
- Contradict something published recently
- Contain new quantitative data (e.g. GDP, unemployment figures)

Output ONLY a JSON array, same order as input, one object per item:
[
  {
    "score": 7.5,
    "rationale": "1-2 sentence explanation",
    "is_original": true
  },
  ...
]

Raw JSON only. No markdown. No preamble.
"""


class NewsJudge:
    """Scores and filters AnalysedItems for newsworthiness."""

    def __init__(self, client: anthropic.Anthropic, model: str,
                 max_tokens: int = 1024, min_score: float = 6.0):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.min_score = min_score

    def score_batch(self, items: list[AnalysedItem]) -> list[ScoredItem]:
        """Score a batch and return only items meeting the threshold."""
        if not items:
            return []

        items_text = json.dumps([
            {
                "index": i,
                "source": a.summarised_item.feed_item.source_name,
                "title": a.summarised_item.feed_item.title,
                "summary": a.summarised_item.summary,
                "key_facts": a.summarised_item.key_facts,
                "corroborations": a.corroborations,
                "contradictions": a.contradictions,
                "context_notes": a.context_notes,
            }
            for i, a in enumerate(items)
        ], indent=2)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Score these {len(items)} items:\n\n{items_text}"
                }],
            )
            raw = response.content[0].text.strip()
            scores = _safe_json_list(raw)

            results = []
            for i, a_item in enumerate(items):
                s = scores[i] if i < len(scores) else {}
                score_val = float(s.get("score", 0))
                scored = ScoredItem(
                    analysed_item=a_item,
                    score=score_val,
                    score_rationale=s.get("rationale", ""),
                    is_original=s.get("is_original", True),
                )
                if score_val >= self.min_score:
                    results.append(scored)
                else:
                    logger.debug(
                        "Dropped '%s' (score %.1f < %.1f)",
                        a_item.summarised_item.feed_item.title,
                        score_val, self.min_score
                    )

            logger.info(
                "News judge: %d/%d items passed score threshold %.1f",
                len(results), len(items), self.min_score
            )
            return results

        except Exception as exc:
            logger.warning("Scoring failed: %s", exc)
            return []


def _safe_json_list(text: str) -> list[dict]:
    import json
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []

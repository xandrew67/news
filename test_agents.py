"""
Test suite for AU News Intelligence Agent.
Uses mocked Claude API responses for unit tests.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from agents.models import FeedItem, SummarisedItem, AnalysedItem, ScoredItem
from agents.summary_agent import SummaryAgent, _safe_json
from agents.analysis_agent import AnalysisAgent
from agents.news_judge import NewsJudge
from agents.post_agent import PostAgent


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_feed_item():
    return FeedItem(
        id="abc123",
        title="RBA raises cash rate by 25 basis points to 4.60%",
        content=(
            "The Reserve Bank of Australia today increased the official cash rate "
            "target by 25 basis points to 4.60 per cent. Governor Michele Bullock "
            "said the decision reflects the Board's determination to return inflation "
            "to the 2-3 per cent target range."
        ),
        url="https://www.rba.gov.au/media-releases/2025/mr-25-01.html",
        source_name="Reserve Bank Media Releases",
        category="economy",
        published_at=datetime(2025, 6, 3, 14, 30),
    )


@pytest.fixture
def mock_anthropic_client():
    client = MagicMock()
    return client


def _make_text_response(text: str):
    """Build a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ── Unit tests: _safe_json ─────────────────────────────────────────────────────

def test_safe_json_clean():
    raw = '{"summary": "test", "key_facts": [], "entities": []}'
    assert _safe_json(raw) == {"summary": "test", "key_facts": [], "entities": []}


def test_safe_json_with_fences():
    raw = '```json\n{"summary": "test"}\n```'
    assert _safe_json(raw) == {"summary": "test"}


def test_safe_json_invalid():
    assert _safe_json("not json at all") == {}


# ── Unit tests: SummaryAgent ───────────────────────────────────────────────────

def test_summary_agent_returns_summarised_item(mock_anthropic_client, sample_feed_item):
    mock_response_json = json.dumps({
        "summary": "The RBA raised rates by 25bp to 4.60%.",
        "key_facts": ["Rate raised to 4.60%", "Governor cited inflation target"],
        "entities": ["RBA", "Michele Bullock", "cash rate"],
    })
    mock_anthropic_client.messages.create.return_value = _make_text_response(mock_response_json)

    agent = SummaryAgent(mock_anthropic_client, model="claude-test", max_tokens=512)
    result = agent.summarise(sample_feed_item)

    assert result is not None
    assert result.summary == "The RBA raised rates by 25bp to 4.60%."
    assert "RBA" in result.entities
    assert result.feed_item == sample_feed_item


def test_summary_agent_skips_empty_content(mock_anthropic_client):
    item = FeedItem(
        id="x", title="hi", content="", url="http://x.com",
        source_name="Test", category="test"
    )
    agent = SummaryAgent(mock_anthropic_client, model="claude-test")
    result = agent.summarise(item)
    assert result is None
    mock_anthropic_client.messages.create.assert_not_called()


# ── Unit tests: NewsJudge ──────────────────────────────────────────────────────

def test_news_judge_filters_below_threshold(mock_anthropic_client, sample_feed_item):
    summarised = SummarisedItem(
        feed_item=sample_feed_item,
        summary="RBA raised rates.",
        key_facts=["rate raised"],
        entities=["RBA"],
    )
    analysed = AnalysedItem(summarised_item=summarised)

    mock_response_json = json.dumps([
        {"score": 4.0, "rationale": "Routine expected rate rise.", "is_original": True}
    ])
    mock_anthropic_client.messages.create.return_value = _make_text_response(mock_response_json)

    judge = NewsJudge(mock_anthropic_client, "claude-test", min_score=6.0)
    results = judge.score_batch([analysed])
    assert len(results) == 0  # Score 4.0 < threshold 6.0


def test_news_judge_passes_above_threshold(mock_anthropic_client, sample_feed_item):
    summarised = SummarisedItem(
        feed_item=sample_feed_item,
        summary="RBA raised rates unexpectedly.",
        key_facts=["unexpected hike"],
        entities=["RBA"],
    )
    analysed = AnalysedItem(summarised_item=summarised)

    mock_response_json = json.dumps([
        {"score": 8.5, "rationale": "Surprise rate hike — high impact.", "is_original": True}
    ])
    mock_anthropic_client.messages.create.return_value = _make_text_response(mock_response_json)

    judge = NewsJudge(mock_anthropic_client, "claude-test", min_score=6.0)
    results = judge.score_batch([analysed])
    assert len(results) == 1
    assert results[0].score == 8.5


# ── Unit tests: PostAgent ──────────────────────────────────────────────────────

def test_post_agent_generates_valid_post(mock_anthropic_client, sample_feed_item):
    summarised = SummarisedItem(
        feed_item=sample_feed_item,
        summary="RBA raises cash rate by 25bp to 4.60%.",
        key_facts=["Rate: 4.60%"],
        entities=["RBA"],
    )
    analysed = AnalysedItem(summarised_item=summarised)
    scored = ScoredItem(analysed_item=analysed, score=8.5, score_rationale="Major move")

    mock_text = "RBA lifts cash rate 25bp to 4.60%, citing persistent inflation above target band."
    mock_anthropic_client.messages.create.return_value = _make_text_response(mock_text)

    agent = PostAgent(mock_anthropic_client, "claude-test")
    post = agent.generate(scored)

    assert post is not None
    assert len(post.text) <= 280
    assert sample_feed_item.url in post.text


def test_post_trimmed_if_too_long(mock_anthropic_client, sample_feed_item):
    summarised = SummarisedItem(
        feed_item=sample_feed_item, summary="s", key_facts=[], entities=[]
    )
    analysed = AnalysedItem(summarised_item=summarised)
    scored = ScoredItem(analysed_item=analysed, score=7.0, score_rationale="ok")

    # Very long post text that needs trimming
    long_text = "A" * 260
    mock_anthropic_client.messages.create.return_value = _make_text_response(long_text)

    agent = PostAgent(mock_anthropic_client, "claude-test")
    post = agent.generate(scored)
    assert post is not None
    assert len(post.text) <= 280

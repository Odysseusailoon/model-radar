"""Classifier JSON parsing/normalization — the highest-risk logic (LLM output
is untrusted text). No network; pure functions only."""
import pytest

from app.classifier import _extract_json, _normalize, VALID_CATEGORIES


def test_extract_plain_json():
    out = _extract_json('{"category": "demo", "confidence": 0.9}')
    assert out["category"] == "demo"


def test_extract_json_from_code_fence():
    raw = '```json\n{"category": "expert_review", "relevant": true}\n```'
    assert _extract_json(raw)["category"] == "expert_review"


def test_extract_json_with_surrounding_prose():
    raw = 'Sure, here is the result: {"category": "promo"} hope that helps!'
    assert _extract_json(raw)["category"] == "promo"


def test_extract_json_invalid_raises():
    with pytest.raises(Exception):
        _extract_json("this is not json at all")


def test_normalize_coerces_bad_category_and_clamps_confidence():
    data = _normalize({
        "category": "totally_made_up",
        "confidence": 5.0,           # out of range -> clamp to 1.0
        "sentiment": "angry",        # invalid -> neutral
        "author_credibility_signals": "not-a-list",
        "relevant": 1,
    })
    assert data["category"] == "irrelevant"          # unknown collapses to irrelevant
    assert data["category"] in VALID_CATEGORIES
    assert data["confidence"] == 1.0
    assert data["sentiment"] == "neutral"
    assert data["author_credibility_signals"] == ["not-a-list"]
    assert data["relevant"] is True
    assert data["classification_failed"] is False


def test_normalize_fills_defaults_for_missing_keys():
    data = _normalize({})
    for key in ("relevant", "category", "confidence", "sentiment", "has_media_evidence",
                "author_credibility_signals", "quotable_excerpt", "summary_zh",
                "usable_for_marketing", "usability_reason"):
        assert key in data

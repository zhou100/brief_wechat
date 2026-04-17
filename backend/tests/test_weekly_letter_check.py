"""
Unit tests for _check_weekly_letter (Stage 2 validator).

Covers deterministic checks (paragraph count, uncomfortable_truth/next_week_action
containment) and best-effort behavior when the LLM groundedness call fails.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.v1.entries import _check_weekly_letter


ANALYSIS = {
    "uncomfortable_truth": "You spent more time scrolling Twitter than writing code.",
    "next_week_action": "Block social media until lunch on three weekdays.",
    "patterns": ["fragmented focus", "late starts"],
    "naval_balance": "Heavy on LEARNING, light on FAMILY.",
}


def _letter(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraphs)


def _mock_grounded(result: dict):
    """Mock the OpenAI groundedness check returning the given JSON."""
    import json as _json
    choice = MagicMock()
    choice.message.content = _json.dumps(result)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_valid_letter_passes_all_checks():
    letter = _letter([
        "This week showed fragmented focus and late starts. Heavy on LEARNING, light on FAMILY.",
        "What is working: you finished the three hardest commits on Tuesday and Thursday despite distractions.",
        "What is not working: You spent more time scrolling Twitter than writing code. Be honest about that.",
        "Next week: Block social media until lunch on three weekdays. Concrete, measurable, simple.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_grounded({"grounded": True, "reason": "ok"})
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    assert issues == []


@pytest.mark.asyncio
async def test_three_paragraphs_fails():
    letter = _letter([
        "Paragraph one about You spent more time scrolling Twitter than writing code.",
        "Paragraph two with Block social media until lunch on three weekdays.",
        "Paragraph three.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_grounded({"grounded": True})
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    assert any("4 paragraphs" in i for i in issues)


@pytest.mark.asyncio
async def test_missing_uncomfortable_truth_flagged():
    letter = _letter([
        "Overall pattern paragraph with no hard truths.",
        "Working stuff paragraph.",
        "Not working paragraph but vague, no specifics.",
        "Next week: Block social media until lunch on three weekdays.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_grounded({"grounded": True})
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    assert any("uncomfortable_truth" in i for i in issues)


@pytest.mark.asyncio
async def test_missing_next_week_action_flagged():
    letter = _letter([
        "Overall paragraph.",
        "Working paragraph.",
        "Not working: You spent more time scrolling Twitter than writing code.",
        "Final paragraph that forgets to give a concrete action.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_grounded({"grounded": True})
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    assert any("next_week_action" in i for i in issues)


@pytest.mark.asyncio
async def test_groundedness_check_failure_is_best_effort():
    """If the LLM groundedness call times out, deterministic checks still run and
    the function does not raise."""
    letter = _letter([
        "Paragraph one with You spent more time scrolling Twitter than writing code.",
        "Paragraph two.",
        "Paragraph three.",
        "Paragraph four: Block social media until lunch on three weekdays.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    # Deterministic checks all pass; groundedness skipped silently
    assert issues == []


@pytest.mark.asyncio
async def test_empty_letter_flagged():
    issues = await _check_weekly_letter("", ANALYSIS)
    assert issues == ["Letter is empty."]


@pytest.mark.asyncio
async def test_llm_reports_ungrounded():
    """If the LLM says the letter contains info not in the analysis, that's flagged."""
    letter = _letter([
        "Paragraph one with You spent more time scrolling Twitter than writing code.",
        "Paragraph two invents a new fact: you fired two employees this week.",
        "Paragraph three.",
        "Paragraph four: Block social media until lunch on three weekdays.",
    ])
    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_grounded({
                "grounded": False,
                "reason": "claims employee firings not present in analysis",
            })
        )
        issues = await _check_weekly_letter(letter, ANALYSIS)
    assert any("not in the analysis" in i for i in issues)

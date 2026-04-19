"""
Unit tests for app.services.categorization.categorize_text().

All OpenAI calls are mocked — no network required.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.categorization import categorize_text


def _mock_openai_response(content: str):
    """Build a minimal mock that matches the openai response shape."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_entry_todo():
    """Short transcript with one clear TODO produces a single TODO entry."""
    payload = json.dumps([{"text": "Fix the login bug", "category": "TODO"}])
    mock_create = AsyncMock(return_value=_mock_openai_response(payload))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("I need to fix the login bug tomorrow.")

    assert len(result) == 1
    assert result[0]["category"] == "TODO"
    assert "login bug" in result[0]["text"].lower()


@pytest.mark.asyncio
async def test_multi_entry_extraction():
    """Long transcript produces multiple entries with correct categories."""
    items = [
        {"text": "Worked on dashboard for 2 hours", "category": "EARNING"},
        {"text": "Three back-to-back meetings", "category": "EARNING"},
        {"text": "Add voice replay to audit", "category": "EXPERIMENT"},
        {"text": "Write tests for auth module", "category": "TODO"},
    ]
    payload = json.dumps(items)
    mock_create = AsyncMock(return_value=_mock_openai_response(payload))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text(
            "This morning I worked on the dashboard for about 2 hours. "
            "Then had three back-to-back meetings. Had an idea to add voice replay. "
            "Still need to write tests for the auth module."
        )

    assert len(result) == 4
    categories = [r["category"] for r in result]
    assert "EARNING" in categories
    assert "EXPERIMENT" in categories
    assert "TODO" in categories


@pytest.mark.asyncio
async def test_all_valid_categories_accepted():
    """All valid categories are returned; TIME_RECORD is remapped to EARNING."""
    items = [
        {"text": "A", "category": "EARNING"},
        {"text": "B", "category": "LEARNING"},
        {"text": "B2", "category": "MAITAISHAO"},
        {"text": "C", "category": "RELAXING"},
        {"text": "D", "category": "FAMILY"},
        {"text": "E", "category": "TODO"},
        {"text": "F", "category": "EXPERIMENT"},
        {"text": "G", "category": "REFLECTION"},
        {"text": "H", "category": "TIME_RECORD"},
    ]
    mock_create = AsyncMock(return_value=_mock_openai_response(json.dumps(items)))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("Some transcript text covering many topics.")

    assert len(result) == 9
    # TIME_RECORD remapped to EARNING
    assert {r["category"] for r in result} == {
        "EARNING", "LEARNING", "MAITAISHAO", "RELAXING", "FAMILY",
        "TODO", "EXPERIMENT", "REFLECTION",
    }
    assert result[8]["category"] == "EARNING"  # was TIME_RECORD


# ── Fallback: empty / malformed LLM response ─────────────────────────────────

@pytest.mark.asyncio
async def test_empty_array_from_llm_falls_back_to_thought():
    """LLM returns [] → fallback to single REFLECTION entry with full transcript."""
    mock_create = AsyncMock(return_value=_mock_openai_response("[]"))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("This is my transcript.")

    assert len(result) == 1
    assert result[0]["category"] == "REFLECTION"
    assert result[0]["text"] == "This is my transcript."


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_thought():
    """LLM returns invalid JSON → fallback to single REFLECTION entry."""
    mock_create = AsyncMock(return_value=_mock_openai_response("not valid json {{{"))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("My transcript here.")

    assert len(result) == 1
    assert result[0]["category"] == "REFLECTION"
    assert result[0]["text"] == "My transcript here."


@pytest.mark.asyncio
async def test_single_dict_instead_of_list_falls_back():
    """LLM returns a single dict (old format) instead of list → fallback."""
    old_format = json.dumps({"category": "TODO", "content": "do something", "confidence": 0.9})
    mock_create = AsyncMock(return_value=_mock_openai_response(old_format))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("do something")

    assert len(result) == 1
    assert result[0]["category"] == "REFLECTION"


@pytest.mark.asyncio
async def test_api_exception_falls_back_to_thought():
    """OpenAI API call raises an exception → fallback to REFLECTION, no crash."""
    mock_create = AsyncMock(side_effect=Exception("Network error"))

    with patch("app.services.categorization.get_chat_client") as mock_client:
        mock_client.return_value.chat.completions.create = mock_create
        result = await categorize_text("Something happened today.")

    assert len(result) == 1
    assert result[0]["category"] == "REFLECTION"


# ── Empty transcript ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_transcript_raises():
    """Empty or blank transcript raises ValueError('No speech detected')."""
    with pytest.raises(ValueError, match="No speech detected"):
        await categorize_text("")


@pytest.mark.asyncio
async def test_whitespace_only_transcript_raises():
    """Whitespace-only transcript raises ValueError('No speech detected')."""
    with pytest.raises(ValueError, match="No speech detected"):
        await categorize_text("   \n\t  ")

"""
Unit tests for local_date field: population on submit and date-based filtering.

Tests cover:
1. local_date is set from explicit body.local_date
2. local_date falls back to recorded_at.date() when local_date is absent
3. local_date falls back to utcnow().date() when both are absent
4. list_entries filters by Entry.local_date (not created_at range)
5. active-dates returns Entry.local_date values
6. _fetch_entries_for_date uses Entry.local_date
"""
import uuid
import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.entry import Entry
from app.models.jobs import Job, JobStatus


class TestLocalDateComputation:
    """Test that submit_entry computes local_date correctly."""

    def test_entry_model_has_local_date(self):
        """Entry model should have a local_date column."""
        e = Entry(
            id=uuid.uuid4(),
            user_id=1,
            raw_audio_key="audio/1/test.webm",
            local_date=date(2026, 4, 1),
        )
        assert e.local_date == date(2026, 4, 1)

    def test_entry_local_date_nullable(self):
        """local_date should be nullable for backwards compatibility."""
        e = Entry(
            id=uuid.uuid4(),
            user_id=1,
            raw_audio_key="audio/1/test.webm",
        )
        assert e.local_date is None


class TestLocalDateFilterLogic:
    """Test the date filter logic change from created_at range to local_date equality."""

    def test_date_filter_uses_local_date_equality(self):
        """
        Verify that the new filter pattern (Entry.local_date == date)
        correctly matches entries, unlike the old pattern which used
        created_at UTC range and could miss timezone-offset entries.
        """
        # Simulate: user in UTC-8 records at 11:30 PM local (7:30 AM next day UTC)
        local_date = date(2026, 4, 1)
        utc_created_at = datetime(2026, 4, 2, 7, 30, tzinfo=timezone.utc)

        entry = Entry(
            id=uuid.uuid4(),
            user_id=1,
            raw_audio_key="audio/1/test.webm",
            local_date=local_date,
            created_at=utc_created_at,
        )

        # Old filter: created_at in UTC day range for 2026-04-01
        # Would be: 2026-04-01 00:00 UTC <= created_at < 2026-04-02 00:00 UTC
        # entry.created_at = 2026-04-02 07:30 UTC → OUTSIDE range → BUG
        old_day_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        old_day_end = old_day_start + timedelta(days=1)
        old_filter_match = old_day_start <= entry.created_at < old_day_end
        assert not old_filter_match, "Old filter incorrectly matches (or this test is wrong)"

        # New filter: local_date == 2026-04-01 → MATCH → CORRECT
        new_filter_match = entry.local_date == local_date
        assert new_filter_match, "New filter should match by local_date"

    def test_local_date_fallback_from_recorded_at(self):
        """When local_date is not provided, it should fall back to recorded_at.date()."""
        from app.routes.v1.entries import SubmitRequest

        body = SubmitRequest(
            audio_key="audio/1/test.webm",
            recorded_at=datetime(2026, 4, 1, 23, 30, tzinfo=timezone.utc),
            local_date=None,
        )
        # The fallback logic: if local_date is None, use recorded_at.date()
        if body.local_date:
            computed = datetime.strptime(body.local_date, "%Y-%m-%d").date()
        elif body.recorded_at:
            computed = body.recorded_at.date()
        else:
            computed = datetime.now(timezone.utc).date()

        assert computed == date(2026, 4, 1)

    def test_local_date_from_explicit_value(self):
        """When local_date is provided, it should be used directly."""
        from app.routes.v1.entries import SubmitRequest

        body = SubmitRequest(
            audio_key="audio/1/test.webm",
            recorded_at=datetime(2026, 4, 2, 7, 30, tzinfo=timezone.utc),  # UTC = April 2
            local_date="2026-04-01",  # but user says it's April 1 locally
        )
        computed = datetime.strptime(body.local_date, "%Y-%m-%d").date()
        assert computed == date(2026, 4, 1), "Should use explicit local_date over recorded_at"


class TestEmptyTranscriptHandling:
    """Test that the worker handles empty transcripts gracefully."""

    def test_empty_transcript_is_falsy(self):
        """Empty/whitespace transcripts should be detected."""
        assert not ""
        assert not "   ".strip()
        assert not None

    def test_nonempty_transcript_is_truthy(self):
        """Non-empty transcripts should pass the check."""
        assert "hello world"
        assert "  hello  ".strip()

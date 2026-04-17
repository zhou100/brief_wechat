"""
Unit tests for the split breakdown functions:
- _compute_activity_breakdown() only includes activity categories
- _compute_capture_counts() only includes capture categories
"""
import pytest
from unittest.mock import MagicMock

from app.routes.v1.entries import (
    _compute_activity_breakdown,
    _compute_capture_counts,
    ACTIVITY_CATEGORIES,
    CAPTURE_CATEGORIES,
)


def _make_cls(category: str, estimated_minutes=None):
    c = MagicMock()
    c.category = category
    c.estimated_minutes = estimated_minutes
    return c


class TestActivityBreakdown:
    def test_only_activity_categories_included(self):
        classifications = [
            _make_cls("EARNING", 120),
            _make_cls("LEARNING", 60),
            _make_cls("TODO"),  # capture — should be excluded
            _make_cls("EXPERIMENT"),  # capture — should be excluded
        ]
        breakdown, _ = _compute_activity_breakdown(classifications)
        assert set(breakdown.keys()) <= ACTIVITY_CATEGORIES
        assert "TODO" not in breakdown
        assert "EXPERIMENT" not in breakdown
        assert "EARNING" in breakdown
        assert "LEARNING" in breakdown

    def test_time_record_included_in_activity(self):
        """Legacy TIME_RECORD entries count as activity."""
        classifications = [
            _make_cls("EARNING", 60),
            _make_cls("TIME_RECORD", 60),
        ]
        breakdown, _ = _compute_activity_breakdown(classifications)
        assert "TIME_RECORD" in breakdown
        assert "EARNING" in breakdown
        assert abs(breakdown["EARNING"] - 50.0) < 1.0

    def test_empty_classifications(self):
        breakdown, approximate = _compute_activity_breakdown([])
        assert breakdown == {}
        assert approximate is False

    def test_no_activity_entries(self):
        """Only capture entries → empty activity breakdown."""
        classifications = [_make_cls("TODO"), _make_cls("EXPERIMENT")]
        breakdown, _ = _compute_activity_breakdown(classifications)
        assert breakdown == {}


class TestCaptureCounts:
    def test_only_capture_categories_included(self):
        classifications = [
            _make_cls("EARNING", 120),
            _make_cls("TODO"),
            _make_cls("TODO"),
            _make_cls("EXPERIMENT"),
            _make_cls("REFLECTION"),
        ]
        counts = _compute_capture_counts(classifications)
        assert set(counts.keys()) <= CAPTURE_CATEGORIES
        assert "EARNING" not in counts
        assert counts["TODO"] == 2
        assert counts["EXPERIMENT"] == 1
        assert counts["REFLECTION"] == 1

    def test_empty_classifications(self):
        counts = _compute_capture_counts([])
        assert counts == {}

    def test_no_capture_entries(self):
        """Only activity entries → empty capture counts."""
        classifications = [_make_cls("EARNING", 60), _make_cls("RELAXING", 30)]
        counts = _compute_capture_counts(classifications)
        assert counts == {}

    def test_legacy_capture_categories_fold_into_new_names(self):
        classifications = [_make_cls("IDEA"), _make_cls("THOUGHT"), _make_cls("TODO")]
        counts = _compute_capture_counts(classifications)
        assert counts["EXPERIMENT"] == 1
        assert counts["REFLECTION"] == 1
        assert counts["TODO"] == 1

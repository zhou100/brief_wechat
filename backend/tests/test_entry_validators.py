"""Unit tests for Pydantic validators on CategoryItem."""
import pytest
from pydantic import ValidationError


def test_valid_category_accepted():
    from app.routes.v1.entries import CategoryItem
    for cat in ("EARNING", "LEARNING", "RELAXING", "FAMILY", "TODO", "EXPERIMENT", "REFLECTION", "TIME_RECORD"):
        item = CategoryItem(text="test", category=cat)
        assert item.category == cat


def test_legacy_capture_categories_normalized():
    from app.routes.v1.entries import CategoryItem
    assert CategoryItem(text="test", category="IDEA").category == "EXPERIMENT"
    assert CategoryItem(text="test", category="THOUGHT").category == "REFLECTION"


def test_invalid_category_rejected():
    from app.routes.v1.entries import CategoryItem
    with pytest.raises(ValidationError, match="category must be one of"):
        CategoryItem(text="test", category="INVALID")


def test_estimated_minutes_within_bounds():
    from app.routes.v1.entries import CategoryItem
    item = CategoryItem(text="test", category="TODO", estimated_minutes=120)
    assert item.estimated_minutes == 120


def test_estimated_minutes_zero_accepted():
    from app.routes.v1.entries import CategoryItem
    item = CategoryItem(text="test", category="TODO", estimated_minutes=0)
    assert item.estimated_minutes == 0


def test_estimated_minutes_max_accepted():
    from app.routes.v1.entries import CategoryItem
    item = CategoryItem(text="test", category="TODO", estimated_minutes=1440)
    assert item.estimated_minutes == 1440


def test_estimated_minutes_over_max_rejected():
    from app.routes.v1.entries import CategoryItem
    with pytest.raises(ValidationError, match="estimated_minutes must be 0-1440"):
        CategoryItem(text="test", category="TODO", estimated_minutes=1441)


def test_estimated_minutes_negative_rejected():
    from app.routes.v1.entries import CategoryItem
    with pytest.raises(ValidationError, match="estimated_minutes must be 0-1440"):
        CategoryItem(text="test", category="TODO", estimated_minutes=-1)


def test_estimated_minutes_none_accepted():
    from app.routes.v1.entries import CategoryItem
    item = CategoryItem(text="test", category="TODO", estimated_minutes=None)
    assert item.estimated_minutes is None

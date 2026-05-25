"""Pure-Python tests for wardrobe constants and helpers (no HA required)."""

from __future__ import annotations

import pytest

from custom_components.wardrobe.const import (
    CATEGORY_ICONS,
    DEFAULT_LAUNDRY_TYPE,
    LAUNDRY_TYPES,
    STATE_CYCLE,
    STATES,
    STORAGE_VERSION,
    LaundryType,
    WardrobeState,
    next_state,
)


def test_states_match_enum_values() -> None:
    """STATES should be the values of WardrobeState, in the spec'd order."""
    assert STATES == [s.value for s in WardrobeState]
    assert STATES == ["clean", "worn", "laundry"]


def test_state_cycle_progression() -> None:
    """next_state should walk clean → worn → laundry → clean."""
    assert next_state("clean") == "worn"
    assert next_state("worn") == "laundry"
    assert next_state("laundry") == "clean"


def test_state_cycle_returns_to_start() -> None:
    """Three applications of next_state should land back on the start state."""
    state = "clean"
    for _ in range(3):
        state = next_state(state)
    assert state == "clean"


def test_state_cycle_table_matches_helper() -> None:
    """STATE_CYCLE dict and next_state should agree."""
    for current, expected in STATE_CYCLE.items():
        assert next_state(current) == expected


def test_next_state_raises_for_unknown() -> None:
    """Unknown states should raise — there is no implicit fallback."""
    with pytest.raises(KeyError):
        next_state("not-a-state")


def test_category_icons_are_mdi() -> None:
    """Every category icon should be an MDI icon string."""
    assert CATEGORY_ICONS
    for category, icon in CATEGORY_ICONS.items():
        assert isinstance(category, str) and category
        assert icon.startswith("mdi:"), f"{category!r} icon {icon!r} is not an MDI icon"


def test_category_icons_includes_baseline_categories() -> None:
    """The 'other' fallback must exist; common categories should be present."""
    assert "other" in CATEGORY_ICONS
    for required in ("shirt", "pants", "shoes", "jacket"):
        assert required in CATEGORY_ICONS, f"missing baseline category {required!r}"


def test_storage_version_is_two() -> None:
    """v1.1 ships storage v2 — guards against accidental rollback."""
    assert STORAGE_VERSION == 2


def test_laundry_types_match_enum_values() -> None:
    """LAUNDRY_TYPES should be the values of LaundryType, in spec'd order."""
    assert LAUNDRY_TYPES == [lt.value for lt in LaundryType]
    assert LAUNDRY_TYPES == ["dark", "light", "color", "delicates"]


def test_default_laundry_type_is_a_valid_option() -> None:
    """The default value used in the config flow must exist in LAUNDRY_TYPES."""
    assert DEFAULT_LAUNDRY_TYPE in LAUNDRY_TYPES

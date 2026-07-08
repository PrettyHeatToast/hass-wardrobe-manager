"""Pure-Python tests for the state-cycle helpers in const.py."""

from __future__ import annotations

from custom_components.wardrobe.const import (
    ALL_STATES,
    CORE_CYCLE,
    DIRTY_STATES,
    EXTRA_STATES,
    build_cycle,
    next_state_in,
    selectable_states,
)


def test_default_cycle_is_core_three() -> None:
    assert build_cycle() == ["clean", "worn", "laundry"]
    assert build_cycle([]) == CORE_CYCLE


def test_cycle_wraps_around() -> None:
    cycle = build_cycle()
    assert next_state_in(cycle, "clean") == "worn"
    assert next_state_in(cycle, "worn") == "laundry"
    assert next_state_in(cycle, "laundry") == "clean"


def test_pipeline_extras_join_in_canonical_order() -> None:
    # Order of the input list doesn't matter; the pipeline order does.
    cycle = build_cycle(["drying", "washing"])
    assert cycle == ["clean", "worn", "laundry", "washing", "drying"]
    assert next_state_in(cycle, "laundry") == "washing"
    assert next_state_in(cycle, "drying") == "clean"


def test_full_pipeline_cycle() -> None:
    cycle = build_cycle(["washing", "drying", "ironing"])
    assert cycle == ["clean", "worn", "laundry", "washing", "drying", "ironing"]
    assert next_state_in(cycle, "ironing") == "clean"


def test_parked_states_never_join_the_cycle() -> None:
    cycle = build_cycle(["repair", "storage"])
    assert cycle == CORE_CYCLE
    # Cycling from a parked state returns to clean.
    assert next_state_in(cycle, "repair") == "clean"
    assert next_state_in(cycle, "storage") == "clean"


def test_selectable_states_include_parked_extras() -> None:
    opts = selectable_states(["washing", "storage"])
    assert opts == ["clean", "worn", "laundry", "washing", "storage"]


def test_state_taxonomy_is_consistent() -> None:
    assert set(CORE_CYCLE) | set(EXTRA_STATES) == set(ALL_STATES)
    assert "worn" not in DIRTY_STATES
    assert "laundry" in DIRTY_STATES
    assert "washing" in DIRTY_STATES

"""Tests for the garment state machine — targeting 100% branch coverage."""

from __future__ import annotations

import pytest

from custom_components.wardrobe_manager.const import GarmentState, ScannerRole
from custom_components.wardrobe_manager.state_machine import (
    GarmentData,
    WashCycle,
    transition,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_garment(
    state: GarmentState = GarmentState.CLEAN,
    **kwargs,
) -> GarmentData:
    defaults = {
        "tag_id": "test123",
        "name": "Test Shirt",
        "category": "shirt",
        "color": "white",
    }
    defaults.update(kwargs)
    return GarmentData(garment_state=state, **defaults)


# ── Valid transitions ────────────────────────────────────────────────────────


class TestValidTransitions:
    """Test all valid state transitions from the transition table."""

    def test_closet_clean_to_worn(self) -> None:
        g = _make_garment(GarmentState.CLEAN)
        result = transition(g, ScannerRole.CLOSET, "nfc_closet")
        assert result is not None
        assert result.garment_state == GarmentState.WORN
        assert result.wear_count_since_wash == 1
        assert result.total_wear_count == 1
        assert result.last_worn is not None
        assert result.last_scanned_at == "nfc_closet"

    def test_closet_worn_to_clean(self) -> None:
        g = _make_garment(GarmentState.WORN, wear_count_since_wash=2)
        result = transition(g, ScannerRole.CLOSET, "nfc_closet")
        assert result is not None
        assert result.garment_state == GarmentState.CLEAN
        # Wear count stays — it's a manual return, not a wash
        assert result.wear_count_since_wash == 2

    def test_closet_in_laundry_bin_to_clean(self) -> None:
        g = _make_garment(GarmentState.IN_LAUNDRY_BIN)
        result = transition(g, ScannerRole.CLOSET, "nfc_closet")
        assert result is not None
        assert result.garment_state == GarmentState.CLEAN

    def test_closet_drying_to_clean(self) -> None:
        g = _make_garment(GarmentState.DRYING)
        result = transition(g, ScannerRole.CLOSET, "nfc_closet")
        assert result is not None
        assert result.garment_state == GarmentState.CLEAN

    def test_closet_needs_ironing_to_clean(self) -> None:
        g = _make_garment(GarmentState.NEEDS_IRONING)
        result = transition(g, ScannerRole.CLOSET, "nfc_closet")
        assert result is not None
        assert result.garment_state == GarmentState.CLEAN

    def test_laundry_bin_worn_to_in_laundry_bin(self) -> None:
        g = _make_garment(GarmentState.WORN)
        result = transition(g, ScannerRole.LAUNDRY_BIN, "nfc_bin")
        assert result is not None
        assert result.garment_state == GarmentState.IN_LAUNDRY_BIN
        assert result.last_scanned_at == "nfc_bin"

    def test_washer_in_laundry_bin_to_washing(self) -> None:
        g = _make_garment(
            GarmentState.IN_LAUNDRY_BIN,
            wear_count_since_wash=5,
            total_wear_count=10,
        )
        result = transition(g, ScannerRole.WASHER, "nfc_washer")
        assert result is not None
        assert result.garment_state == GarmentState.WASHING
        assert result.wear_count_since_wash == 0
        assert result.total_wear_count == 10  # unchanged
        assert result.last_washed is not None
        assert len(result.wash_cycles) == 1
        assert result.wash_cycles[0].method == "machine"

    def test_dryer_washing_to_drying(self) -> None:
        g = _make_garment(GarmentState.WASHING)
        result = transition(g, ScannerRole.DRYER, "nfc_dryer")
        assert result is not None
        assert result.garment_state == GarmentState.DRYING

    def test_ironing_drying_to_needs_ironing(self) -> None:
        g = _make_garment(GarmentState.DRYING)
        result = transition(g, ScannerRole.IRONING, "nfc_iron")
        assert result is not None
        assert result.garment_state == GarmentState.NEEDS_IRONING

    def test_ironing_washing_to_needs_ironing(self) -> None:
        g = _make_garment(GarmentState.WASHING)
        result = transition(g, ScannerRole.IRONING, "nfc_iron")
        assert result is not None
        assert result.garment_state == GarmentState.NEEDS_IRONING


# ── Invalid transitions ──────────────────────────────────────────────────────


class TestInvalidTransitions:
    """Test transitions that should be rejected (return None)."""

    @pytest.mark.parametrize(
        ("scanner_role", "state"),
        [
            (ScannerRole.LAUNDRY_BIN, GarmentState.CLEAN),
            (ScannerRole.LAUNDRY_BIN, GarmentState.WASHING),
            (ScannerRole.LAUNDRY_BIN, GarmentState.DRYING),
            (ScannerRole.LAUNDRY_BIN, GarmentState.NEEDS_IRONING),
            (ScannerRole.LAUNDRY_BIN, GarmentState.IN_LAUNDRY_BIN),
            (ScannerRole.WASHER, GarmentState.CLEAN),
            (ScannerRole.WASHER, GarmentState.WORN),
            (ScannerRole.WASHER, GarmentState.WASHING),
            (ScannerRole.WASHER, GarmentState.DRYING),
            (ScannerRole.WASHER, GarmentState.NEEDS_IRONING),
            (ScannerRole.DRYER, GarmentState.CLEAN),
            (ScannerRole.DRYER, GarmentState.WORN),
            (ScannerRole.DRYER, GarmentState.IN_LAUNDRY_BIN),
            (ScannerRole.DRYER, GarmentState.DRYING),
            (ScannerRole.DRYER, GarmentState.NEEDS_IRONING),
            (ScannerRole.IRONING, GarmentState.CLEAN),
            (ScannerRole.IRONING, GarmentState.WORN),
            (ScannerRole.IRONING, GarmentState.IN_LAUNDRY_BIN),
            (ScannerRole.IRONING, GarmentState.NEEDS_IRONING),
            (ScannerRole.CLOSET, GarmentState.WASHING),
        ],
    )
    def test_invalid_transition_returns_none(
        self, scanner_role: ScannerRole, state: GarmentState
    ) -> None:
        g = _make_garment(state)
        result = transition(g, scanner_role, "scanner_x")
        assert result is None

    def test_garment_unchanged_on_invalid(self) -> None:
        g = _make_garment(GarmentState.CLEAN, wear_count_since_wash=2)
        transition(g, ScannerRole.WASHER, "nfc_washer")
        # Garment should not be mutated on invalid transition
        assert g.garment_state == GarmentState.CLEAN
        assert g.wear_count_since_wash == 2


# ── Wear count tracking ─────────────────────────────────────────────────────


class TestWearCountTracking:
    """Test wear count increments and resets."""

    def test_multiple_wears_increment(self) -> None:
        g = _make_garment(GarmentState.CLEAN)
        transition(g, ScannerRole.CLOSET, "nfc_closet")  # → worn (1)
        assert g.wear_count_since_wash == 1

        # Return to closet (clean) then wear again
        transition(g, ScannerRole.CLOSET, "nfc_closet")  # → clean
        transition(g, ScannerRole.CLOSET, "nfc_closet")  # → worn (2)
        assert g.wear_count_since_wash == 2
        assert g.total_wear_count == 2

    def test_wash_resets_wear_count(self) -> None:
        g = _make_garment(
            GarmentState.IN_LAUNDRY_BIN,
            wear_count_since_wash=5,
            total_wear_count=20,
        )
        transition(g, ScannerRole.WASHER, "nfc_washer")
        assert g.wear_count_since_wash == 0
        assert g.total_wear_count == 20  # total unchanged


# ── Full lifecycle ───────────────────────────────────────────────────────────


class TestFullLifecycle:
    """Test complete garment lifecycle paths."""

    def test_full_wash_cycle_with_dryer(self) -> None:
        g = _make_garment(GarmentState.CLEAN)
        assert transition(g, ScannerRole.CLOSET, "c") is not None  # → worn
        assert transition(g, ScannerRole.LAUNDRY_BIN, "b") is not None  # → in_laundry_bin
        assert transition(g, ScannerRole.WASHER, "w") is not None  # → washing
        assert transition(g, ScannerRole.DRYER, "d") is not None  # → drying
        assert transition(g, ScannerRole.CLOSET, "c") is not None  # → clean
        assert g.garment_state == GarmentState.CLEAN
        assert len(g.wash_cycles) == 1

    def test_full_wash_cycle_with_ironing(self) -> None:
        g = _make_garment(GarmentState.CLEAN)
        transition(g, ScannerRole.CLOSET, "c")  # → worn
        transition(g, ScannerRole.LAUNDRY_BIN, "b")  # → in_laundry_bin
        transition(g, ScannerRole.WASHER, "w")  # → washing
        transition(g, ScannerRole.IRONING, "i")  # → needs_ironing
        transition(g, ScannerRole.CLOSET, "c")  # → clean
        assert g.garment_state == GarmentState.CLEAN

    def test_full_wash_cycle_dryer_then_ironing(self) -> None:
        g = _make_garment(GarmentState.CLEAN)
        transition(g, ScannerRole.CLOSET, "c")
        transition(g, ScannerRole.LAUNDRY_BIN, "b")
        transition(g, ScannerRole.WASHER, "w")
        transition(g, ScannerRole.DRYER, "d")
        transition(g, ScannerRole.IRONING, "i")
        transition(g, ScannerRole.CLOSET, "c")
        assert g.garment_state == GarmentState.CLEAN


# ── Serialization ────────────────────────────────────────────────────────────


class TestSerialization:
    """Test to_dict / from_dict round-trip."""

    def test_round_trip(self) -> None:
        g = _make_garment(
            GarmentState.WORN,
            wear_count_since_wash=3,
            total_wear_count=10,
            last_worn="2026-02-25T08:30:00+00:00",
            last_washed="2026-02-20T11:00:00+00:00",
            last_scanned_at="nfc_closet",
        )
        g.wash_cycles.append(
            WashCycle(timestamp="2026-02-20T11:00:00+00:00", method="machine_30")
        )

        data = g.to_dict()
        restored = GarmentData.from_dict("test123", data)

        assert restored.tag_id == g.tag_id
        assert restored.name == g.name
        assert restored.garment_state == g.garment_state
        assert restored.wear_count_since_wash == g.wear_count_since_wash
        assert restored.total_wear_count == g.total_wear_count
        assert restored.last_worn == g.last_worn
        assert restored.last_washed == g.last_washed
        assert restored.last_scanned_at == g.last_scanned_at
        assert len(restored.wash_cycles) == 1
        assert restored.wash_cycles[0].method == "machine_30"

    def test_from_dict_defaults(self) -> None:
        minimal = {"name": "Shirt", "category": "shirt"}
        g = GarmentData.from_dict("tag1", minimal)
        assert g.garment_state == GarmentState.CLEAN
        assert g.wear_count_since_wash == 0
        assert g.color == ""
        assert g.wash_cycles == []

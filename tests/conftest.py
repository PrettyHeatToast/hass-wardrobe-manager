"""Fixtures for Wardrobe Manager tests."""

from __future__ import annotations

import pytest

from custom_components.wardrobe_manager.const import GarmentState
from custom_components.wardrobe_manager.state_machine import GarmentData


@pytest.fixture
def sample_garment() -> GarmentData:
    """Return a sample garment for testing."""
    return GarmentData(
        tag_id="abc123",
        name="Blue Oxford Shirt",
        category="shirt",
        color="blue",
        needs_washing_threshold=3,
    )


@pytest.fixture
def worn_garment() -> GarmentData:
    """Return a garment in 'worn' state."""
    return GarmentData(
        tag_id="def456",
        name="Black Jeans",
        category="jeans",
        color="black",
        garment_state=GarmentState.WORN,
        wear_count_since_wash=1,
        total_wear_count=5,
        needs_washing_threshold=3,
    )

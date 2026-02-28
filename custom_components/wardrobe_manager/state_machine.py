"""Pure state machine for garment transitions — no Home Assistant dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .const import GarmentState, ScannerRole

# Valid transitions: (scanner_role, from_state) → to_state
TRANSITIONS: dict[tuple[ScannerRole, GarmentState], GarmentState] = {
    (ScannerRole.CLOSET, GarmentState.CLEAN): GarmentState.WORN,
    (ScannerRole.CLOSET, GarmentState.WORN): GarmentState.CLEAN,
    (ScannerRole.CLOSET, GarmentState.IN_LAUNDRY_BIN): GarmentState.CLEAN,
    (ScannerRole.CLOSET, GarmentState.DRYING): GarmentState.CLEAN,
    (ScannerRole.CLOSET, GarmentState.NEEDS_IRONING): GarmentState.CLEAN,
    (ScannerRole.LAUNDRY_BIN, GarmentState.WORN): GarmentState.IN_LAUNDRY_BIN,
    (ScannerRole.WASHER, GarmentState.IN_LAUNDRY_BIN): GarmentState.WASHING,
    (ScannerRole.DRYER, GarmentState.WASHING): GarmentState.DRYING,
    (ScannerRole.IRONING, GarmentState.DRYING): GarmentState.NEEDS_IRONING,
    (ScannerRole.IRONING, GarmentState.WASHING): GarmentState.NEEDS_IRONING,
}


@dataclass
class WashCycle:
    """A recorded wash event."""

    timestamp: str
    method: str


@dataclass
class GarmentData:
    """In-memory representation of a garment."""

    tag_id: str
    name: str
    category: str
    color: str
    garment_state: GarmentState = GarmentState.CLEAN
    wear_count_since_wash: int = 0
    total_wear_count: int = 0
    needs_washing_threshold: int = 3
    last_worn: str | None = None
    last_washed: str | None = None
    last_scanned_at: str | None = None
    wash_cycles: list[WashCycle] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a dictionary for storage."""
        return {
            "name": self.name,
            "category": self.category,
            "color": self.color,
            "garment_state": self.garment_state.value,
            "wear_count_since_wash": self.wear_count_since_wash,
            "total_wear_count": self.total_wear_count,
            "needs_washing_threshold": self.needs_washing_threshold,
            "last_worn": self.last_worn,
            "last_washed": self.last_washed,
            "last_scanned_at": self.last_scanned_at,
            "wash_cycles": [
                {"timestamp": wc.timestamp, "method": wc.method}
                for wc in self.wash_cycles
            ],
        }

    @classmethod
    def from_dict(cls, tag_id: str, data: dict) -> GarmentData:
        """Deserialize from a storage dictionary."""
        return cls(
            tag_id=tag_id,
            name=data["name"],
            category=data["category"],
            color=data.get("color", ""),
            garment_state=GarmentState(data.get("garment_state", "clean")),
            wear_count_since_wash=data.get("wear_count_since_wash", 0),
            total_wear_count=data.get("total_wear_count", 0),
            needs_washing_threshold=data.get("needs_washing_threshold", 3),
            last_worn=data.get("last_worn"),
            last_washed=data.get("last_washed"),
            last_scanned_at=data.get("last_scanned_at"),
            wash_cycles=[
                WashCycle(timestamp=wc["timestamp"], method=wc["method"])
                for wc in data.get("wash_cycles", [])
            ],
        )


def transition(
    garment: GarmentData,
    scanner_role: ScannerRole,
    scanner_id: str,
) -> GarmentData | None:
    """Apply a state transition. Returns updated garment or None if invalid.

    This function mutates and returns the garment if the transition is valid.
    Returns None if the transition is not allowed.
    """
    key = (scanner_role, garment.garment_state)
    new_state = TRANSITIONS.get(key)

    if new_state is None:
        return None

    now = datetime.now(timezone.utc).isoformat()

    garment.garment_state = new_state
    garment.last_scanned_at = scanner_id

    # Track wear events
    if new_state == GarmentState.WORN:
        garment.wear_count_since_wash += 1
        garment.total_wear_count += 1
        garment.last_worn = now

    # Track wash events — entering washing resets wear count
    if new_state == GarmentState.WASHING:
        garment.wear_count_since_wash = 0
        garment.last_washed = now
        garment.wash_cycles.append(WashCycle(timestamp=now, method="machine"))

    # Returning to clean from washer path (via closet after drying/ironing)
    # is already handled by the transition table; last_washed is set at washing.
    # If going directly back to closet from worn/in_laundry_bin, it's a manual
    # return — no wash event recorded.

    return garment

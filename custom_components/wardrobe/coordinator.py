"""Coordinator for the Wardrobe integration — shared state and persistence."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_LAST_WORN_AT,
    ATTR_STATE_CHANGED_AT,
    ATTR_WEAR_COUNT_TOTAL,
    ATTR_WEARS_SINCE_WASH,
    CONF_ITEM_NAME,
    DEFAULT_STATE,
    DOMAIN,
    EVENT_STATE_CHANGED,
    STATES,
    STORAGE_KEY,
    STORAGE_VERSION,
    WardrobeState,
    next_state,
)

_LOGGER = logging.getLogger(__name__)


class WardrobeRecord(TypedDict):
    """Per-entry state persisted in storage."""

    state: str
    wears_since_wash: int
    wear_count_total: int
    last_worn_at: str | None
    state_changed_at: str | None


def _new_record(*, state: str = DEFAULT_STATE) -> WardrobeRecord:
    """Return a fully-populated default record for a given state."""
    return {
        "state": state,
        "wears_since_wash": 0,
        "wear_count_total": 0,
        "last_worn_at": None,
        "state_changed_at": None,
    }


def _coerce_record(value: Any) -> WardrobeRecord:
    """Coerce a stored value into a complete WardrobeRecord.

    Defensive merge so half-populated rows (hand edits, future minor-version
    skew) don't KeyError downstream.
    """
    base = _new_record()
    if isinstance(value, dict):
        state = value.get("state", DEFAULT_STATE)
        if state not in STATES:
            state = DEFAULT_STATE
        base["state"] = state
        for key in ("wears_since_wash", "wear_count_total"):
            v = value.get(key)
            if isinstance(v, int) and v >= 0:
                base[key] = v
        for key in ("last_worn_at", "state_changed_at"):
            v = value.get(key)
            if isinstance(v, str) or v is None:
                base[key] = v
    return base


class WardrobeStore(Store[dict[str, Any]]):
    """Store subclass that handles v1 → v2 migration."""

    async def async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Lift v1 ``{entry_id: state_string}`` rows into v2 records."""
        if old_major_version == 1:
            entries_old = old_data.get("entries", {}) or {}
            entries_new: dict[str, WardrobeRecord] = {}
            for entry_id, value in entries_old.items():
                if isinstance(value, str):
                    if value not in STATES:
                        _LOGGER.warning(
                            "Migrating unknown wardrobe state %r for %s → %s",
                            value,
                            entry_id,
                            DEFAULT_STATE,
                        )
                        state = DEFAULT_STATE
                    else:
                        state = value
                else:
                    _LOGGER.warning(
                        "Migrating non-string wardrobe row for %s → default",
                        entry_id,
                    )
                    state = DEFAULT_STATE
                entries_new[entry_id] = _new_record(state=state)
            return {"entries": entries_new}
        return old_data


class WardrobeCoordinator(DataUpdateCoordinator[dict[str, WardrobeRecord]]):
    """Holds the wardrobe state for every configured item and persists it.

    Despite subclassing ``DataUpdateCoordinator`` (per the spec), this is not a
    polling coordinator — there is no remote source to poll. ``async_set_updated_data``
    is used to notify ``CoordinatorEntity`` listeners after mutations.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._store: WardrobeStore = WardrobeStore(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self.data: dict[str, WardrobeRecord] = {}

    async def async_load(self) -> None:
        """Read persisted state from storage."""
        stored = await self._store.async_load()
        if stored is None:
            self.data = {}
        else:
            entries = stored.get("entries", {}) or {}
            self.data = {
                entry_id: _coerce_record(rec) for entry_id, rec in entries.items()
            }
        self.async_set_updated_data(self.data)

    async def _async_save(self) -> None:
        """Persist the current state to storage."""
        try:
            await self._store.async_save({"entries": self.data})
        except Exception:
            _LOGGER.error("Failed to save wardrobe state", exc_info=True)

    async def async_ensure_entry(self, entry_id: str) -> None:
        """Seed an entry's record to defaults if it hasn't been seen before."""
        if entry_id not in self.data:
            self.data[entry_id] = _new_record()
            await self._async_save()
            self.async_set_updated_data(self.data)

    def get_state(self, entry_id: str) -> str:
        """Return the current state for an entry."""
        rec = self.data.get(entry_id)
        if rec is None:
            return DEFAULT_STATE
        return rec["state"]

    def get_record(self, entry_id: str) -> WardrobeRecord:
        """Return a defensive copy of an entry's record (or defaults)."""
        rec = self.data.get(entry_id)
        if rec is None:
            return _new_record()
        return dict(rec)  # type: ignore[return-value]

    def get_all_items(self) -> dict[str, str]:
        """Return a snapshot of all entry → state mappings."""
        return {entry_id: rec["state"] for entry_id, rec in self.data.items()}

    def count_by_state(self) -> dict[str, int]:
        """Return a map of state → number of entries currently in that state."""
        counts = {s: 0 for s in STATES}
        for rec in self.data.values():
            state = rec["state"]
            counts[state] = counts.get(state, 0) + 1
        return counts

    async def async_set_state(self, entry_id: str, new_state: str) -> None:
        """Set an entry's state, persist, and fire the state-changed event."""
        if new_state not in STATES:
            raise ValueError(f"Invalid wardrobe state: {new_state!r}")

        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        old_state = rec["state"]
        same_state = old_state == new_state
        now_iso = dt_util.utcnow().isoformat()

        rec["state"] = new_state

        if not same_state:
            rec["state_changed_at"] = now_iso

        if new_state == WardrobeState.WORN.value and not same_state:
            rec["wears_since_wash"] = int(rec["wears_since_wash"]) + 1
            rec["wear_count_total"] = int(rec["wear_count_total"]) + 1
            rec["last_worn_at"] = now_iso

        if new_state == WardrobeState.LAUNDRY.value and not same_state:
            rec["wears_since_wash"] = 0

        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

        entry = self.hass.config_entries.async_get_entry(entry_id)
        name = entry.data.get(CONF_ITEM_NAME) if entry is not None else None
        self.hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "entry_id": entry_id,
                "name": name,
                "old_state": old_state,
                "new_state": new_state,
                ATTR_WEARS_SINCE_WASH: rec["wears_since_wash"],
                ATTR_WEAR_COUNT_TOTAL: rec["wear_count_total"],
                ATTR_LAST_WORN_AT: rec["last_worn_at"],
                ATTR_STATE_CHANGED_AT: rec["state_changed_at"],
            },
        )
        _LOGGER.debug(
            "Wardrobe state changed: %s (%s) %s -> %s",
            name,
            entry_id,
            old_state,
            new_state,
        )

    async def async_cycle_state(self, entry_id: str) -> str:
        """Advance an entry to its next state in the cycle."""
        current = self.get_state(entry_id)
        new = next_state(current)
        await self.async_set_state(entry_id, new)
        return new

    async def async_remove_entry(self, entry_id: str) -> None:
        """Drop an entry's record from storage when its ConfigEntry is removed."""
        if entry_id in self.data:
            del self.data[entry_id]
            await self._async_save()
            self.async_set_updated_data(self.data)

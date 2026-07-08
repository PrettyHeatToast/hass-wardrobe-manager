"""Coordinator for the Wardrobe integration — shared state and persistence."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ALL_STATES,
    ATTR_LAST_WASHED_AT,
    ATTR_LAST_WORN_AT,
    ATTR_STATE_CHANGED_AT,
    ATTR_THRESHOLD,
    ATTR_WASH_COUNT,
    ATTR_WEAR_COUNT_TOTAL,
    ATTR_WEARS_SINCE_WASH,
    CONF_EXTRA_STATES,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_QUANTITY,
    CONF_WEAR_THRESHOLD,
    CONF_WEIGHT,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_STATE,
    DEFAULT_WEAR_THRESHOLD,
    DEFAULT_WEIGHT,
    DIRTY_STATES,
    DOMAIN,
    EVENT_NEEDS_WASH,
    EVENT_STATE_CHANGED,
    KIND_SUMMARY,
    STORAGE_KEY,
    STORAGE_VERSION,
    WardrobeState,
    build_cycle,
    is_bulk_entry,
    next_state_in,
)

_LOGGER = logging.getLogger(__name__)


class WardrobeRecord(TypedDict):
    """Per-entry state persisted in storage."""

    state: str
    wears_since_wash: int
    wear_count_total: int
    wash_count: int
    last_worn_at: str | None
    last_washed_at: str | None
    state_changed_at: str | None
    wear_threshold: int | None
    weight: float | None
    dirty_count: int


def _new_record(
    *,
    state: str = DEFAULT_STATE,
    wear_threshold: int | None = None,
    weight: float | None = None,
) -> WardrobeRecord:
    """Return a fully-populated default record."""
    return {
        "state": state,
        "wears_since_wash": 0,
        "wear_count_total": 0,
        "wash_count": 0,
        "last_worn_at": None,
        "last_washed_at": None,
        "state_changed_at": None,
        "wear_threshold": wear_threshold,
        "weight": weight,
        "dirty_count": 0,
    }


def _coerce_record(value: Any) -> WardrobeRecord:
    """Coerce a stored value into a complete WardrobeRecord.

    Defensive merge so half-populated rows (hand edits, older minor versions)
    don't KeyError downstream. A missing ``wear_threshold`` or ``weight``
    stays ``None`` so ``async_ensure_entry`` can seed it from the ConfigEntry.
    """
    base = _new_record()
    if isinstance(value, dict):
        state = value.get("state", DEFAULT_STATE)
        if state not in ALL_STATES:
            state = DEFAULT_STATE
        base["state"] = state
        for key in ("wears_since_wash", "wear_count_total", "wash_count"):
            v = value.get(key)
            if isinstance(v, int) and v >= 0:
                base[key] = v
        for key in ("last_worn_at", "last_washed_at", "state_changed_at"):
            v = value.get(key)
            if isinstance(v, str) or v is None:
                base[key] = v
        v = value.get("wear_threshold")
        if isinstance(v, int) and v >= 0:
            base["wear_threshold"] = v
        v = value.get("weight")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            base["weight"] = float(v)
        v = value.get("dirty_count")
        if isinstance(v, int) and v >= 0:
            base["dirty_count"] = v
    return base


class WardrobeStore(Store[dict[str, Any]]):
    """Store subclass that migrates v1/v2/v3 payloads to v4."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Lift older storage payloads into v4 records.

        v1 rows were bare state strings; v2 rows were records without
        ``wash_count`` / ``last_washed_at`` / ``wear_threshold``; v3 rows
        lacked ``weight`` / ``dirty_count``. ``_coerce_record`` fills every
        gap, so all lift the same way.
        """
        if old_major_version in (1, 2, 3):
            entries_old = old_data.get("entries", {}) or {}
            entries_new: dict[str, WardrobeRecord] = {}
            for entry_id, value in entries_old.items():
                if isinstance(value, str):
                    if value not in ALL_STATES:
                        _LOGGER.warning(
                            "Migrating unknown wardrobe state %r for %s → %s",
                            value,
                            entry_id,
                            DEFAULT_STATE,
                        )
                        value = DEFAULT_STATE
                    entries_new[entry_id] = _new_record(state=value)
                else:
                    entries_new[entry_id] = _coerce_record(value)
            return {"entries": entries_new}
        return old_data


class WardrobeCoordinator(DataUpdateCoordinator[dict[str, WardrobeRecord]]):
    """Holds the wardrobe state for every configured item and persists it.

    Despite subclassing ``DataUpdateCoordinator``, this is not a polling
    coordinator — there is no remote source to poll. ``async_set_updated_data``
    notifies ``CoordinatorEntity`` listeners after mutations.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._store: WardrobeStore = WardrobeStore(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, WardrobeRecord] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

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
        """Seed an entry's record, syncing seeded fields from config on first run."""
        rec = self.data.get(entry_id)
        if rec is None:
            self.data[entry_id] = _new_record(
                wear_threshold=self._config_threshold(entry_id),
                weight=self._config_weight(entry_id),
            )
        else:
            changed = False
            if rec["wear_threshold"] is None:
                # Migrated record: adopt the threshold configured on the entry.
                rec["wear_threshold"] = self._config_threshold(entry_id)
                changed = True
            if rec["weight"] is None:
                rec["weight"] = self._config_weight(entry_id)
                changed = True
            if not changed:
                return
        await self._async_save()
        self.async_set_updated_data(self.data)

    async def async_remove_entry(self, entry_id: str) -> None:
        """Drop an entry's record from storage when its ConfigEntry is removed."""
        if entry_id in self.data:
            del self.data[entry_id]
            await self._async_save()
            self.async_set_updated_data(self.data)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_state(self, entry_id: str) -> str:
        """Return the current state for an entry."""
        rec = self.data.get(entry_id)
        return DEFAULT_STATE if rec is None else rec["state"]

    def get_record(self, entry_id: str) -> WardrobeRecord:
        """Return a defensive copy of an entry's record (or defaults)."""
        rec = self.data.get(entry_id)
        if rec is None:
            return _new_record()
        return dict(rec)  # type: ignore[return-value]

    def get_threshold(self, entry_id: str) -> int:
        """Return the effective wear threshold for an entry (0 = disabled)."""
        rec = self.data.get(entry_id)
        if rec is not None and rec["wear_threshold"] is not None:
            return int(rec["wear_threshold"])
        return self._config_threshold(entry_id)

    def get_weight(self, entry_id: str) -> float:
        """Return the effective per-unit load weight for an entry."""
        rec = self.data.get(entry_id)
        if rec is not None and rec["weight"] is not None:
            return float(rec["weight"])
        return self._config_weight(entry_id)

    def get_clean_remaining(self, entry_id: str) -> int:
        """Return how many clean units of a bulk item remain."""
        rec = self.data.get(entry_id)
        dirty = 0 if rec is None else int(rec["dirty_count"])
        return max(0, self._config_quantity(entry_id) - dirty)

    def load_for_type(self, laundry_type: str) -> tuple[list[str], int, float]:
        """Return ``(names, units, total_weight)`` waiting for a laundry type.

        Individual items in ``laundry`` contribute one unit of their weight;
        bulk items contribute ``dirty_count`` units of theirs (named once).
        """
        names: list[str] = []
        units = 0
        total_weight = 0.0
        for entry_id, rec in self.data.items():
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.data.get(CONF_KIND) == KIND_SUMMARY:
                continue
            if (
                entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE)
                != laundry_type
            ):
                continue
            if is_bulk_entry(entry.data):
                dirty = int(rec["dirty_count"])
                if dirty <= 0:
                    continue
                names.append(entry.data.get(CONF_ITEM_NAME, entry_id))
                units += dirty
                total_weight += dirty * self.get_weight(entry_id)
            else:
                if rec["state"] != WardrobeState.LAUNDRY.value:
                    continue
                names.append(entry.data.get(CONF_ITEM_NAME, entry_id))
                units += 1
                total_weight += self.get_weight(entry_id)
        return sorted(names), units, total_weight

    def count_by_state(self) -> dict[str, int]:
        """Return a map of state → number of entries currently in that state."""
        counts = {s: 0 for s in ALL_STATES}
        for rec in self.data.values():
            counts[rec["state"]] = counts.get(rec["state"], 0) + 1
        return counts

    def _config_threshold(self, entry_id: str) -> int:
        """Return the threshold configured on the ConfigEntry (creation default)."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return DEFAULT_WEAR_THRESHOLD
        return int(entry.data.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD) or 0)

    def _config_weight(self, entry_id: str) -> float:
        """Return the weight configured on the ConfigEntry (creation default)."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return DEFAULT_WEIGHT
        return float(entry.data.get(CONF_WEIGHT, DEFAULT_WEIGHT) or DEFAULT_WEIGHT)

    def _config_quantity(self, entry_id: str) -> int:
        """Return the owned quantity configured on a bulk ConfigEntry."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return 1
        return max(1, int(entry.data.get(CONF_QUANTITY, 1) or 1))

    def _is_bulk(self, entry_id: str) -> bool:
        """Return True when the entry is a bulk (counter-tracked) item."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        return entry is not None and is_bulk_entry(entry.data)

    def _cycle_for(self, entry_id: str) -> list[str]:
        """Return the state cycle for an entry, honoring its extra states."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        extras = entry.data.get(CONF_EXTRA_STATES) if entry is not None else None
        return build_cycle(extras)

    def _item_name(self, entry_id: str) -> str | None:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        return entry.data.get(CONF_ITEM_NAME) if entry is not None else None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def async_set_threshold(self, entry_id: str, value: int) -> None:
        """Set the runtime wear threshold for an entry (0 disables it)."""
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        rec["wear_threshold"] = max(0, int(value))
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

    async def async_set_weight(self, entry_id: str, value: float) -> None:
        """Set the runtime per-unit load weight for an entry."""
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        rec["weight"] = max(0.1, float(value))
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

    async def async_set_clean_remaining(self, entry_id: str, value: int) -> None:
        """Set how many clean units of a bulk item remain.

        Lowering the count means units were worn: the difference is added to
        ``dirty_count`` and ``wear_count_total`` and ``last_worn_at`` is
        stamped. Raising it is a silent correction (dirty units removed
        without wash accounting). No events fire either way.
        """
        quantity = self._config_quantity(entry_id)
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        old_dirty = int(rec["dirty_count"])
        new_clean = min(max(0, int(value)), quantity)
        new_dirty = quantity - new_clean
        if new_dirty == old_dirty:
            return
        if new_dirty > old_dirty:
            worn = new_dirty - old_dirty
            rec["wear_count_total"] = int(rec["wear_count_total"]) + worn
            rec["last_worn_at"] = dt_util.utcnow().isoformat()
        rec["dirty_count"] = new_dirty
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

    async def async_bulk_wear_one(self, entry_id: str) -> None:
        """Record putting on one unit of a bulk item (clean → dirty)."""
        await self.async_set_clean_remaining(
            entry_id, self.get_clean_remaining(entry_id) - 1
        )

    async def async_bulk_mark_washed(self, entry_id: str) -> bool:
        """Wash a bulk item's dirty units. Returns True if anything was dirty."""
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        if int(rec["dirty_count"]) <= 0:
            return False
        rec["dirty_count"] = 0
        rec["wash_count"] = int(rec["wash_count"]) + 1
        rec["last_washed_at"] = dt_util.utcnow().isoformat()
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)
        return True

    async def async_set_state(self, entry_id: str, new_state: str) -> None:
        """Set an entry's state with full wear/wash accounting.

        - Entering ``worn`` from another state counts a wear.
        - Entering ``clean`` from a dirty state (laundry/washing/drying/
          ironing) counts a completed wash and resets ``wears_since_wash``.
        """
        if new_state not in ALL_STATES:
            raise ValueError(f"Invalid wardrobe state: {new_state!r}")
        if self._is_bulk(entry_id):
            _LOGGER.debug("Ignoring state change for bulk item %s", entry_id)
            return

        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        old_state = rec["state"]
        same_state = old_state == new_state
        now_iso = dt_util.utcnow().isoformat()

        rec["state"] = new_state
        if not same_state:
            rec["state_changed_at"] = now_iso

        crossed_threshold = False
        if new_state == WardrobeState.WORN.value and not same_state:
            rec["wears_since_wash"] = int(rec["wears_since_wash"]) + 1
            rec["wear_count_total"] = int(rec["wear_count_total"]) + 1
            rec["last_worn_at"] = now_iso
            crossed_threshold = self._reached_threshold(entry_id, rec)

        if new_state == DEFAULT_STATE and old_state in DIRTY_STATES:
            rec["wash_count"] = int(rec["wash_count"]) + 1
            rec["last_washed_at"] = now_iso
            rec["wears_since_wash"] = 0

        await self._commit_and_fire(entry_id, rec, old_state, new_state)
        if crossed_threshold:
            self._fire_needs_wash(entry_id, rec)

    async def async_record_wear(self, entry_id: str) -> None:
        """Record another wear without changing state.

        Used when an item is worn again while already in ``worn``. Bumps the
        counters and ``last_worn_at`` but leaves ``state`` alone. Fires
        ``EVENT_STATE_CHANGED`` with ``old_state == new_state`` so automations
        can react to re-wears.
        """
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        now_iso = dt_util.utcnow().isoformat()
        rec["wears_since_wash"] = int(rec["wears_since_wash"]) + 1
        rec["wear_count_total"] = int(rec["wear_count_total"]) + 1
        rec["last_worn_at"] = now_iso
        crossed_threshold = self._reached_threshold(entry_id, rec)

        await self._commit_and_fire(entry_id, rec, rec["state"], rec["state"])
        if crossed_threshold:
            self._fire_needs_wash(entry_id, rec)

    async def async_mark_worn(self, entry_id: str) -> None:
        """Mark an item as worn: transition to worn, or count a re-wear."""
        if self._is_bulk(entry_id):
            _LOGGER.debug("Ignoring mark_worn for bulk item %s", entry_id)
            return
        if self.get_state(entry_id) == WardrobeState.WORN.value:
            await self.async_record_wear(entry_id)
        else:
            await self.async_set_state(entry_id, WardrobeState.WORN.value)

    async def async_mark_washed(self, entry_id: str) -> None:
        """Mark an item as freshly washed regardless of its current state."""
        if self._is_bulk(entry_id):
            await self.async_bulk_mark_washed(entry_id)
            return
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        old_state = rec["state"]
        now_iso = dt_util.utcnow().isoformat()

        rec["state"] = DEFAULT_STATE
        if old_state != DEFAULT_STATE:
            rec["state_changed_at"] = now_iso
        rec["wash_count"] = int(rec["wash_count"]) + 1
        rec["last_washed_at"] = now_iso
        rec["wears_since_wash"] = 0

        await self._commit_and_fire(entry_id, rec, old_state, DEFAULT_STATE)

    async def async_cycle_state(self, entry_id: str) -> str:
        """Advance an entry to its next state, respecting the wear threshold.

        Threshold disabled (``0``): cycle on every call.

        Threshold ``N > 0``: while in ``worn`` and ``wears_since_wash < N``,
        record another wear (state stays ``worn``). The call after the
        threshold is reached transitions onward as normal.
        """
        if self._is_bulk(entry_id):
            _LOGGER.debug("Ignoring cycle_state for bulk item %s", entry_id)
            return self.get_state(entry_id)
        current = self.get_state(entry_id)
        threshold = self.get_threshold(entry_id)
        if (
            current == WardrobeState.WORN.value
            and threshold > 0
            and int(self.get_record(entry_id)["wears_since_wash"]) < threshold
        ):
            await self.async_record_wear(entry_id)
            return current

        new = next_state_in(self._cycle_for(entry_id), current)
        await self.async_set_state(entry_id, new)
        return new

    async def async_reset_statistics(self, entry_id: str) -> None:
        """Zero all counters and timestamps, keeping the current state."""
        rec = dict(self.data.get(entry_id) or _new_record())  # type: ignore[arg-type]
        rec["wears_since_wash"] = 0
        rec["wear_count_total"] = 0
        rec["wash_count"] = 0
        rec["last_worn_at"] = None
        rec["last_washed_at"] = None
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _reached_threshold(self, entry_id: str, rec: WardrobeRecord) -> bool:
        """Return True when this wear made the item hit its threshold exactly.

        Checking equality (not >=) fires the needs-wash event once per wash
        cycle instead of on every wear past the limit.
        """
        threshold = (
            int(rec["wear_threshold"])
            if rec["wear_threshold"] is not None
            else self._config_threshold(entry_id)
        )
        return threshold > 0 and int(rec["wears_since_wash"]) == threshold

    def _fire_needs_wash(self, entry_id: str, rec: WardrobeRecord) -> None:
        self.hass.bus.async_fire(
            EVENT_NEEDS_WASH,
            {
                "entry_id": entry_id,
                "name": self._item_name(entry_id),
                ATTR_WEARS_SINCE_WASH: rec["wears_since_wash"],
                ATTR_THRESHOLD: rec["wear_threshold"],
            },
        )

    async def _commit_and_fire(
        self,
        entry_id: str,
        rec: WardrobeRecord,
        old_state: str,
        new_state: str,
    ) -> None:
        """Store the record, notify listeners and fire the state-changed event."""
        self.data[entry_id] = rec  # type: ignore[assignment]
        await self._async_save()
        self.async_set_updated_data(self.data)

        name = self._item_name(entry_id)
        self.hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "entry_id": entry_id,
                "name": name,
                "old_state": old_state,
                "new_state": new_state,
                ATTR_WEARS_SINCE_WASH: rec["wears_since_wash"],
                ATTR_WEAR_COUNT_TOTAL: rec["wear_count_total"],
                ATTR_WASH_COUNT: rec["wash_count"],
                ATTR_LAST_WORN_AT: rec["last_worn_at"],
                ATTR_LAST_WASHED_AT: rec["last_washed_at"],
                ATTR_STATE_CHANGED_AT: rec["state_changed_at"],
            },
        )
        _LOGGER.debug(
            "Wardrobe: %s (%s) %s -> %s (wears=%d total=%d washes=%d)",
            name,
            entry_id,
            old_state,
            new_state,
            rec["wears_since_wash"],
            rec["wear_count_total"],
            rec["wash_count"],
        )

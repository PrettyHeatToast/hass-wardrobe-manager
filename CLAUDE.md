# CLAUDE.md — Wardrobe HA Integration (v2)

## Project Overview

`wardrobe` is a custom Home Assistant integration (`custom_components/wardrobe`) that tracks
individual clothing items through a configurable laundry-cycle state machine with full
wear/wash accounting. Each garment is a separate HA **ConfigEntry** (one Device, ~11
entities). A singleton **Wardrobe Summary** hub entry is auto-created with the first item
and aggregates household-wide sensors.

NFC tags are matched against HA's native `tag_scanned` event (built-in `tag` integration).

## Compatibility

Code must run on **HA 2024.3 through current**. The repo venv (`.venv`, Python 3.11) pins
HA 2024.3.3 — that is what tests run against. Known shims:

- `ConfigFlowResult` is imported with a try/except fallback to `FlowResult`
  (config_flow.py) — do not import it unconditionally.
- `OptionsFlow` handlers receive the ConfigEntry via `__init__` and store it as
  `self._entry` (never assign `self.config_entry`; deprecated on new cores, absent on old).

## State Machine

Core cycle: `clean → worn → laundry → clean`, wrapping.

Per-item opt-in **extra states** (`CONF_EXTRA_STATES`):
- Pipeline states `washing`, `drying`, `ironing` — inserted between `laundry` and `clean`
  in canonical order (`build_cycle()` in const.py, pure function).
- Parked states `repair`, `storage` — selectable but outside the cycle; cycling from a
  parked state returns to `clean` (`next_state_in()`).

**Accounting rules** (coordinator.py `async_set_state`):
- entering `worn` from another state → `wears_since_wash++`, `wear_count_total++`, `last_worn_at`
- entering `clean` from a `DIRTY_STATES` member (laundry/washing/drying/ironing) →
  `wash_count++`, `last_washed_at`, `wears_since_wash = 0`
- wears do NOT reset on entering `laundry` (changed from v1.2) — they reset when washed.

**Wear threshold** (`N > 0`): while `worn` with `wears_since_wash < N`, `async_cycle_state`
records a re-wear instead of advancing. Fires `wardrobe_needs_wash` exactly once when the
count *equals* the threshold. The runtime threshold lives in the **storage record**
(edited by the per-item `number` entity); the config-flow value only seeds it at creation.

Triggers: NFC scan (per-item `scan_action`: cycle | mark_worn | mark_washed), entity
services, domain services, select UI.

Events: `wardrobe_state_changed` (also fired for re-wears with old==new),
`wardrobe_needs_wash`, `wardrobe_wash_completed` (from `wash_load`).

## Project Structure

```
custom_components/wardrobe/
├── __init__.py          # setup/unload/remove, shared singleton, tag listener,
│                        #   bulk_set_state + wash_load domain services
├── const.py             # states, build_cycle/next_state_in/selectable_states,
│                        #   categories, laundry types, seasons, scan actions
├── coordinator.py       # WardrobeCoordinator + WardrobeStore (v3, migrates v1/v2)
├── config_flow.py       # 3-step create flow (user→tracking→details),
│                        #   menu OptionsFlow (item), load-size OptionsFlow (hub)
├── entity.py            # WardrobeItemEntity / WardrobeHubEntity bases + device_info
├── select.py            # state select + ALL entity services registered here
├── sensor.py            # item counters/timestamps/cost_per_wear + hub aggregates
├── binary_sensor.py     # item needs_washing + hub load_ready_<type>
├── button.py            # item mark_worn/mark_washed + hub complete_wash
├── number.py            # item wear_threshold (storage-backed, no entry reload)
├── diagnostics.py       # redacts nfc_tag_id
├── services.yaml / strings.json / translations/en.json
tests/                   # pytest-homeassistant-custom-component suite
├── helpers.py           # make_item/setup_item/entity_id/hub_entity_id
└── test_wardrobe_*.py
```

## Architecture Notes

- **Shared singleton**: coordinator + tag listener + domain services are created lazily on
  first `async_setup_entry` (`_ensure_shared`), torn down when the last entry unloads.
  Ref counting in `hass.data[DOMAIN]["shared"]["entry_ids"]`.
- **Hub entry**: marked by `data["_kind"] == "summary"`; auto-created via an
  `integration_discovery` flow from the first item's setup; unique_id enforces singleton.
  Hub forwards `HUB_PLATFORMS`, items forward `PLATFORMS` (const.py).
- **Storage**: `Store(version=3, key="wardrobe_states")`, one record per entry_id:
  `{state, wears_since_wash, wear_count_total, wash_count, last_worn_at, last_washed_at,
  state_changed_at, wear_threshold}`. `wear_threshold: None` means "seed from ConfigEntry
  on next ensure" (migration path). Rows purged in `async_remove_entry`.
- **Unique IDs are frozen**: item entities `wardrobe_<entry_id>_<suffix>` (select suffix is
  `state`), hub entities `wardrobe_summary_<suffix>` (count sensors keep pre-2.0 suffixes:
  `clean`, `worn`, `laundry`). Don't rename without a registry migration.
- **Options flow writes to `entry.data`** (not `entry.options`) for items; the update
  listener reloads the entry. Hub options (`load_size`) go to `entry.options`.

## Coding Standards

- Python 3.12+ syntax level, full type hints, `from __future__ import annotations`.
- No hardcoded user-facing strings — everything through `strings.json` +
  `translations/en.json` (kept as identical copies; `strings.json` is the source).
- Pure state-machine helpers stay in `const.py` so they're testable without `hass`.
- 100% local; `Store` is the only persistence layer.

## Running tests

```
.venv/Scripts/python.exe -m pytest tests -q
```

The full suite takes several minutes (HA test harness on Windows). `tests/conftest.py`
stubs `pytest_socket.disable_socket` on win32 — do not remove it. Resolve entity IDs via
the registry helpers in `tests/helpers.py`, never hardcode `entity_id` strings.

## Out of Scope

- Outfit grouping, AI suggestions, weather-aware recommendations
- Multi-locale translations (only `en.json` ships)
- Photos / images per item

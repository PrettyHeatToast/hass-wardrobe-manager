# CLAUDE.md — wardrobe HA Integration

## Project Overview

`wardrobe` is a custom Home Assistant integration (`custom_components/wardrobe`) that tracks
individual clothing items through a simple laundry-cycle state machine. Each garment is a
separate Home Assistant **ConfigEntry** registered via Settings → Devices → Add Integration,
which produces one HA **Device** and one `select` entity for that item's state.

NFC tags are matched against HA's native `tag_scanned` event (from the built-in `tag`
integration). Any tag source that fires `tag_scanned` works — ESPhome, the HA companion
mobile app, USB NFC readers, etc.

## Domain & Key Terminology

| Term | Meaning |
|---|---|
| `wardrobe` | Integration domain |
| Item | A clothing garment; one HA Device + one `select` entity per item |
| `nfc_tag_id` | Optional NFC tag UID associated with an item; matched against `tag_scanned` events |
| `category` | Garment type (shirt, jeans, jacket, …); drives the entity icon |
| State | One of `clean`, `worn`, `laundry` |

## State Machine

A single three-state cycle, wrapping around:

```
clean → worn → laundry → clean
```

Triggered by:
1. Scanning the item's NFC tag (HA `tag_scanned` event) — calls `cycle_state` for the
   matching entry.
2. Calling the `wardrobe.cycle_state` service from an automation, script, or developer tools.
3. Calling `wardrobe.set_state` (with `state: clean|worn|laundry`) — jumps to a specific state.
4. Editing the `select` entity directly in the HA UI.

Every state change fires an HA event `wardrobe_state_changed` with payload:
`{entry_id, name, old_state, new_state}`.

## Project Structure

```
custom_components/wardrobe/
├── __init__.py              # async_setup_entry / unload_entry / remove_entry, tag listener
├── manifest.json            # version, dependencies = ["tag"], integration_type = "device"
├── const.py                 # DOMAIN, WardrobeState enum, STATE_CYCLE, CATEGORY_ICONS
├── coordinator.py           # WardrobeCoordinator(DataUpdateCoordinator) — Store-backed
├── config_flow.py           # WardrobeConfigFlow + WardrobeOptionsFlow
├── select.py                # WardrobeStateSelect + entity-service registration
├── services.yaml            # cycle_state + set_state descriptions
├── strings.json             # Source UI strings
└── translations/en.json     # English translations (mirrors strings.json)

tests/
├── conftest.py                       # enable_custom_integrations autouse fixture
├── test_wardrobe_const.py            # Pure-Python tests for STATE_CYCLE / next_state
├── test_wardrobe_config_flow.py      # User flow + OptionsFlow tests
└── test_wardrobe_coordinator.py      # Coordinator + tag-scan tests
```

## Architecture

### Per-entry device + entity

Each ConfigEntry corresponds to one garment. Its entity's `device_info` uses
`identifiers={(DOMAIN, entry.entry_id)}` so HA creates one Device per entry automatically.

### Shared singleton (coordinator + listener + services)

The coordinator, `tag_scanned` listener, and entity services are **shared across all entries**.
They are created lazily on the first `async_setup_entry` via `_ensure_shared(hass)`, and torn
down on the last `async_unload_entry`. Ref counting lives in
`hass.data[DOMAIN]["shared"]["entry_ids"]` — a set of active entry IDs.

### Storage

`Store(hass, version=1, key="wardrobe_states")` persists per-entry state:

```json
{
  "entries": {
    "<entry_id_1>": "clean",
    "<entry_id_2>": "worn"
  }
}
```

Storage rows are purged from `async_remove_entry` when a user deletes an item via the UI.

### NFC matching

The `tag_scanned` listener (decorated `@callback`) iterates
`hass.config_entries.async_entries(DOMAIN)`, finds the entry whose `data["nfc_tag_id"]`
equals the scanned tag, and dispatches `coordinator.async_cycle_state` via
`hass.async_create_task` (sync callback can't `await`). Unmatched tags log at debug level.

## Entities per Item

| Platform | Entity | Description |
|---|---|---|
| `select` | `<item_name>_state` | Current state; UI dropdown allows manual override |

Icon logic: when state is `laundry`, the icon is `mdi:washing-machine`; otherwise it's
`CATEGORY_ICONS[category]` (falling back to `mdi:hanger`).

## Services

| Service | Target | Fields |
|---|---|---|
| `wardrobe.cycle_state` | `target.entity` (select) | — |
| `wardrobe.set_state` | `target.entity` (select) | `state` (one of `clean`, `worn`, `laundry`) |

Both are registered via `entity_platform.async_register_entity_service` in `select.py`. The
service caller picks a target entity in the UI service editor and HA expands it automatically.

## Config Flow

**User step** (single step, one item per flow):
- `name` (required, string) — must be unique among items; uniqueness enforced via
  `unique_id = slugify(name)` + `_abort_if_unique_id_configured()`.
- `category` (required) — `SelectSelector` over `CATEGORY_ICONS.keys()`.
- `nfc_tag_id` (optional, string) — must be unique among items if provided.

**Options flow** (edit existing item):
- `category` + `nfc_tag_id` (pre-populated). Re-checks tag uniqueness excluding self.
- Writes back to `entry.data` (not `entry.options`) and triggers an `async_reload` via the
  `add_update_listener` registered in `async_setup_entry` — so the icon picks up the new
  category immediately.

## Coding Standards

- **Python**: 3.12+, full type hints, `from __future__ import annotations` everywhere.
- **Async**: all HA-touching code is `async`; `const.py::next_state` is intentionally sync
  for testing without a `hass` fixture.
- **Logging**: `logging.getLogger(__name__)` per module. `_LOGGER.debug` for scan events;
  `_LOGGER.error` (with `exc_info=True`) for storage failures.
- **No hardcoded user-facing strings**: every label goes through `strings.json` and
  `translations/en.json`.
- **GDPR / privacy**: 100% local — `Store` is the only persistence layer, no network calls.

## manifest.json

```json
{
  "domain": "wardrobe",
  "name": "Wardrobe",
  "version": "1.0.0",
  "config_flow": true,
  "integration_type": "device",
  "iot_class": "local_push",
  "dependencies": ["tag"],
  "codeowners": ["@wouthofman"],
  "requirements": []
}
```

## Out of Scope (v1.0)

- Outfit grouping or AI suggestions
- Weather-aware recommendations
- Per-garment thresholds for "needs washing" (the cycle is fixed: 3 states, no counts)
- Multi-locale translations (only `en.json` is shipped — `strings.json` is the source)
- Migration from any previous integration's storage

## Reference Automation

Manually wiring an NFC scan to a state cycle from a YAML automation (the integration does
this automatically, but the snippet is useful for testing or explicit overrides):

```yaml
trigger:
  - platform: event
    event_type: tag_scanned
    event_data:
      tag_id: "abc-123-def"
action:
  - service: wardrobe.cycle_state
    target:
      entity_id: select.white_tshirt_state
```

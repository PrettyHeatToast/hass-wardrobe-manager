# Wardrobe — Home Assistant integration

Track every garment in your wardrobe and through the wash, with NFC tags,
wear counting, laundry-load planning and cost-per-wear statistics.
100% local — no cloud, no network calls.

## How it works

Each clothing item is its own device in Home Assistant. Items move through a
configurable state cycle:

```
clean → worn → laundry ─→ clean
                  │  (optional pipeline states)
                  └→ washing → drying → ironing → clean
```

Two extra **parked states** — `repair` and `storage` — can be enabled per
item. They sit outside the cycle; cycling from them returns the item to
`clean`.

Scan the item's NFC tag (any source that fires Home Assistant's native
`tag_scanned` event: the companion app, ESPHome, a USB reader, …) and the
item advances. What a scan does is configurable per item: cycle to the next
state, mark as worn, or mark as washed.

### Wear thresholds

Give an item a *wears per wash cycle* threshold (say, 3 for jeans) and
cycling keeps it in `worn` — counting re-wears — until the threshold is
reached; the next scan sends it to the laundry. The threshold is a live
`number` entity, adjustable anytime without touching the config.

### The Wardrobe Summary hub

A summary device is created automatically with your first item:

- counts per state (clean / worn / laundry / being washed / total)
- items that hit their wear threshold
- a load sensor per laundry type (dark, light, color, delicates, wool, hand
  wash) with the waiting items listed as attributes
- a **load ready** binary sensor per laundry type that turns on when a full
  load is waiting (load size configurable in the hub's options)
- a **Complete wash cycle** button that returns every dirty item to clean

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → *Custom repositories* → add this repo as type
   *Integration*.
2. Install **Wardrobe**, restart Home Assistant.

### Manual

Copy `custom_components/wardrobe` into your `config/custom_components/`
folder and restart.

## Adding items

Settings → Devices & Services → *Add Integration* → **Wardrobe**. The flow
has three steps:

1. **Basics** — name, category (34 to choose from), laundry type.
2. **Tracking** — NFC tag ID, scan action, extra states, wear threshold.
3. **Details** (all optional) — brand, size, color, material, seasons,
   storage location, purchase date, purchase price, notes.

Everything except the name can be edited later via the entry's *Configure*
menu. If a purchase price is set, a **cost per wear** sensor appears.

> Tip: to read a tag's ID, scan it once and look at Settings → Tags, or
> watch the `tag_scanned` event in Developer Tools.

## Entities per item

| Platform | Entity | Notes |
|---|---|---|
| `select` | State | full item metadata in the attributes |
| `sensor` | Wears since wash | resets when washed |
| `sensor` | Total wears | lifetime |
| `sensor` | Wash count | lifetime |
| `sensor` | Last worn / Last washed / Last state change | timestamps |
| `sensor` | Cost per wear | only when a purchase price is set |
| `binary_sensor` | Needs washing | on when the wear threshold is reached |
| `button` | I wore this / Washed | quick actions |
| `number` | Wears per wash cycle | 0 disables the threshold |

## Services

| Service | Target | Description |
|---|---|---|
| `wardrobe.cycle_state` | select entity | advance to the next state (threshold-aware) |
| `wardrobe.set_state` | select entity | jump to a specific state |
| `wardrobe.mark_worn` | select entity | record a wear (or re-wear) |
| `wardrobe.mark_washed` | select entity | freshly washed → clean |
| `wardrobe.reset_statistics` | select entity | zero all counters |
| `wardrobe.bulk_set_state` | — | set state on all items matching category / laundry type / current state filters |
| `wardrobe.wash_load` | — | complete a wash for all dirty items (optionally one laundry type) |

## Events

| Event | Fired when |
|---|---|
| `wardrobe_state_changed` | any state change or re-wear (`old_state == new_state`), with full counters in the payload |
| `wardrobe_needs_wash` | an item reaches its wear threshold (once per cycle) |
| `wardrobe_wash_completed` | `wardrobe.wash_load` (or the hub button) finishes, with the washed items |

## Example automations

Notify when a dark load is ready:

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.wardrobe_summary_dark_load_ready
    to: "on"
action:
  - service: notify.mobile_app_phone
    data:
      message: >-
        Dark load ready:
        {{ state_attr('binary_sensor.wardrobe_summary_dark_load_ready', 'items') | join(', ') }}
```

Empty the whole basket when the washing machine finishes:

```yaml
trigger:
  - platform: state
    entity_id: sensor.washing_machine
    from: running
    to: idle
action:
  - service: wardrobe.wash_load
```

Nag about an item that needs washing:

```yaml
trigger:
  - platform: event
    event_type: wardrobe_needs_wash
action:
  - service: notify.mobile_app_phone
    data:
      message: "{{ trigger.event.data.name }} has been worn {{ trigger.event.data.wears_since_wash }} times — time to wash it."
```

## Privacy

All data lives in Home Assistant's local storage
(`.storage/wardrobe_states`). Nothing leaves your network.

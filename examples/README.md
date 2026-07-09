# Wardrobe — front-end examples

Ready-to-adapt Home Assistant automations and dashboard cards for the
`wardrobe` integration. These are **config examples**, not part of the
integration itself — copy them into your HA config and tweak the entity ids /
notify service to match your setup.

| File | What it does |
| --- | --- |
| [`automation_item_needs_wash.yaml`](automation_item_needs_wash.yaml) | Actionable push alert when an item hits its wear threshold, with a **Put in laundry** button that moves that item to the `laundry` state. |
| [`automation_load_ready.yaml`](automation_load_ready.yaml) | Alert when a laundry load of any type is full, with a **Mark load washed** button. |
| [`dashboard_item_card.yaml`](dashboard_item_card.yaml) | A single card showing state, quick actions, statistics and all metadata for one garment. |
| [`scan_to_focus.yaml`](scan_to_focus.yaml) | Scan-to-focus: a scan stores the item in a helper and opens its dashboard on the scanning phone (instead of mutating state). |
| [`dashboard_focused_item_view.yaml`](dashboard_focused_item_view.yaml) | The dashboard view that follows the scan helper — always shows the last-scanned item, with Wore it / Laundry / Washed buttons. |

## Before you start

1. **Actionable notifications need the Companion app.** Every file references
   `notify.mobile_app_your_phone` — find & replace it with your device's notify
   service (Developer Tools → Actions → search `notify.mobile_app_`).
2. **Automations** go in `automations.yaml` (or paste each block via
   Settings → Automations → ⋮ → Edit in YAML). They use the classic
   `trigger:`/`condition:`/`action:` + `service:` keys, which load on every
   supported core (HA 2024.3+).
3. **The card** goes into a dashboard view — see the header comment in
   `dashboard_item_card.yaml`.

## Entity-id conventions

The integration uses `has_entity_name`, so every entity id is
`<platform>.<device name slugified>_<suffix>`.

**Per item** — device name is the item's name (e.g. *Blue Jeans* → `blue_jeans`):

| Entity | Suffix |
| --- | --- |
| State dropdown | `select.<slug>_state` |
| Needs-washing flag | `binary_sensor.<slug>_needs_washing` |
| "I wore this" / "Washed" buttons | `button.<slug>_i_wore_this`, `button.<slug>_washed` |
| Wears per wash (threshold) | `number.<slug>_wears_per_wash_cycle` |
| Counters | `sensor.<slug>_wears_since_wash`, `_total_wears`, `_wash_count` |
| Timestamps | `sensor.<slug>_last_worn`, `_last_washed`, `_last_state_change` |
| Cost per wear (only if a price was set) | `sensor.<slug>_cost_per_wear` |

All the optional metadata (brand, size, colour, material, seasons, location,
purchase date/price, notes, category, laundry type, NFC tag) is exposed as
**attributes on the `select.<slug>_state` entity**, which is why the card can
render them without extra entities.

**Summary hub** — device *Wardrobe Summary* (`wardrobe_summary`):

| Entity | Example |
| --- | --- |
| Load-ready flags (per type) | `binary_sensor.wardrobe_summary_dark_load_ready` |
| Load size sensors | `sensor.wardrobe_summary_dark_load` |
| State counts | `sensor.wardrobe_summary_clean_items`, `_worn_items`, `_items_in_laundry_basket`, `_items_being_washed`, `_total_items`, `_items_needing_wash` |
| Complete-wash buttons | `button.wardrobe_summary_complete_wash_cycle`, `..._complete_dark_wash` |

Laundry types: `dark`, `light`, `color`, `delicates`, `wool`, `hand_wash`.

## Scan-to-focus flow

`scan_to_focus.yaml` + `dashboard_focused_item_view.yaml` turn an NFC scan into
"focus this item and open its dashboard" instead of blindly changing state:

1. Set each item's scan action to **"Open its dashboard (don't change state)"**
   (item device → Configure → Tracking). Added in the integration alongside a
   new `wardrobe_item_scanned` event.
2. On scan, the integration fires `wardrobe_item_scanned` with the item's
   `entry_id`, `name`, the resolved `entity_id` (its `select.*_state`) and the
   scanning `device_id`.
3. The automation writes that `entity_id` into
   `input_text.wardrobe_focused_item` and sends the scanning phone a Companion
   `command_webview` command to open `/wardrobe/item`.
4. The `config-template-card` view derives every entity id for that item from
   the helper, so the dashboard always reflects the last-scanned garment. Its
   buttons call `wardrobe.mark_worn` / `wardrobe.set_state` / `wardrobe.mark_washed`
   on the focused item.

> `wardrobe_item_scanned` fires for **every** scan action, not just `open`, so
> you can keep `cycle`/`mark_worn` and still get the dashboard to follow along —
> the scan will just also mutate state. `command_webview` auto-navigation is
> Android-only; on iOS the helper still updates (park a tablet on the view, or
> swap the notify step for a tap-through notification).

## How the item alert finds the right entity

`automation_item_needs_wash.yaml` triggers on the integration's
`wardrobe_needs_wash` event, which carries the item's `entry_id` (its
ConfigEntry id) and `name`. A template maps that `entry_id` to the item's
`select.*_state` entity via `config_entry_id()`, so **one automation covers
every item** — current and future — with no per-item editing. The resolved
entity id is encoded in the notification action so the button handler knows
exactly which garment to move.

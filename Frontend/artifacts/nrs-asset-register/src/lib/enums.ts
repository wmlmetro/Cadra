/**
 * Every enum the back end owns, in one place.
 *
 * WHY THIS MODULE EXISTS
 * ----------------------
 * It replaces five hand-maintained copies of sets the Odoo model defines, all
 * five of which had drifted, and none of which ever said a word about it:
 *
 *   - `priority` was shifted one whole step. The form displayed "Normal" and
 *     wrote `"2"`, which the model calls **High**, so every request created
 *     without touching the dropdown was filed a level above what the user saw.
 *   - `location_type` offered `state` and `office`, which the model does not
 *     have (saving either raised), and omitted `wing`, which it does — so a
 *     wing loaded for edit showed a blank select and could not be saved back
 *     unchanged.
 *   - `domain` was a free-text input whose placeholder advertised `nrs.fcs`,
 *     a value that is not in the set and not even the right shape — while the
 *     correct eight-value list already sat two exports away in dataProvider.
 *   - `asset_level` was missing `group`, so a group-level asset silently
 *     demoted itself if anybody opened the dropdown.
 *   - `fuel_type` collapsed nine model values onto three labels, rendering
 *     `electric` and both plug-in hybrids as **CNG**.
 *
 * They are all one defect: a front end that declares a set the back end owns.
 * Correcting the five copies would have left the mechanism that produced them
 * intact, so this module is the fix and the corrections are a side effect.
 *
 * THE SETS ARE READ, NOT DECLARED
 * -------------------------------
 * `GET /api/v1/meta/enums` derives every set below from the live Odoo
 * Selection at request time (`utils.selection_values`), so a value the model
 * gains is offered by this front end the same day, with no release. Use the
 * `useEnum` hook in `hooks/useEnums.ts` — that is the live set.
 *
 * What follows is the SEED: what the app renders before that request resolves
 * and what it falls back to if the request fails. A seed that silently rotted
 * is the whole problem, so it does not get to rot quietly —
 * `tests/test_frontend_enums.py` parses this file and the Odoo model source
 * and FAILS when they disagree. That guard is the real deliverable. Editing a
 * list here without editing the model breaks the build, and so does the
 * reverse.
 *
 * If you are adding a value: add it to the model, run the guard, and it will
 * tell you this file is stale. Then fix this file.
 */

export interface EnumOption {
  /** The technical key the API stores and accepts. */
  value: string;
  /** The model's own label, shown to users. */
  label: string;
}

/**
 * The seed sets, keyed by the name `/api/v1/meta/enums` publishes.
 *
 * ORDER IS THE MODEL'S ORDER and is load-bearing for `priority`, where the
 * keys are numeric strings that read like a scale. Do not sort these.
 */
export const ENUM_SEED = {
  /**
   * `request.request.priority` — myservice_request_core/models/request_request.py
   *
   * Read the labels before you touch anything here. `"2"` is **High**, not
   * Normal. The model's own default is `"1"`, and the form's default must be
   * the same value, not the same *position*.
   */
  priority: [
    { value: "0", label: "Low" },
    { value: "1", label: "Normal" },
    { value: "2", label: "High" },
    { value: "3", label: "Critical" },
    { value: "4", label: "Very Urgent" },
  ],

  /** `generic.location.location_type` — crnd-19/generic_location/models/generic_location.py */
  location_type: [
    { value: "building", label: "Building" },
    { value: "floor", label: "Floor" },
    { value: "wing", label: "Wing" },
    { value: "room", label: "Room" },
    { value: "zone", label: "Zone" },
  ],

  /** `nrs.asset.asset_level` — myservice_asset_register/models/asset.py */
  asset_level: [
    { value: "group", label: "Asset Group" },
    { value: "asset", label: "Asset" },
    { value: "sub_asset", label: "Sub-Asset" },
    { value: "component", label: "Component" },
  ],

  /**
   * `nrs.asset.domain` — a related field onto `nrs.asset.category.domain`,
   * which is where the Selection is actually declared.
   */
  domain: [
    { value: "building", label: "Building Services" },
    { value: "plant", label: "Plant & Machinery" },
    { value: "plumbing", label: "Plumbing & Drainage" },
    { value: "fleet", label: "Fleet" },
    { value: "security", label: "Security & Safety" },
    { value: "it", label: "IT & Communications" },
    { value: "furniture", label: "Furniture & Fittings" },
    { value: "other", label: "Other" },
  ],

  /** `nrs.asset.condition` — myservice_asset_register/models/asset.py */
  condition: [
    { value: "new", label: "New" },
    { value: "good", label: "Good" },
    { value: "fair", label: "Fair" },
    { value: "poor", label: "Poor" },
    { value: "decommissioned", label: "Decommissioned" },
  ],

  /** `nrs.asset.state` — myservice_asset_register/models/asset.py */
  asset_state: [
    { value: "active", label: "Active" },
    { value: "in_repair", label: "Under Repair" },
    { value: "disposed", label: "Disposed" },
    { value: "transferred", label: "Transferred" },
    { value: "missing", label: "Missing" },
  ],

  /**
   * `fleet.vehicle.fuel_type` — Odoo core, mirrored by `_FUEL_TYPES` in
   * myservice_api/controllers/v1_fleet.py, which is the published fallback
   * the guard compares against.
   *
   * Nine values. The old front end had three, and mapped six of the nine —
   * including `electric` — onto "CNG" with a regex. A fleet manager reading
   * fuel type off that screen was told something flatly untrue about the
   * vehicle, which is why there is no "display grouping" here any more:
   * the model's label is the label.
   */
  fuel_type: [
    { value: "diesel", label: "Diesel" },
    { value: "gasoline", label: "Gasoline" },
    { value: "full_hybrid", label: "Full Hybrid" },
    { value: "plug_in_hybrid_diesel", label: "Plug-in Hybrid Diesel" },
    { value: "plug_in_hybrid_gasoline", label: "Plug-in Hybrid Gasoline" },
    { value: "cng", label: "CNG" },
    { value: "lpg", label: "LPG" },
    { value: "hydrogen", label: "Hydrogen" },
    { value: "electric", label: "Electric" },
  ],
} satisfies Record<string, EnumOption[]>;

export type EnumName = keyof typeof ENUM_SEED;

/**
 * The value a blank form starts on, taken from the MODEL's default rather
 * than from the first option or from a position in the list.
 *
 * `priority` is here because getting it wrong is what this handoff was
 * about: the form defaulted to `"2"` believing it was the middle of five,
 * and `"2"` is High. A default is a value, not an index.
 */
export const ENUM_DEFAULT = {
  priority: "1",
  asset_level: "asset",
  condition: "good",
  asset_state: "active",
} satisfies Partial<Record<EnumName, string>>;

/** Key → label for one set. Unknown keys pass through unchanged, so a value
 *  the model gained before this build shows as its key rather than vanishing. */
export function enumLabel(
  options: readonly EnumOption[],
  value: string | null | undefined,
): string {
  if (!value) return "";
  return options.find((o) => o.value === value)?.label ?? value;
}

/**
 * `options`, with `value` appended if the live set does not contain it.
 *
 * A `<select>` whose `value` matches no `<option>` renders BLANK, and the next
 * interaction writes some other value back — so a record can be silently
 * retyped by the act of being opened and saved. That is not hypothetical: it
 * is exactly what the old hard-coded `location_type` list did to every wing in
 * the register, which had no `wing` option to match.
 *
 * The appended entry is labelled with its own key, because there is no label
 * to be had for a value this build has never seen. Showing the raw key is the
 * honest answer; showing nothing is how the record got lost.
 */
export function withCurrent(
  options: readonly EnumOption[],
  value: string | null | undefined,
): EnumOption[] {
  if (!value || options.some((o) => o.value === value)) return [...options];
  return [...options, { value, label: value }];
}

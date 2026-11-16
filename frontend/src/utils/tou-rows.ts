/**
 * Wire-format helpers for tariff rule rows (the rooms/save `tou_overrides`
 * payload). The server stores thin references and strips any `definition`
 * before writing the room; the card stages definitions client-side and sends
 * them on the row while the rule is being created or edited. These helpers
 * pin the emitted shape to what the production schema accepts
 * (websocket_api.ROOM_SAVE_SCHEMA + _TOU_RULE_DEF_FIELDS) — one source of
 * truth for the round trip, testable without a DOM.
 */
import type { TouOverrideRow, TouRuleDef } from "../types";

/** Keys a row may carry on the wire; anything else is editor-local state. */
const ROW_WIRE_KEYS = ["id", "rule_id", "enabled", "definition"];

/** Keys a staged definition may carry; the library owns the rule id. */
export const DEF_WIRE_KEYS = [
  "name",
  "tier",
  "edge",
  "action",
  "heat",
  "cool",
  "until",
  "minutes",
  "clock",
  "days",
  "between",
];

/** The thin reference the server persists. */
export function thinRow(row: TouOverrideRow): TouOverrideRow {
  return { id: row.id, rule_id: row.rule_id, enabled: row.enabled ?? true };
}

/** A row with its staged definition; the definition never carries an id. */
export function rowPayload(row: TouOverrideRow, def: TouRuleDef): TouOverrideRow {
  const entries = Object.entries(def).filter(
    ([key, value]) => DEF_WIRE_KEYS.includes(key) && value !== undefined,
  );
  return { ...thinRow(row), definition: Object.fromEntries(entries) as TouRuleDef };
}

/** Normalize one row for the wire: thin when nothing is staged. */
export function wireRow(row: TouOverrideRow): TouOverrideRow {
  return row.definition ? rowPayload(row, row.definition) : thinRow(row);
}

/** The rows payload the card sends. Unknown keys never leave the client. */
export function wireRows(rows: TouOverrideRow[]): TouOverrideRow[] {
  return rows.map(wireRow);
}

/** True when the object carries only wire-legal row keys (schema test hook). */
export function matchesRowWireShape(value: Record<string, unknown>): boolean {
  return Object.keys(value).every((key) => ROW_WIRE_KEYS.includes(key));
}

import { describe, expect, test } from "vitest";
import type { TouOverrideRow, TouRuleDef } from "../types";
import { DEF_WIRE_KEYS, matchesRowWireShape, thinRow, wireRow, wireRows } from "./tou-rows";

/**
 * Round-trip guards: every row the card emits must validate against the
 * production `roommind/rooms/save` schema for `tou_overrides` (see
 * websocket_api.ROOM_SAVE_SCHEMA and the upsert tests in
 * tests/test_websocket_api.py, which feed the shapes asserted here).
 */

const definition: TouRuleDef = {
  name: "Warm by nine",
  tier: "ultra_low",
  edge: "end",
  action: "arrive",
  heat: 20.0,
  cool: null,
  until: "tier_window",
  minutes: 0,
  clock: "09:00",
  days: [],
  between: null,
};

describe("tou row payloads", () => {
  test("a row without a staged definition is a thin reference", () => {
    const row: TouOverrideRow = {
      id: "row1",
      rule_id: "rl1",
      enabled: true,
      definition,
    };
    // The editor keeps the definition only while staging; clearing it leaves
    // exactly the keys the server persists (and the poll echoes back).
    expect(thinRow(row)).toEqual({ id: "row1", rule_id: "rl1", enabled: true });
    expect(Object.keys(thinRow(row)).sort()).toEqual(["enabled", "id", "rule_id"]);
  });

  test("enabled defaults to true on the wire", () => {
    const row: TouOverrideRow = { id: "r", rule_id: "shared" };
    expect(thinRow(row).enabled).toBe(true);
  });

  test("a staged definition rides the row without a library id", () => {
    // The card may echo the library entry's id while editing; ids are
    // library-owned and the schema rejects the echo.
    const staged = { ...definition, id: "rl1", stray: 1 } as TouRuleDef;
    const out = wireRow({ id: "row1", rule_id: "rl1", enabled: true, definition: staged });
    expect(out.definition).toBeDefined();
    expect(Object.keys(out.definition!).every((k) => DEF_WIRE_KEYS.includes(k))).toBe(true);
    expect((out.definition as unknown as Record<string, unknown>).id).toBeUndefined();
    expect(out.definition!.name).toBe("Warm by nine");
    expect(out.definition!.clock).toBe("09:00");
    expect(matchesRowWireShape(out as unknown as Record<string, unknown>)).toBe(true);
  });

  test("rows the editor saves round-trip through the wire format unchanged", () => {
    const rows: TouOverrideRow[] = [
      { id: "row-cool", rule_id: "rl-cool", enabled: true },
      { id: "row-nine", rule_id: "rl-nine", enabled: true, definition },
    ];
    const sent = wireRows(rows);
    // Re-sending what a save would produce yields the identical payload:
    // after the server strips definitions and the poll echoes thin rows,
    // nothing about the staged row changes shape-wise a second time.
    expect(sent[0]).toEqual({ id: "row-cool", rule_id: "rl-cool", enabled: true });
    expect(sent[1]!.definition).toEqual(definition);
    const again = wireRows(sent);
    expect(again[0]).toEqual(sent[0]);
    expect(again[1]!.definition).toEqual(sent[1]!.definition);
    expect(again.every((r) => matchesRowWireShape(r as unknown as Record<string, unknown>))).toBe(
      true,
    );
  });
});

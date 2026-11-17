import { describe, expect, test } from "vitest";
import type { TouLimits, TouRoomLimits } from "../types";
import { effectiveLimits } from "./tou-limits";

const GLOBAL: TouLimits = {
  heat_min: 17.0,
  heat_max: 28.0,
  cool_min: 18.0,
  cool_max: 30.0,
  swing: 3.0,
  store_gap: 1.0,
};

describe("effective store limits", () => {
  test("blank overrides inherit every global value", () => {
    expect(effectiveLimits(GLOBAL, {})).toEqual(GLOBAL);
    expect(effectiveLimits(GLOBAL, { heat_min: null, swing: null })).toEqual(GLOBAL);
  });

  test("an override wins for its key alone", () => {
    const room: TouRoomLimits = { heat_min: 15.5, store_gap: 2.0 };
    const eff = effectiveLimits(GLOBAL, room);
    expect(eff.heat_min).toBe(15.5);
    expect(eff.store_gap).toBe(2.0);
    expect(eff.heat_max).toBe(GLOBAL.heat_max);
    expect(eff.cool_min).toBe(GLOBAL.cool_min);
    expect(eff.cool_max).toBe(GLOBAL.cool_max);
    expect(eff.swing).toBe(GLOBAL.swing);
  });

  test("zero is a real override, not a blank", () => {
    // swing 0 means "never deviate": falsiness must not read as inherit.
    const eff = effectiveLimits(GLOBAL, { swing: 0 });
    expect(eff.swing).toBe(0);
  });

  test("never mutates the inputs", () => {
    const room: TouRoomLimits = { swing: 1 };
    effectiveLimits(GLOBAL, room);
    expect(GLOBAL.swing).toBe(3.0);
    expect(room).toEqual({ swing: 1 });
  });
});

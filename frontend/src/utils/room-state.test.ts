import { describe, expect, test } from "vitest";
import type { RoomConfig, RoomLiveData } from "../types";
import { hintText, roomHints, type RoomHintContext } from "./room-state";

const ctx: RoomHintContext = {
  climateControlActive: true,
  controlMode: "mpc",
  language: "de",
  displayDelta: (d) => d,
  formatTemp: (c) => c.toFixed(1).replace(".", ","),
  unit: "°C",
  now: new Date(2026, 10, 12, 5, 0).getTime(),
};

function room(live: Partial<RoomLiveData>): RoomConfig {
  return {
    temperature_sensor: "sensor.t",
    live: { mode: "idle", mpc_active: true, mold_risk_level: "ok", ...live } as RoomLiveData,
  } as RoomConfig;
}

const sixAm = new Date(2026, 10, 12, 6, 0).getTime() / 1000;

describe("roomHints pre-heat", () => {
  test("names the target and the start while the room heats ahead", () => {
    const hints = roomHints(
      room({ mode: "heating", preheat: { mode: "heating", target: 21.5, at: sixAm } }),
      "controlled",
      ctx,
    );
    const hint = hints.find((h) => h.id === "preheat");
    expect(hint).toBeDefined();
    expect(hintText(hint!, "de")).toBe("Heizt vor auf 21,5 °C ab 06:00");
  });

  test("pre-cooling has its own text", () => {
    const hints = roomHints(
      room({ mode: "cooling", preheat: { mode: "cooling", target: 24, at: sixAm } }),
      "controlled",
      ctx,
    );
    expect(
      hintText(
        hints.find((h) => h.id === "preheat")!,
        "en",
      ),
    ).toBe("Cooling ahead for 24,0 °C from 06:00");
  });

  test("no hint without a pre-heat or once the room stopped", () => {
    expect(roomHints(room({ mode: "heating" }), "controlled", ctx).map((h) => h.id)).not.toContain(
      "preheat",
    );
    const stale = room({ mode: "idle", preheat: { mode: "heating", target: 21.5, at: sixAm } });
    expect(roomHints(stale, "controlled", ctx).map((h) => h.id)).not.toContain("preheat");
  });
});

describe("roomHints setback (#509)", () => {
  const ids = (r: RoomConfig) => roomHints(r, "controlled", ctx).map((h) => h.id);
  const setbackText = (r: RoomConfig) =>
    hintText(
      roomHints(r, "controlled", ctx).find((h) => h.id === "setback")!,
      "de",
    );

  test("counts down to the earliest switch-off", () => {
    const until = Date.now() / 1000 + 25 * 60;
    expect(setbackText(room({ setback: { devices: ["climate.ac"], until } }))).toBe(
      "Absenkung, aus in 25\u00a0min ohne Bedarf",
    );
  });

  test("without a time, or once it passed, the device just stays on", () => {
    expect(setbackText(room({ setback: { devices: ["climate.ac"], until: null } }))).toBe(
      "Absenkung, bleibt an",
    );
    const past = Date.now() / 1000 - 60;
    expect(setbackText(room({ setback: { devices: ["climate.ac"], until: past } }))).toBe(
      "Absenkung, bleibt an",
    );
  });

  test("does not push the more important hints out of the tile's first place", () => {
    const r = room({
      setback: { devices: ["climate.ac"], until: null },
      compressor_protection_until: Date.now() / 1000 + 600,
      compressor_protection_reason: "min_off",
      occupancy_vacant: true,
      mold_prevention_active: true,
      mold_prevention_delta: 1,
      price_shift_heat: -1,
    });
    expect(ids(r)).toEqual([
      "compressor",
      "room_vacant",
      "mold_prevention",
      "price_shift",
      "setback",
    ]);
  });

  test("no hint without a held device or while the room runs", () => {
    expect(ids(room({ setback: null }))).not.toContain("setback");
    expect(ids(room({ setback: { devices: [], until: null } }))).not.toContain("setback");
    expect(
      ids(room({ mode: "heating", setback: { devices: ["climate.ac"], until: null } })),
    ).not.toContain("setback");
  });
});

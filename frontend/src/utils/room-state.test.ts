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

describe("roomHints air quality (#267)", () => {
  test("names the CO2 reading and comes right after the mold risk", () => {
    const hints = roomHints(
      room({
        mold_risk_level: "warning",
        window_open: true,
        co2: 1349.6,
        air_quality_bad: true,
        air_quality_reason: "co2",
      }),
      "controlled",
      ctx,
    );
    expect(hints.map((h) => h.id).slice(0, 3)).toEqual(["mold_risk", "air_quality", "window_open"]);
    expect(hintText(hints[1], "de")).toBe("CO₂ 1.350 ppm, bitte lüften");
  });

  test("says when RoomMind ventilates, and VOC has no figure", () => {
    const venting = roomHints(
      room({
        co2: 1100,
        air_quality_bad: true,
        air_quality_reason: "co2",
        ventilation_active: true,
      }),
      "controlled",
      ctx,
    );
    expect(hintText(venting[0], "de")).toBe("CO₂ 1.100 ppm, Lüftung läuft");
    const voc = roomHints(
      room({ voc: 300, air_quality_bad: true, air_quality_reason: "voc" }),
      "sensor",
      ctx,
    );
    expect(voc.map((h) => h.id)).toEqual(["air_quality"]);
    expect(hintText(voc[0], "de")).toBe("Luft belastet, bitte lüften");
  });

  test("no hint while the air is good", () => {
    const hints = roomHints(room({ co2: 900, air_quality_bad: false }), "controlled", ctx);
    expect(hints.map((h) => h.id)).not.toContain("air_quality");
  });
});

describe("roomHints humidity (#518, #526)", () => {
  test("too humid comes after the air quality and names what runs", () => {
    const hints = roomHints(
      room({
        current_humidity: 72.4,
        humidity_high: true,
        co2: 1100,
        air_quality_bad: true,
        air_quality_reason: "co2",
      }),
      "controlled",
      ctx,
    );
    expect(hints.map((h) => h.id).slice(0, 2)).toEqual(["air_quality", "humidity"]);
    expect(hintText(hints[1], "de")).toBe("Luftfeuchte 72 %, zu feucht");
    expect(hints[1].severity).toBe("warn");
    const dehum = roomHints(
      room({ current_humidity: 65, humidity_high: true, dehumidifier_active: true }),
      "sensor",
      ctx,
    );
    expect(hintText(dehum[0], "de")).toBe("Luftfeuchte 65 %, Entfeuchter läuft");
    expect(dehum[0].severity).toBe("info");
    const vent = roomHints(
      room({
        current_humidity: 80,
        humidity_high: true,
        humidity_ventilate: true,
        ventilation_active: true,
      }),
      "controlled",
      ctx,
    );
    expect(hintText(vent[0], "de")).toBe("Luftfeuchte 80 %, Lüftung läuft");
  });

  test("an air conditioner drying the room (#440)", () => {
    const hints = roomHints(
      room({ current_humidity: 68, humidity_high: true, ac_dry_active: true }),
      "controlled",
      ctx,
    );
    expect(hintText(hints[0], "de")).toBe("Luftfeuchte 68 %, Klimaanlage entfeuchtet");
    expect(hints[0].severity).toBe("info");
  });

  test("outdoor air wetter, too dry and fine", () => {
    const wetter = roomHints(
      room({ current_humidity: 66, humidity_high: true, humidity_vent_blocked: true }),
      "controlled",
      ctx,
    );
    expect(hintText(wetter[0], "de")).toBe("Luftfeuchte 66 %, draußen feuchter");
    const dry = roomHints(
      room({ current_humidity: null, humidity_low: true, humidifier_active: true }),
      "controlled",
      ctx,
    );
    expect(hintText(dry[0], "de")).toBe("Luftfeuchte – %, Befeuchter läuft");
    const low = roomHints(room({ current_humidity: 35, humidity_low: true }), "controlled", ctx);
    expect(hintText(low[0], "de")).toBe("Luftfeuchte 35 %, zu trocken");
    expect(roomHints(room({ current_humidity: 50 }), "controlled", ctx)).toEqual([]);
  });
});

describe("roomHints all in the same mode (#533)", () => {
  test("a room its group holds names the way the outdoor unit runs, not a compressor timer", () => {
    const held = room({
      compressor_protection_active: true,
      compressor_protection_reason: "uniform_mode",
      compressor_protection_until: null,
      uniform_group_mode: "heat",
    });
    const hints = roomHints(held, "controlled", ctx);
    expect(hints.map((h) => h.id)).toEqual(expect.arrayContaining(["uniform_mode"]));
    expect(hints.map((h) => h.id)).not.toContain("compressor");
    expect(
      hintText(
        hints.find((h) => h.id === "uniform_mode")!,
        "de",
      ),
    ).toBe("Außeneinheit heizt");
  });

  test("while the group switches", () => {
    const switching = room({
      compressor_protection_reason: "uniform_mode",
      uniform_group_mode: null,
    });
    const hint = roomHints(switching, "controlled", ctx).find((h) => h.id === "uniform_mode");
    expect(hintText(hint!, "en")).toBe("Outdoor unit switching");
  });
});

describe("roomHints room fan (#266)", () => {
  const ids = (r: RoomConfig) => roomHints(r, "controlled", ctx).map((h) => h.id);

  test("comes last, after every other hint", () => {
    const r = room({ mode: "heating", room_fan_active: true, window_open: true });
    expect(ids(r)).toEqual(["window_open", "room_fan"]);
    const hint = roomHints(r, "controlled", ctx).find((h) => h.id === "room_fan")!;
    expect(hint.severity).toBe("info");
    expect(hintText(hint, "de")).toBe("Raumlüfter läuft");
  });

  test("no hint while RoomMind does not run it", () => {
    expect(ids(room({ mode: "heating", room_fan_active: false }))).not.toContain("room_fan");
    expect(ids(room({ mode: "heating" }))).not.toContain("room_fan");
  });
});

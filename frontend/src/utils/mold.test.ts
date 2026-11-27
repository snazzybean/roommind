import { describe, expect, test } from "vitest";
import type { HomeAssistant } from "../types";
import { moldDeltaText, moldIntensityLabel, moldPreventionDelta } from "./mold";

const hass = (unit: "°C" | "°F", language = "en") =>
  ({ language, config: { unit_system: { temperature: unit } } }) as unknown as HomeAssistant;

describe("mold prevention intensity", () => {
  test("deltas match the backend, unknown falls back to medium", () => {
    expect(moldPreventionDelta("light")).toBe(1);
    expect(moldPreventionDelta("medium")).toBe(2);
    expect(moldPreventionDelta("strong")).toBe(3);
    expect(moldPreventionDelta("")).toBe(2);
  });

  test("delta in the user's unit", () => {
    expect(moldDeltaText("light", hass("°C"))).toBe("1");
    expect(moldDeltaText("medium", hass("°F"))).toBe("3.6");
    expect(moldDeltaText("medium", hass("°F", "de"))).toBe("3,6");
  });

  test("label names the level and the raise", () => {
    expect(moldIntensityLabel("strong", hass("°C"), "en")).toBe("Strong (+3\u00a0°C)");
    expect(moldIntensityLabel("bogus", hass("°C"), "de")).toBe("Mittel (+2\u00a0°C)");
  });
});

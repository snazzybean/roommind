import { describe, expect, test } from "vitest";
import type { DeviceConfig, HomeAssistant } from "../types";
import { deviceAbilities, modeFits } from "./device-utils";

const ac = (entity_id: string) => ({ entity_id, type: "ac", role: "auto" }) as DeviceConfig;
const trv = (entity_id: string) => ({ entity_id, type: "trv", role: "auto" }) as DeviceConfig;

function hassWith(modes: Record<string, string[] | undefined>): Pick<HomeAssistant, "states"> {
  const states: Record<string, unknown> = {};
  for (const [eid, m] of Object.entries(modes)) {
    states[eid] = { entity_id: eid, state: "off", attributes: m ? { hvac_modes: m } : {} };
  }
  return { states } as unknown as Pick<HomeAssistant, "states">;
}

describe("deviceAbilities", () => {
  test("reads heat and cool from the AC's hvac_modes", () => {
    const hass = hassWith({ "climate.ac": ["off", "cool", "dry"] });
    expect(deviceAbilities([ac("climate.ac")], hass)).toEqual({
      heat: false,
      cool: true,
      mixed: false,
    });
  });

  test("a heat pump split heats and cools", () => {
    const hass = hassWith({ "climate.ac": ["off", "heat", "cool"] });
    const ability = deviceAbilities([ac("climate.ac")], hass);
    expect(ability.heat && ability.cool).toBe(true);
  });

  test("modes without any active one count as able, like the backend (#100)", () => {
    const hass = hassWith({ "climate.zone": ["off", "fan_only"] });
    const ability = deviceAbilities([ac("climate.zone")], hass);
    expect(ability).toEqual({ heat: true, cool: true, mixed: false });
    expect(modeFits("heat_only", [ac("climate.zone")], ability)).toBe(true);
  });

  test("a device without state or modes counts as able", () => {
    const ability = deviceAbilities([ac("climate.gone")], hassWith({}));
    expect(ability.heat && ability.cool).toBe(true);
  });

  test("a thermostat heats, never cools", () => {
    const hass = hassWith({ "climate.trv": ["heat"] });
    expect(deviceAbilities([trv("climate.trv")], hass)).toEqual({
      heat: true,
      cool: false,
      mixed: false,
    });
  });
});

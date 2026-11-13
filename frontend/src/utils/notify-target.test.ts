import { describe, expect, test } from "vitest";
import { notifyTargetIcon, notifyTargetName, slugify } from "./notify-target";
import type { HomeAssistant } from "../types";

const hass = (
  states: HomeAssistant["states"] = {},
  devices: HomeAssistant["devices"] = {},
): Pick<HomeAssistant, "states" | "devices"> => ({ states, devices });

describe("slugify", () => {
  test("drops apostrophes and accents like Home Assistant", () => {
    expect(slugify("Alex's iPhone")).toBe("alexs_iphone");
    expect(slugify("Jürgens Größtes Handy")).toBe("jurgens_grosstes_handy");
    expect(slugify("  Pixel 8 Pro ")).toBe("pixel_8_pro");
  });
});

describe("notifyTargetName", () => {
  test("prefers the entity's friendly name", () => {
    const h = hass({
      "notify.kitchen": {
        entity_id: "notify.kitchen",
        state: "",
        attributes: { friendly_name: "Küche" },
      },
    });
    expect(notifyTargetName(h, "notify.kitchen")).toBe("Küche");
  });

  test("names a mobile app service after its phone", () => {
    const h = hass(
      {},
      {
        a: { id: "a", area_id: null, name: "Alex's iPhone" },
        b: { id: "b", area_id: null, name: "Pixel", name_by_user: "Annas Pixel" },
      },
    );
    expect(notifyTargetName(h, "notify.mobile_app_alexs_iphone")).toBe("Alex's iPhone");
    expect(notifyTargetName(h, "notify.mobile_app_annas_pixel")).toBe("Annas Pixel");
  });

  test("falls back to the service name", () => {
    expect(notifyTargetName(hass(), "notify.mobile_app_gone")).toBe("mobile_app_gone");
    expect(notifyTargetName(hass(), "notify.signal")).toBe("signal");
  });
});

test("notifyTargetIcon", () => {
  expect(notifyTargetIcon("notify.mobile_app_x")).toBe("mdi:cellphone");
  expect(notifyTargetIcon("notify.signal")).toBe("mdi:bell-outline");
});

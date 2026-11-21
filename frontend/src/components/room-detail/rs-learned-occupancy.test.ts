// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import "./rs-learned-occupancy";
import { comfortHoursLabel, thresholdLabel, type RsLearnedOccupancy } from "./rs-learned-occupancy";
import type { HomeAssistant } from "../../types";

afterEach(() => document.body.replaceChildren());

const HASS = {
  language: "en",
  areas: { bath: { area_id: "bath", name: "Bathroom" } },
} as unknown as HomeAssistant;

async function dialog(props: Partial<RsLearnedOccupancy>) {
  const element = document.createElement("rs-learned-occupancy");
  Object.assign(element, { hass: HASS, available: true, areas: ["bath", "kitchen"], ...props });
  const events: [string, unknown][] = [];
  for (const name of [
    "learned-schedule-changed",
    "learned-area-changed",
    "learned-threshold-changed",
  ]) {
    element.addEventListener(name, (e) => events.push([name, (e as CustomEvent).detail.value]));
  }
  document.body.append(element);
  await element.updateComplete;
  return { element, events };
}

test("labels use the locale", () => {
  expect(thresholdLabel(0.12, "en")).toBe("12%");
  expect(comfortHoursLabel(76, "en")).toBe("76 h");
});

test("off by default shows only the opt-in switch", async () => {
  const { element } = await dialog({});
  expect(element.shadowRoot!.querySelectorAll("rs-list-row")).toHaveLength(1);
  expect(element.shadowRoot!.querySelector("rs-radio-group")).toBeNull();
});

test("without the integration the switch is disabled", async () => {
  const { element } = await dialog({ available: false });
  const row = element.shadowRoot!.querySelector("rs-list-row")!;
  expect(row.disabled).toBe(true);
});

test("an enabled room lists the areas by name and the live figures", async () => {
  const { element } = await dialog({
    enabled: true,
    areaId: "bath",
    liveThreshold: 0.12,
    comfortHours: 76,
  });
  const group = element.shadowRoot!.querySelector("rs-radio-group")!;
  expect(group.options.map((o) => o.label)).toEqual(["Bathroom", "kitchen"]);
  const values = [...element.shadowRoot!.querySelectorAll("rs-list-row")].map((r) => r.value);
  expect(values).toContain("12%");
  expect(values).toContain("76 h");
  // automatic threshold: no slider
  expect(element.shadowRoot!.querySelector("input[type=range]")).toBeNull();
});

test("switching the automatic threshold off starts from the threshold in force", async () => {
  const { element, events } = await dialog({ enabled: true, areaId: "bath", liveThreshold: 0.12 });
  const auto = element.shadowRoot!.querySelector("rs-list-row.threshold")!;
  auto.dispatchEvent(new CustomEvent("toggle-changed", { detail: false }));
  expect(events).toEqual([["learned-threshold-changed", 0.12]]);
});

test("the slider sends the manual threshold as a share", async () => {
  const { element, events } = await dialog({ enabled: true, areaId: "bath", threshold: 0.3 });
  const slider = element.shadowRoot!.querySelector<HTMLInputElement>("input[type=range]")!;
  expect(slider.value).toBe("30");
  slider.value = "45";
  slider.dispatchEvent(new Event("change"));
  expect(events).toEqual([["learned-threshold-changed", 0.45]]);
});

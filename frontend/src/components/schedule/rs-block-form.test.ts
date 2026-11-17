// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { RsBlockForm, type BlockTempChange } from "./rs-block-form";
import type { HomeAssistant } from "../../types";

afterEach(() => document.body.replaceChildren());

async function form(unit = "°C", heat = 21.7) {
  const el = new RsBlockForm();
  el.hass = { language: "de", config: { unit_system: { temperature: unit } } } as HomeAssistant;
  el.sides = { heat: true, cool: false };
  el.block = { start: 360, end: 480, data: { heat_temperature: heat } };
  el.blockKey = "mon-360";
  const changes: BlockTempChange[] = [];
  el.addEventListener("block-temps", (e) =>
    changes.push((e as CustomEvent<{ temps: BlockTempChange }>).detail.temps),
  );
  document.body.append(el);
  await el.updateComplete;
  const stepper = el.shadowRoot!.querySelector("rs-stepper")!;
  await stepper.updateComplete;
  return { stepper, changes };
}

test("own temperature from YAML is shown exactly and can be typed", async () => {
  const { stepper } = await form();
  expect(stepper.value).toBe(21.7);
  expect(stepper.shadowRoot!.querySelector("input")!.value).toBe("21,7");
});

test("a typed value is stored without snapping to the grid", async () => {
  const { stepper, changes } = await form();
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = "22,3";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
  expect(changes).toEqual([{ heat: 22.3 }]);
});

test("plus moves an exact value to the next grid point in °F", async () => {
  const { stepper, changes } = await form("°F", 70.4);
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(changes).toEqual([{ heat: 71 }]);
});

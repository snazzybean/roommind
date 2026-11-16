// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { render } from "lit";
import { tempRow } from "./temp-row";
import { RsStepper } from "./rs-stepper";
import type { HomeAssistant } from "../../types";

afterEach(() => document.body.replaceChildren());

async function row(unit = "°C", celsius = 21.7) {
  const changes: number[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  render(
    tempRow({
      hass: { language: "de", config: { unit_system: { temperature: unit } } } as HomeAssistant,
      side: "heat",
      label: "Comfort",
      celsius,
      onChange: (v) => changes.push(v),
    }),
    host,
  );
  const stepper = host.querySelector("rs-stepper")!;
  await stepper.updateComplete;
  return { stepper, changes };
}

test("temperature row preserves saved precision and enables exact entry", async () => {
  const { stepper } = await row();
  expect(stepper.value).toBe(21.7);
  const input = stepper.shadowRoot!.querySelector("input")!;
  expect(input).not.toBeNull();
  expect(input.value).toBe("21,7");
  expect(input.getAttribute("aria-label")).toContain("Comfort");
});

test("editable plus preserves the fractional target instead of snapping", async () => {
  const { stepper, changes } = await row();
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(changes).toEqual([22.2]);
});

test.each(["Enter", "blur"])("comma decimal commits once on %s", async (action) => {
  const { stepper, changes } = await row();
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = "22,3";
  input.dispatchEvent(
    action === "blur" ? new Event("blur") : new KeyboardEvent("keydown", { key: action }),
  );
  expect(changes).toEqual([22.3]);
  input.dispatchEvent(new Event("blur"));
  expect(changes).toHaveLength(1);
});

test("Escape cancels without committing on subsequent blur", async () => {
  const { stepper, changes } = await row();
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = "25";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([]);
  expect(input.value).toBe("21,7");
});

test.each(["", " ", "no", "21x", "NaN", "Infinity", "1e2", "4.9", "35.1", "21,2,3"])(
  "rejects invalid target %j without emitting",
  async (text) => {
    const { stepper, changes } = await row();
    const input = stepper.shadowRoot!.querySelector("input")!;
    input.value = text;
    input.dispatchEvent(new Event("blur"));
    expect(changes).toEqual([]);
    expect(input.value).toBe("21,7");
  },
);

test.each([5, 35])("accepts Celsius boundary %s", async (value) => {
  const { stepper, changes } = await row();
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = String(value);
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([value]);
});

test("Fahrenheit preserves precision and converts typed targets to Celsius", async () => {
  const { stepper, changes } = await row("°F");
  expect(stepper.value).toBeCloseTo(71.06);
  expect(stepper.min).toBe(41);
  expect(stepper.max).toBe(95);
  const input = stepper.shadowRoot!.querySelector("input")!;
  expect(input.value).toBe("71,06");
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([]);
  input.value = "72,5";
  input.dispatchEvent(new Event("blur"));
  expect(changes[0]).toBeCloseTo(22.5);
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(changes[1]).toBeCloseTo(22.2555555556);
});

test("disabled entry and buttons cannot emit", async () => {
  const { stepper, changes } = await row();
  stepper.disabled = true;
  await stepper.updateComplete;
  const input = stepper.shadowRoot!.querySelector("input")!;
  expect(input.disabled).toBe(true);
  input.value = "25";
  input.dispatchEvent(new Event("blur"));
  for (const button of stepper.shadowRoot!.querySelectorAll("button")) {
    expect(button.disabled).toBe(true);
    button.click();
  }
  expect(changes).toEqual([]);
});

test("non-editable steppers retain output and step snapping", async () => {
  const stepper = new RsStepper();
  stepper.value = 21.7;
  stepper.step = 0.5;
  document.body.append(stepper);
  await stepper.updateComplete;
  expect(stepper.shadowRoot!.querySelector("input")).toBeNull();
  expect(stepper.shadowRoot!.querySelector("output")!.textContent).toBe("21.7");
  const values: number[] = [];
  stepper.addEventListener("value-changed", (e) => values.push((e as CustomEvent).detail.value));
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(values).toEqual([22]);
});

test.each([5, 35])("buttons cannot exceed target boundary %s", async (celsius) => {
  const { stepper, changes } = await row("°C", celsius);
  const buttons = stepper.shadowRoot!.querySelectorAll("button");
  const button = buttons[celsius === 5 ? 0 : 1];
  expect(button.getAttribute("aria-disabled")).toBe("true");
  button.click();
  expect(changes).toEqual([]);
});

test.each(["21.75", "21,75"])("accepts exact decimals %s without step rounding", async (text) => {
  const { stepper, changes } = await row();
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = text;
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([21.75]);
  stepper.value = changes[0];
  await stepper.updateComplete;
  expect(input.value).toBe("21,75");
});

test.each(["40.9", "95.1"])("rejects Fahrenheit outside range %s", async (text) => {
  const { stepper, changes } = await row("°F");
  const input = stepper.shadowRoot!.querySelector("input")!;
  input.value = text;
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([]);
  expect(input.value).toBe("71,06");
});

test("minus preserves the fractional target", async () => {
  const { stepper, changes } = await row();
  stepper.shadowRoot!.querySelectorAll("button")[0].click();
  expect(changes).toEqual([21.2]);
});

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

test("editable plus moves an exact target to the next grid point", async () => {
  const { stepper, changes } = await row();
  stepper.shadowRoot!.querySelectorAll("button")[1].click();
  expect(changes).toEqual([22]);
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
  expect(changes[1]).toBeCloseTo(22.2222222222);
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

test.each([
  [34.7, 1, 35],
  [5.2, 0, 5],
])("editable boundary step from %s clamps to the endpoint", async (start, index, end) => {
  const { stepper, changes } = await row("°C", start);
  const button = stepper.shadowRoot!.querySelectorAll("button")[index];
  expect(button.getAttribute("aria-disabled")).toBe("false");
  button.focus();
  button.click();
  expect(changes).toEqual([end]);
  stepper.value = end;
  await stepper.updateComplete;
  expect(button.getAttribute("aria-disabled")).toBe("true");
  expect(button.disabled).toBe(false);
  expect(stepper.shadowRoot!.activeElement).toBe(button);
  button.click();
  expect(changes).toEqual([end]);
});

test.each([
  ["°C", "22 °C"],
  ["°F", "72 °F"],
])("editable %s changes have one polite announcement without moving focus", async (unit, text) => {
  const { stepper } = await row(unit);
  const root = stepper.shadowRoot!;
  const regions = root.querySelectorAll('[aria-live="polite"]');
  expect(regions).toHaveLength(1);
  const region = regions[0];
  expect(region.getAttribute("aria-hidden")).not.toBe("true");
  expect(region.classList.contains("sr-only")).toBe(true);
  expect(RsStepper.elementStyles.map(String).join("\n")).toContain(".sr-only");
  expect(region.getAttribute("aria-atomic")).toBe("true");
  expect(root.querySelector("input")!.hasAttribute("aria-live")).toBe(false);
  expect(root.querySelector("input")!.getAttribute("aria-label")).toBe(`Comfort (${unit})`);
  expect(root.querySelector("span[aria-hidden='true']")!.textContent).toBe(unit);
  const button = root.querySelectorAll("button")[1];
  stepper.addEventListener("value-changed", (e) => {
    stepper.value = (e as CustomEvent).detail.value;
  });
  button.focus();
  button.click();
  await stepper.updateComplete;
  expect(root.querySelector('[aria-live="polite"]')).toBe(region);
  expect(region.textContent!.trim()).toBe(text);
  expect(root.activeElement).toBe(button);
});

test.each([
  [34.7, 1],
  [5.2, 0],
])("non-editable boundary guard at %s still rejects a crossing step", async (value, index) => {
  const stepper = new RsStepper();
  Object.assign(stepper, { value, min: 5, max: 35, step: 0.5, display: `${value} °C` });
  document.body.append(stepper);
  await stepper.updateComplete;
  const changes: number[] = [];
  stepper.addEventListener("value-changed", (e) => changes.push((e as CustomEvent).detail.value));
  const button = stepper.shadowRoot!.querySelectorAll("button")[index];
  expect(button.getAttribute("aria-disabled")).toBe("true");
  button.click();
  expect(changes).toEqual([]);
  const regions = stepper.shadowRoot!.querySelectorAll('[aria-live="polite"]');
  expect(regions).toHaveLength(1);
  expect(regions[0].tagName).toBe("OUTPUT");
  expect(regions[0].textContent).toBe(`${value} °C`);
});

test.each([34.7, 5.2])("disabled editable boundary at %s cannot emit", async (value) => {
  const { stepper, changes } = await row("°C", value);
  stepper.disabled = true;
  await stepper.updateComplete;
  for (const button of stepper.shadowRoot!.querySelectorAll("button")) {
    expect(button.disabled).toBe(true);
    button.dispatchEvent(new MouseEvent("click"));
  }
  expect(changes).toEqual([]);
});

test("minus moves an exact target to the previous grid point", async () => {
  const { stepper, changes } = await row();
  stepper.shadowRoot!.querySelectorAll("button")[0].click();
  expect(changes).toEqual([21.5]);
});

test("Escape in a changed entry resets it and keeps the dialog open", async () => {
  const { stepper, changes } = await row();
  const input = stepper.shadowRoot!.querySelector("input")!;
  const reachedWindow: string[] = [];
  const listener = (e: KeyboardEvent) => reachedWindow.push(e.key);
  window.addEventListener("keydown", listener);
  input.value = "25";
  input.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }),
  );
  expect(input.value).toBe("21,7");
  expect(reachedWindow).toEqual([]);
  input.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }),
  );
  expect(reachedWindow).toEqual(["Escape"]);
  window.removeEventListener("keydown", listener);
  expect(changes).toEqual([]);
});

test("an exact value shows at most two decimals and is not written back", async () => {
  const { stepper, changes } = await row("°C", 21.666666666666668);
  const input = stepper.shadowRoot!.querySelector("input")!;
  expect(input.value).toBe("21,67");
  input.dispatchEvent(new Event("blur"));
  expect(changes).toEqual([]);
});

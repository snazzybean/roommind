// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { blurFocusedIn, containsDeep } from "./focus";

afterEach(() => document.body.replaceChildren());

function popWithShadowInput() {
  const pop = document.createElement("div");
  const host = document.createElement("div");
  const input = document.createElement("input");
  host.attachShadow({ mode: "open" }).append(input);
  pop.append(host);
  const outside = document.createElement("input");
  document.body.append(pop, outside);
  return { pop, input, outside };
}

test("containsDeep sees through shadow roots", () => {
  const { pop, input, outside } = popWithShadowInput();
  expect(containsDeep(pop, input)).toBe(true);
  expect(containsDeep(pop, outside)).toBe(false);
});

test("blurFocusedIn commits a field inside and leaves one outside alone", () => {
  const { pop, input, outside } = popWithShadowInput();
  let blurs = 0;
  input.addEventListener("blur", () => blurs++);
  input.focus();
  blurFocusedIn(pop);
  expect(blurs).toBe(1);

  outside.focus();
  blurFocusedIn(pop);
  expect(document.activeElement).toBe(outside);
  blurFocusedIn(null);
  expect(document.activeElement).toBe(outside);
});

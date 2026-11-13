import { describe, expect, test } from "vitest";
import { formatAgo } from "./format";

describe("formatAgo", () => {
  const now = 1_762_000_000;

  test("counts at least one minute", () => {
    expect(formatAgo(now - 5, "en", now)).toBe("1 minute ago");
    expect(formatAgo(now + 30, "de", now)).toBe("vor 1 Minute");
  });

  test("switches to hours and then days", () => {
    expect(formatAgo(now - 59 * 60, "en", now)).toBe("59 minutes ago");
    expect(formatAgo(now - 3 * 3600, "de", now)).toBe("vor 3 Stunden");
    expect(formatAgo(now - 47 * 3600, "en", now)).toBe("47 hours ago");
    expect(formatAgo(now - 3 * 86400, "fr", now)).toBe("il y a 3 jours");
  });
});

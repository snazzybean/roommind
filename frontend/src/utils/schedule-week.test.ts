import { describe, expect, test } from "vitest";
import {
  copyDay,
  dayIsValid,
  emptyWeek,
  parseTime,
  parseWeek,
  serializeWeek,
  splitOverMidnight,
  withTemps,
  type Week,
} from "./schedule-week";

const both = { heat: true, cool: true };
const heatOnly = { heat: true, cool: false };
const coolOnly = { heat: false, cool: true };

describe("withTemps", () => {
  test("a changed side is written, the stored other side stays", () => {
    expect(withTemps({ heat_temperature: 21, cool_temperature: 26 }, { heat: 20 }, both)).toEqual({
      heat_temperature: 20,
      cool_temperature: 26,
    });
    expect(
      withTemps({ heat_temperature: 21, cool_temperature: 26 }, { heat: 22 }, heatOnly),
    ).toEqual({ heat_temperature: 22, cool_temperature: 26 });
  });

  test("a block with only heat does not get cool pinned to comfort", () => {
    expect(withTemps({ heat_temperature: 21 }, { heat: 20 }, both)).toEqual({
      heat_temperature: 20,
    });
  });

  test("a plain temperature moves to every needed side not given", () => {
    expect(withTemps({ temperature: 22 }, { heat: 20 }, both)).toEqual({
      heat_temperature: 20,
      cool_temperature: 22,
    });
    expect(withTemps({ temperature: 22 }, { cool: 25 }, both)).toEqual({
      heat_temperature: 22,
      cool_temperature: 25,
    });
    expect(withTemps({ temperature: 22 }, { heat: 20 }, heatOnly)).toEqual({
      heat_temperature: 20,
    });
    expect(withTemps({ temperature: 22 }, { cool: 25 }, coolOnly)).toEqual({
      cool_temperature: 25,
    });
    expect(withTemps({ temperature: "22" }, { heat: 20 }, both)).toEqual({
      heat_temperature: 20,
      cool_temperature: 22,
    });
  });

  test("an existing side key wins over the plain temperature", () => {
    expect(withTemps({ temperature: 22, cool_temperature: 27 }, { heat: 20 }, both)).toEqual({
      heat_temperature: 20,
      cool_temperature: 27,
    });
  });

  test("comfort drops all three temperature keys and keeps the rest", () => {
    expect(
      withTemps(
        { temperature: 22, heat_temperature: 20, cool_temperature: 26, mode: "x" },
        null,
        both,
      ),
    ).toEqual({ mode: "x" });
    expect(withTemps({ heat_temperature: 20 }, null, both)).toBeUndefined();
  });

  test("unknown keys stay, a band bump writes both sides", () => {
    expect(
      withTemps(
        { fan: "low", heat_temperature: 20, cool_temperature: 22 },
        { heat: 23, cool: 23 },
        both,
      ),
    ).toEqual({ fan: "low", heat_temperature: 23, cool_temperature: 23 });
  });

  test("switching a comfort block to own writes the given sides", () => {
    expect(withTemps(undefined, { heat: 21, cool: 24 }, both)).toEqual({
      heat_temperature: 21,
      cool_temperature: 24,
    });
  });

  test("the input is not mutated", () => {
    const src = { temperature: 22 };
    withTemps(src, { heat: 20 }, both);
    expect(src).toEqual({ temperature: 22 });
  });
});

describe("parseTime / parseWeek / serializeWeek", () => {
  test("both day-end spellings of Home Assistant read as 1440", () => {
    expect(parseTime("24:00:00")).toBe(1440);
    expect(parseTime("23:59:59.999999")).toBe(1440);
    expect(parseTime("06:30:00")).toBe(390);
    expect(parseTime("06:30")).toBe(390);
  });

  test("round trip keeps blocks and data, sorted, all seven days", () => {
    const week = parseWeek({
      monday: [
        { from: "17:00:00", to: "22:00:00", data: { heat_temperature: 21 } },
        { from: "06:00:00", to: "08:00:00" },
      ],
    });
    expect(week[0]).toEqual([
      { start: 360, end: 480 },
      { start: 1020, end: 1320, data: { heat_temperature: 21 } },
    ]);
    const ha = serializeWeek(week);
    expect(Object.keys(ha)).toHaveLength(7);
    expect(ha.monday).toEqual([
      { from: "06:00:00", to: "08:00:00" },
      { from: "17:00:00", to: "22:00:00", data: { heat_temperature: 21 } },
    ]);
    expect(ha.sunday).toEqual([]);
  });
});

describe("week edits", () => {
  const week = (): Week => {
    const w = emptyWeek();
    w[0] = [{ start: 360, end: 480, data: { heat_temperature: 21 } }];
    w[1] = [{ start: 600, end: 660 }];
    return w;
  };

  test("copyDay replaces the targets with a deep copy and skips the source", () => {
    const w = week();
    const out = copyDay(w, 0, [0, 1, 2]);
    expect(out[1]).toEqual(w[0]);
    expect(out[2]).toEqual(w[0]);
    expect(out[0]).toBe(w[0]);
    expect(out[1][0].data).not.toBe(w[0][0].data);
  });

  test("dayIsValid rejects overlaps and empty blocks", () => {
    expect(
      dayIsValid([
        { start: 0, end: 60 },
        { start: 60, end: 120 },
      ]),
    ).toBe(true);
    expect(
      dayIsValid([
        { start: 0, end: 90 },
        { start: 60, end: 120 },
      ]),
    ).toBe(false);
    expect(dayIsValid([{ start: 60, end: 60 }])).toBe(false);
  });

  test("splitOverMidnight wraps Sunday to Monday and refuses overlaps", () => {
    const w = emptyWeek();
    w[6] = [{ start: 1320, end: 1440, data: { heat_temperature: 19 } }];
    const out = splitOverMidnight(w, 6, 0, 1320, 120);
    expect(out?.[6]).toEqual([{ start: 1320, end: 1440, data: { heat_temperature: 19 } }]);
    expect(out?.[0]).toEqual([{ start: 0, end: 120, data: { heat_temperature: 19 } }]);
    w[0] = [{ start: 60, end: 180 }];
    expect(splitOverMidnight(w, 6, 0, 1320, 120)).toBeNull();
  });
});

import { describe, expect, test } from "vitest";
import type { RoomConfig } from "../types";
import { roomNameOf, scheduleUsage, usageText } from "./schedule-usage";

const room = (area_id: string, schedules: string[], covers: string[] = []): RoomConfig =>
  ({
    area_id,
    schedules: schedules.map((entity_id) => ({ entity_id })),
    cover_schedules: covers.map((entity_id) => ({ entity_id, mode: "force" })),
  }) as unknown as RoomConfig;

const rooms = {
  kueche: room("kueche", ["schedule.a"]),
  bad: room("bad", ["schedule.a", "schedule.b"]),
  wohnzimmer: room("wohnzimmer", [], ["schedule.a", "schedule.c"]),
};
const name = (id: string) => id.toUpperCase();

describe("scheduleUsage", () => {
  test("lists the rooms per kind", () => {
    expect(scheduleUsage(rooms, "schedule.a")).toEqual({
      climate: ["kueche", "bad"],
      cover: ["wohnzimmer"],
    });
    expect(scheduleUsage(rooms, "schedule.x")).toEqual({ climate: [], cover: [] });
  });
});

describe("usageText", () => {
  test("overview: the rooms of its kind, the other kind named", () => {
    expect(usageText(rooms, "schedule.a", "climate", name, "de")).toBe(
      "KUECHE, BAD · Rollläden: WOHNZIMMER",
    );
    expect(usageText(rooms, "schedule.c", "cover", name, "en")).toBe("WOHNZIMMER");
  });

  test("a room's dialog leaves the room out and says who else uses it", () => {
    expect(usageText(rooms, "schedule.a", "climate", name, "de", "bad")).toBe(
      "Auch in KUECHE · Rollläden: WOHNZIMMER",
    );
    expect(usageText(rooms, "schedule.b", "climate", name, "de", "bad")).toBe("");
    expect(usageText(rooms, "schedule.a", "cover", name, "en", "wohnzimmer")).toBe(
      "Temperature: KUECHE, BAD",
    );
  });
});

test("roomNameOf prefers the display name, then the area, then the id", () => {
  const nameOf = roomNameOf(
    { a: { area_id: "a", display_name: "Alpha" } as unknown as RoomConfig },
    { b: { name: "Beta" } },
  );
  expect([nameOf("a"), nameOf("b"), nameOf("c")]).toEqual(["Alpha", "Beta", "c"]);
});

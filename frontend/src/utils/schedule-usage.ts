import type { RoomConfig } from "../types";
import { localize } from "./localize";

export type ScheduleKind = "climate" | "cover";

/** Rooms (area ids) using a schedule helper, for the temperature and for the covers. */
export function scheduleUsage(
  rooms: Record<string, RoomConfig>,
  entityId: string,
): Record<ScheduleKind, string[]> {
  const uses = (list: { entity_id: string }[] | undefined) =>
    (list ?? []).some((s) => s.entity_id === entityId);
  const all = Object.values(rooms);
  return {
    climate: all.filter((r) => uses(r.schedules)).map((r) => r.area_id),
    cover: all.filter((r) => uses(r.cover_schedules)).map((r) => r.area_id),
  };
}

/**
 * Where a helper is used, seen from a list of `kind`: "Küche, Bad · Rollläden: Wohnzimmer".
 * With `exceptRoom` (a room's own dialog) that room is left out of its own kind and the rest
 * reads "Auch in Küche, Bad". Empty when nobody else uses it.
 */
export function usageText(
  rooms: Record<string, RoomConfig>,
  entityId: string,
  kind: ScheduleKind,
  nameOf: (areaId: string) => string,
  language: string,
  exceptRoom = "",
): string {
  const usage = scheduleUsage(rooms, entityId);
  const other: ScheduleKind = kind === "climate" ? "cover" : "climate";
  const same = usage[kind].filter((id) => id !== exceptRoom).map(nameOf);
  const elsewhere = usage[other].map(nameOf);
  const parts: string[] = [];
  if (same.length) {
    parts.push(
      exceptRoom
        ? localize("schedules.also_in", language, { rooms: same.join(", ") })
        : same.join(", "),
    );
  }
  if (elsewhere.length) {
    parts.push(
      localize(other === "cover" ? "schedules.covers_in" : "schedules.temperature_in", language, {
        rooms: elsewhere.join(", "),
      }),
    );
  }
  return parts.join(" · ");
}

/** Name of a room as the panel shows it. */
export function roomNameOf(
  rooms: Record<string, RoomConfig>,
  areas: Record<string, { name: string }> | undefined,
): (areaId: string) => string {
  return (id) => rooms[id]?.display_name || areas?.[id]?.name || id;
}

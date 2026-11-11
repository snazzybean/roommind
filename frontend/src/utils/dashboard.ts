/**
 * Dashboard model: which areas show up, in which order, grouped by floor. Pure, shared by the
 * dashboard view and its edit mode.
 */
import type { HassArea, HomeAssistant, RoomConfig } from "../types";
import { getEntitiesForArea } from "./room-state";
import { localize } from "./localize";

export interface AreaInfo {
  area: HassArea;
  config: RoomConfig | null;
  climateEntityCount: number;
  tempSensorCount: number;
}

export interface FloorGroup {
  /** Floor id, "" without grouping, null for areas without a floor. */
  key: string | null;
  name: string;
  items: AreaInfo[];
}

/** All HA areas with their RoomMind config, sorted by `room_order`, then configured first. */
export function computeAreaInfos(
  hass: HomeAssistant,
  rooms: Record<string, RoomConfig>,
  roomOrder: readonly string[],
): AreaInfo[] {
  if (!hass?.areas) return [];
  const infos: AreaInfo[] = Object.values(hass.areas).map((area) => {
    const areaEntities = getEntitiesForArea(area.area_id, hass.entities, hass.devices).filter(
      (e) => !e.entity_id.substring(e.entity_id.indexOf(".") + 1).startsWith("roommind_"),
    );
    return {
      area,
      config: rooms[area.area_id] ?? null,
      climateEntityCount: areaEntities.filter((e) => e.entity_id.startsWith("climate.")).length,
      tempSensorCount: areaEntities.filter(
        (e) =>
          e.entity_id.startsWith("sensor.") &&
          hass.states[e.entity_id]?.attributes?.device_class === "temperature",
      ).length,
    };
  });

  const orderIndex = new Map(roomOrder.map((id, i) => [id, i]));
  infos.sort((a, b) => {
    const aIdx = orderIndex.get(a.area.area_id);
    const bIdx = orderIndex.get(b.area.area_id);
    if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx;
    if (aIdx !== undefined) return -1;
    if (bIdx !== undefined) return 1;
    const aScore = a.config ? 2 : a.climateEntityCount > 0 ? 1 : 0;
    const bScore = b.config ? 2 : b.climateEntityCount > 0 ? 1 : 0;
    if (aScore !== bScore) return bScore - aScore;
    // Sorted by the name the card shows
    const shown = (i: AreaInfo) => i.config?.display_name || i.area.name;
    return shown(a).localeCompare(shown(b));
  });
  return infos;
}

/** Whether HA has any floor; grouping by floor is only offered (and applied) then. */
export function hasFloors(hass: Pick<HomeAssistant, "floors">): boolean {
  return !!hass.floors && Object.keys(hass.floors).length > 0;
}

/** One group without floors; else floors by level (highest first), then name, no floor last. */
export function floorGroups(
  infos: AreaInfo[],
  hass: HomeAssistant,
  groupByFloor: boolean,
): FloorGroup[] {
  if (!groupByFloor || !hasFloors(hass)) return [{ key: "", name: "", items: infos }];
  const floors = hass.floors!;
  const l = hass.language;
  const groups = new Map<string | null, AreaInfo[]>();
  for (const info of infos) {
    const fid = info.area.floor_id ?? null;
    if (!groups.has(fid)) groups.set(fid, []);
    groups.get(fid)!.push(info);
  }
  const keys = [...groups.keys()].sort((a, b) => {
    if (a === null) return 1;
    if (b === null) return -1;
    const fa = floors[a];
    const fb = floors[b];
    if (fa?.level != null && fb?.level != null) return fb.level - fa.level;
    if (fa?.level != null) return -1;
    if (fb?.level != null) return 1;
    return (fa?.name ?? "").localeCompare(fb?.name ?? "");
  });
  return keys.map((key) => ({
    key,
    name:
      key === null
        ? localize("panel.floor_other", l)
        : (floors[key]?.name ?? localize("panel.floor_other", l)),
    items: groups.get(key)!,
  }));
}

/** Full `room_order` after one group got a new order; the other groups keep theirs. */
export function orderWithGroup(
  groups: FloorGroup[],
  groupKey: string | null,
  groupIds: readonly string[],
): string[] {
  return groups.flatMap((g) =>
    g.key === groupKey ? [...groupIds] : g.items.map((i) => i.area.area_id),
  );
}

/** Ids of a group with one id moved by `delta` places; null at the edge. */
export function moveInGroup(ids: readonly string[], id: string, delta: number): string[] | null {
  const idx = ids.indexOf(id);
  const target = idx + delta;
  if (idx === -1 || target < 0 || target >= ids.length) return null;
  const next = [...ids];
  next.splice(idx, 1);
  next.splice(target, 0, id);
  return next;
}

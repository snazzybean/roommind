/**
 * Home Assistant schedule helpers through Home Assistant's own WebSocket commands. Helpers made
 * in the UI live in a storage collection (`schedule/list|create|update|delete`, admin only for
 * writes); YAML helpers are read through the `schedule.get_schedule` service and stay read-only.
 */
import type { HomeAssistant } from "../types";
import { parseWeek, serializeWeek, type HaWeek, type Week } from "./schedule-week";

export interface StorageScheduleItem extends Partial<HaWeek> {
  id: string;
  name: string;
  icon?: string;
}

export interface LoadedSchedule {
  entityId: string;
  /** Storage item id; null for YAML helpers (read-only). */
  itemId: string | null;
  name: string;
  icon?: string;
  week: Week;
}

interface RegistryEntry {
  entity_id: string;
  unique_id: string;
  platform: string;
}

/** Storage helpers carry `editable: true` (also in Home Assistant 2026.5). */
export function isEditableSchedule(hass: HomeAssistant, entityId: string): boolean {
  return hass.states[entityId]?.attributes?.editable === true;
}

export function isAdmin(hass: HomeAssistant): boolean {
  return hass.user?.is_admin === true;
}

/** Schedule entity ids by storage item id (registry unique_id = item id). */
async function scheduleEntityIds(hass: HomeAssistant): Promise<Map<string, string>> {
  const entries = await hass.callWS<RegistryEntry[]>({ type: "config/entity_registry/list" });
  const map = new Map<string, string>();
  for (const e of entries) {
    if (e.platform === "schedule") map.set(e.unique_id, e.entity_id);
  }
  return map;
}

async function readThroughService(hass: HomeAssistant, entityId: string): Promise<Week> {
  const result = await hass.callWS<{ response?: Record<string, Record<string, unknown>> }>({
    type: "call_service",
    domain: "schedule",
    service: "get_schedule",
    target: { entity_id: entityId },
    return_response: true,
  });
  return parseWeek(result.response?.[entityId] ?? {});
}

export async function loadSchedule(hass: HomeAssistant, entityId: string): Promise<LoadedSchedule> {
  const name = (hass.states[entityId]?.attributes?.friendly_name as string) || entityId;
  if (isEditableSchedule(hass, entityId)) {
    const [ids, items] = await Promise.all([
      scheduleEntityIds(hass),
      hass.callWS<StorageScheduleItem[]>({ type: "schedule/list" }),
    ]);
    for (const item of items) {
      if (ids.get(item.id) === entityId) {
        return {
          entityId,
          itemId: item.id,
          name: item.name,
          icon: item.icon,
          week: parseWeek(item as unknown as Record<string, unknown>),
        };
      }
    }
  }
  return { entityId, itemId: null, name, week: await readThroughService(hass, entityId) };
}

/** `update` replaces the whole item: name, icon (dropped if not sent) and all seven days. */
export async function saveSchedule(
  hass: HomeAssistant,
  itemId: string,
  name: string,
  icon: string | undefined,
  week: Week,
): Promise<void> {
  await hass.callWS({
    type: "schedule/update",
    schedule_id: itemId,
    name,
    ...(icon ? { icon } : {}),
    ...serializeWeek(week),
  });
}

/** Creates a storage helper and returns its entity id once the registry knows it. */
export async function createSchedule(
  hass: HomeAssistant,
  name: string,
  week: Week,
): Promise<string> {
  const item = await hass.callWS<StorageScheduleItem>({
    type: "schedule/create",
    name,
    icon: "mdi:calendar-clock",
    ...serializeWeek(week),
  });
  for (let attempt = 0; attempt < 10; attempt++) {
    const entityId = (await scheduleEntityIds(hass)).get(item.id);
    if (entityId) return entityId;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`schedule ${item.id} has no entity`);
}

export async function deleteSchedule(hass: HomeAssistant, itemId: string): Promise<void> {
  await hass.callWS({ type: "schedule/delete", schedule_id: itemId });
}

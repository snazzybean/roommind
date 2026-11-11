/**
 * Shared utilities for reading and formatting RoomMind room state.
 */
import type {
  HassDeviceRegistryEntry,
  HassEntity,
  HassEntityRegistryEntry,
  OverrideType,
  RoomConfig,
  RoomMode,
} from "../types";
import { localize, type TranslationKey } from "./localize";
import type { EffectiveOverride } from "./override";
import { formatMinutes, formatNumber, formatRemaining } from "./format";
import { VACATION_SENTINEL } from "./constants";

/**
 * Resolve the effective area_id for an entity.
 * Entities may have area_id set directly, or inherit it from their device.
 */
function getEntityAreaId(
  entity: HassEntityRegistryEntry,
  devices: Record<string, HassDeviceRegistryEntry> | undefined,
): string | null {
  if (entity.area_id) return entity.area_id;
  if (entity.device_id && devices) {
    const device = devices[entity.device_id];
    if (device?.area_id) return device.area_id;
  }
  return null;
}

/**
 * Get all entities belonging to a specific area (including device-inherited area).
 */
export function getEntitiesForArea(
  areaId: string,
  entities: Record<string, HassEntityRegistryEntry> | undefined,
  devices: Record<string, HassDeviceRegistryEntry> | undefined,
): HassEntityRegistryEntry[] {
  if (!entities) return [];
  return Object.values(entities).filter((e) => getEntityAreaId(e, devices) === areaId);
}

/**
 * Return the CSS class name corresponding to a room mode.
 */
export function getModeClass(mode: RoomMode | undefined): string {
  switch (mode) {
    case "heating":
      return "mode-heating";
    case "cooling":
      return "mode-cooling";
    case "idle":
      return "mode-idle";
    default:
      return "mode-other";
  }
}

const modeKeys: Record<RoomMode, TranslationKey> = {
  heating: "mode.heating",
  cooling: "mode.cooling",
  idle: "mode.idle",
};

/**
 * Format a room mode for display (localized).
 */
export function formatMode(mode: RoomMode, language: string): string {
  return localize(modeKeys[mode], language);
}

/** Whole minutes until a Unix timestamp, floored at 1 so a badge never reads "0 min". */
export function minutesLeft(until: number | null): number {
  if (until == null) return 1;
  return Math.max(1, Math.ceil((until * 1000 - Date.now()) / 60000));
}

/* ---------- Room kind, state and hints (dashboard card, later the room hero) ---------- */

/**
 * What a room is from the dashboard's point of view:
 * - `controlled`: devices configured, live data present
 * - `waiting`: devices configured, no live data yet
 * - `outdoor`: outdoor area (measurement only)
 * - `sensor`: no devices, but a sensor delivers temperature or humidity
 * - `unconfigured`: climate devices in the area, not set up
 * - `empty`: no climate devices in the area
 */
export type RoomKind = "controlled" | "waiting" | "outdoor" | "sensor" | "unconfigured" | "empty";

export function hasDevices(config: RoomConfig | null | undefined): boolean {
  return (
    (config?.devices?.length ?? 0) > 0 ||
    (config?.thermostats?.length ?? 0) > 0 ||
    (config?.acs?.length ?? 0) > 0
  );
}

export function roomKind(config: RoomConfig | null, climateEntityCount: number): RoomKind {
  const live = config?.live;
  const hasReadings = !!live && (live.current_temp !== null || live.current_humidity !== null);
  if (config?.is_outdoor)
    return hasReadings ? "outdoor" : climateEntityCount > 0 ? "unconfigured" : "empty";
  if (config && hasDevices(config)) return live ? "controlled" : "waiting";
  if (hasReadings) return "sensor";
  return climateEntityCount > 0 ? "unconfigured" : "empty";
}

/** RoomMind controls the room: global switch and the room's own switch are on. */
export function isRoomControlled(
  config: RoomConfig | null,
  climateControlActive: boolean,
): boolean {
  return climateControlActive && config?.climate_control_enabled !== false;
}

/** MPC badge state; only for Full Control rooms with MPC selected (Managed never runs MPC). */
export function mpcStatus(
  config: RoomConfig | null,
  controlMode: "mpc" | "bangbang",
): "active" | "learning" | null {
  if (controlMode !== "mpc" || !config?.temperature_sensor || !config.live) return null;
  return config.live.mpc_active ? "active" : "learning";
}

export interface RoomStateInfo {
  key: TranslationKey;
  icon: string;
  tone: "heat" | "cool" | "idle" | "off" | "paused";
  /** Output in percent when partial (0 < p < 100), else null. */
  power: number | null;
}

/** Header state of a controlled room: heats/cools (with output), paused (window), off, standby. */
export function roomStateInfo(config: RoomConfig, climateControlActive: boolean): RoomStateInfo {
  const live = config.live;
  if (!isRoomControlled(config, climateControlActive)) {
    return { key: "card.state.off", icon: "mdi:power-off", tone: "off", power: null };
  }
  if (live?.window_open) {
    return {
      key: "card.state.paused",
      icon: "mdi:pause-circle-outline",
      tone: "paused",
      power: null,
    };
  }
  const p = live?.heating_power ?? 0;
  const power = p > 0 && p < 100 ? Math.round(p) : null;
  if (live?.mode === "heating")
    return { key: "card.state.heating", icon: "mdi:fire", tone: "heat", power };
  if (live?.mode === "cooling") {
    return { key: "card.state.cooling", icon: "mdi:snowflake", tone: "cool", power };
  }
  return { key: "mode.idle", icon: "mdi:circle-small", tone: "idle", power: null };
}

export type RoomHintId =
  | "mold_risk"
  | "window_open"
  | "not_controlled"
  | "override"
  | "compressor"
  | "presence_away"
  | "room_vacant"
  | "mold_prevention"
  | "learning_paused"
  | "mpc_learning";

export interface RoomHint {
  id: RoomHintId;
  icon: string;
  severity: "info" | "warn" | "error";
  key: TranslationKey;
  params?: Record<string, string | number>;
}

export interface RoomHintContext {
  climateControlActive: boolean;
  controlMode: "mpc" | "bangbang";
  language: string;
  /** °C delta in the display unit (°F installs). */
  displayDelta: (celsiusDelta: number) => number;
  unit: string;
  now?: number;
}

const OVERRIDE_TYPE_KEYS: Record<OverrideType, TranslationKey> = {
  boost: "override.comfort",
  eco: "override.eco",
  custom: "override.custom",
};

/** "18:00", or "Fr 18:00" when the time is not today. */
export function formatClock(unixS: number, language: string, now = Date.now()): string {
  const d = new Date(unixS * 1000);
  const sameDay = new Date(now).toDateString() === d.toDateString();
  return new Intl.DateTimeFormat(language, {
    ...(sameDay ? {} : { weekday: "short" }),
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/**
 * Everything worth a hint for a room, most important first: mold risk, window open, not
 * controlled, override (with end), compressor protection, away / room empty, mold
 * prevention, learning. Rooms without control only get the mold risk.
 */
export function roomHints(
  config: RoomConfig | null,
  kind: RoomKind,
  ctx: RoomHintContext,
): RoomHint[] {
  const live = config?.live;
  if (!config || !live) return [];
  const hints: RoomHint[] = [];
  if (live.mold_risk_level === "warning" || live.mold_risk_level === "critical") {
    const critical = live.mold_risk_level === "critical";
    hints.push({
      id: "mold_risk",
      icon: "mdi:water-alert",
      severity: critical ? "error" : "warn",
      key: critical ? "card.mold_critical" : "card.mold_warning",
    });
  }
  if (kind !== "controlled") return hints;

  if (live.window_open) {
    hints.push({
      id: "window_open",
      icon: "mdi:window-open-variant",
      severity: "info",
      key: "hero.window_open",
    });
  }
  if (!isRoomControlled(config, ctx.climateControlActive)) {
    hints.push({
      id: "not_controlled",
      icon: "mdi:power-off",
      severity: "info",
      key: "card.hint.not_controlled",
    });
  }
  if (live.override_active && live.override_type) {
    const type = localize(OVERRIDE_TYPE_KEYS[live.override_type], ctx.language);
    const icon =
      live.override_type === "eco"
        ? "mdi:leaf"
        : live.override_type === "boost"
          ? "mdi:sofa"
          : "mdi:thermometer";
    if (live.override_suppressed) {
      hints.push({
        id: "override",
        icon,
        severity: "info",
        key: "card.hint.override_paused",
        params: { type },
      });
    } else if (live.override_until != null) {
      hints.push({
        id: "override",
        icon,
        severity: "info",
        key: "card.hint.override_until",
        params: { type, time: formatClock(live.override_until, ctx.language, ctx.now) },
      });
    } else {
      hints.push({
        id: "override",
        icon,
        severity: "info",
        key: "card.hint.override_permanent",
        params: { type },
      });
    }
  }
  if (live.compressor_protection_until != null) {
    hints.push({
      id: "compressor",
      icon: "mdi:timer-sand",
      severity: "info",
      key:
        live.compressor_protection_reason === "min_run"
          ? "card.compressor_min_run"
          : "card.compressor_min_off",
      params: { time: formatMinutes(minutesLeft(live.compressor_protection_until), ctx.language) },
    });
  }
  if (live.presence_away) {
    hints.push({
      id: "presence_away",
      icon: "mdi:home-off-outline",
      severity: "info",
      key: "card.presence_away",
    });
  } else if (live.occupancy_vacant && !live.override_active) {
    hints.push({
      id: "room_vacant",
      icon: "mdi:account-off-outline",
      severity: "info",
      key: "card.hint.vacant",
    });
  }
  if (live.mold_prevention_active) {
    hints.push({
      id: "mold_prevention",
      icon: "mdi:shield-check",
      severity: "info",
      key: "card.mold_prevention",
      params: {
        delta: `${formatNumber(ctx.displayDelta(live.mold_prevention_delta), { language: ctx.language })} ${ctx.unit}`,
      },
    });
  }
  if (live.learning_paused_reason) {
    hints.push({
      id: "learning_paused",
      icon: "mdi:school-outline",
      severity: "warn",
      key: "hero.mpc_learning_paused",
    });
  } else if (mpcStatus(config, ctx.controlMode) === "learning") {
    hints.push({
      id: "mpc_learning",
      icon: "mdi:school-outline",
      severity: "info",
      key: "card.mpc_learning",
    });
  }
  return hints;
}

export function hintText(hint: RoomHint, language: string): string {
  return localize(hint.key, language, hint.params);
}

/* ---------- Why the room has its target (room hero) ---------- */

/** Unix seconds of the active schedule's next change (`next_event`), null if unknown. */
export function scheduleNextChange(
  config: RoomConfig | null,
  states: Record<string, HassEntity> | undefined,
): number | null {
  const eid = activeScheduleEntity(config);
  const raw = eid ? states?.[eid]?.attributes?.next_event : undefined;
  if (typeof raw !== "string") return null;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** Entity of the schedule the room follows now; the first one without a selector. */
export function activeScheduleEntity(config: RoomConfig | null): string | null {
  const schedules = (config?.schedules ?? []).filter((s) => !!s.entity_id);
  if (!schedules.length) return null;
  const idx = config?.live?.active_schedule_index ?? -1;
  return (schedules[idx] ?? schedules[0]).entity_id;
}

export interface TargetReason {
  icon: string;
  /** What sets the target: override type, vacation, away, the schedule's name. */
  label: string;
  /** Until when, or in which state. */
  detail: string;
}

export interface TargetReasonContext {
  language: string;
  states: Record<string, HassEntity> | undefined;
  vacationActive: boolean;
  vacationUntil: number | null;
  now?: number;
}

/**
 * Where the current target comes from, in the backend's order: override > vacation >
 * presence away > schedule (an empty room caps it at eco). The live data carries no reason,
 * so it is derived here; `override` is the effective one (optimistic before the poll).
 */
export function targetReason(
  config: RoomConfig,
  override: EffectiveOverride,
  ctx: TargetReasonContext,
): TargetReason {
  const l = ctx.language;
  const live = config.live;
  const nowMs = ctx.now ?? Date.now();
  const suppressed = !!live?.override_suppressed && !!live?.override_active;
  if (override.active && override.type && !suppressed) {
    const until = override.until;
    let detail: string;
    if (until == null) detail = localize("detail.reason.permanent", l);
    else {
      const left = formatRemaining(until, l, nowMs / 1000);
      detail = left
        ? localize("detail.reason.until_left", l, {
            time: formatClock(until, l, nowMs),
            left,
          })
        : localize("detail.reason.until", l, { time: formatClock(until, l, nowMs) });
    }
    return {
      icon: OVERRIDE_ICONS[override.type],
      label: localize(OVERRIDE_TYPE_KEYS[override.type], l),
      detail,
    };
  }
  if (ctx.vacationActive) {
    const until = ctx.vacationUntil;
    return {
      icon: "mdi:airplane",
      label: localize("panel.stat.vacation", l),
      detail:
        until && until < VACATION_SENTINEL
          ? localize("detail.reason.until", l, {
              time: new Intl.DateTimeFormat(l, {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              }).format(new Date(until * 1000)),
            })
          : localize("detail.reason.permanent", l),
    };
  }
  if (live?.presence_away) {
    return {
      icon: "mdi:home-off-outline",
      label: localize("card.presence_away", l),
      detail: suppressed
        ? localize("card.hint.override_paused", l, {
            type: localize(OVERRIDE_TYPE_KEYS[live.override_type ?? "custom"], l),
          })
        : localize("detail.reason.nobody_home", l),
    };
  }
  const eid = activeScheduleEntity(config);
  if (!eid) {
    return {
      icon: "mdi:home-thermometer-outline",
      label: localize("detail.reason.no_schedule", l),
      detail: localize("override.comfort", l),
    };
  }
  const st = ctx.states?.[eid];
  const name = (st?.attributes?.friendly_name as string | undefined) || eid;
  const on = st?.state === "on";
  const vacant = !!live?.occupancy_vacant;
  const phase = localize(on && !vacant ? "override.comfort" : "override.eco", l);
  const next = scheduleNextChange(config, ctx.states);
  let detail = next
    ? localize("detail.reason.phase_until", l, { phase, time: formatClock(next, l, nowMs) })
    : phase;
  if (vacant && on) detail = `${localize("card.hint.vacant", l)} · ${detail}`;
  return { icon: "mdi:calendar-clock", label: name, detail };
}

const OVERRIDE_ICONS: Record<OverrideType, string> = {
  boost: "mdi:sofa",
  eco: "mdi:leaf",
  custom: "mdi:thermometer",
};

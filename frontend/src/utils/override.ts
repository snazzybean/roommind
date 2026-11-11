/**
 * Override logic shared by the panel's override section and the dashboard card.
 * Kept free of custom elements: the card is a separate bundle and must not define
 * the panel's tags a second time.
 */
import type { ClimateMode, OverrideType, RoomConfig, RoomLiveData } from "../types";
import { localize } from "./localize";

export const OVERRIDE_DURATIONS_H = [1, 2, 4];

/** `duration` for an override without end (the backend stores no `override_until`). */
export const OVERRIDE_PERMANENT_H = 0;

/** Fallback duration of a dashboard quick override in a room without schedule (h). */
export const QUICK_OVERRIDE_FALLBACK_H = 4;

/** Override as the UI shows it: live data, or what the user just set before the poll confirms it. */
export interface EffectiveOverride {
  active: boolean;
  type: OverrideType | null;
  heat: number | null;
  cool: number | null;
  until: number | null;
}

export const NO_OVERRIDE: EffectiveOverride = {
  active: false,
  type: null,
  heat: null,
  cool: null,
  until: null,
};

export function liveOverride(live: RoomLiveData | null | undefined): EffectiveOverride {
  if (!live?.override_active || !live.override_type) return NO_OVERRIDE;
  return {
    active: true,
    type: live.override_type,
    heat: live.override_heat,
    cool: live.override_cool,
    until: live.override_until,
  };
}

export interface RoomTemps {
  comfortHeat: number;
  comfortCool: number;
  ecoHeat: number;
  ecoCool: number;
}

/** Heat/cool targets an override of this type sets, masked to the room's climate mode. */
export function overrideBand(
  type: OverrideType,
  climateMode: ClimateMode,
  temps: RoomTemps,
  custom: { heat: number; cool: number },
): { heat: number | null; cool: number | null } {
  let heat: number | null;
  let cool: number | null;
  if (type === "boost") {
    heat = temps.comfortHeat;
    cool = temps.comfortCool;
  } else if (type === "eco") {
    heat = temps.ecoHeat;
    cool = temps.ecoCool;
  } else {
    heat = custom.heat;
    cool = custom.cool;
  }
  if (climateMode === "heat_only") cool = null;
  if (climateMode === "cool_only") heat = null;
  return { heat, cool };
}

export function isInvalidBand(heat: number | null, cool: number | null): boolean {
  return heat != null && cool != null && cool < heat;
}

/**
 * WS message for `roommind/override/set`; presets take their targets from the room.
 * `untilScheduleChange`: hold until the next schedule change, `hours` is the fallback for
 * rooms without a schedule.
 */
export function overrideSetMessage(
  areaId: string,
  type: OverrideType,
  hours: number,
  climateMode: ClimateMode,
  custom: { heat: number; cool: number },
  untilScheduleChange = false,
): Record<string, unknown> {
  const msg: Record<string, unknown> = {
    type: "roommind/override/set",
    area_id: areaId,
    override_type: type,
    duration: hours,
  };
  if (untilScheduleChange) msg.until_schedule_change = true;
  if (type === "custom") {
    if (climateMode !== "cool_only") msg.heat = custom.heat;
    if (climateMode !== "heat_only") msg.cool = custom.cool;
  }
  return msg;
}

/* ---------- Quick choice (panel room card and dashboard card) ---------- */

export type QuickValue = "schedule" | "comfort" | "eco";

/** The quick choice a room's live state matches; null under a custom override. */
export function quickValueOf(live: RoomLiveData | undefined): QuickValue | null {
  if (!live?.override_active) return "schedule";
  if (live.override_type === "boost") return "comfort";
  if (live.override_type === "eco") return "eco";
  return null;
}

/**
 * Options of the quick choice. Comfort stays offered without a schedule too: away, vacation,
 * an empty room or the price shift can hold the room below comfort there.
 */
export function quickOptions(
  config: RoomConfig | null | undefined,
  language: string,
): { value: QuickValue; label: string; icon: string }[] {
  const hasSchedule = (config?.schedules ?? []).some((s) => !!s.entity_id);
  return [
    {
      value: "schedule",
      label: localize(hasSchedule ? "card.quick.schedule" : "card.quick.normal", language),
      icon: hasSchedule ? "mdi:calendar-clock" : "mdi:home-thermometer-outline",
    },
    { value: "comfort", label: localize("override.comfort", language), icon: "mdi:sofa" },
    { value: "eco", label: localize("override.eco", language), icon: "mdi:leaf" },
  ];
}

/** WS message for a quick choice: clear, or comfort/eco until the next schedule change. */
export function quickMessage(config: RoomConfig, value: QuickValue): Record<string, unknown> {
  if (value === "schedule") return { type: "roommind/override/clear", area_id: config.area_id };
  return overrideSetMessage(
    config.area_id,
    value === "comfort" ? "boost" : "eco",
    QUICK_OVERRIDE_FALLBACK_H,
    config.climate_mode ?? "auto",
    { heat: 0, cool: 0 },
    true,
  );
}

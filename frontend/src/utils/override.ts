/**
 * Override logic shared by the panel's override section and the dashboard card.
 * Kept free of custom elements: the card is a separate bundle and must not define
 * the panel's tags a second time.
 */
import type { ClimateMode, OverrideType } from "../types";

export const OVERRIDE_DURATIONS_H = [1, 2, 4];

/** Fallback duration of a dashboard quick override in a room without schedule (h). */
export const QUICK_OVERRIDE_FALLBACK_H = 4;

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

/** Remaining time as "1h 20m" / "20m", empty once the time has passed. */
export function formatRemaining(until: number, now = Date.now() / 1000): string {
  const remaining = until - now;
  if (remaining <= 0) return "";
  const h = Math.floor(remaining / 3600);
  const m = Math.floor((remaining % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

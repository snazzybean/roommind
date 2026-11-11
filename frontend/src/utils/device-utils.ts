/**
 * Shared device utilities for the unified device model.
 * Mirrors backend logic from custom_components/roommind/utils/device_utils.py.
 */

import type { ClimateMode, DeviceConfig, HomeAssistant } from "../types";

const HST_PRIORITY: Record<string, number> = { underfloor: 2, radiator: 1, "": 0 };

/**
 * Resolve room-level heating_system_type from devices.
 * Most conservative type wins (longest residual heat tau).
 * Only TRV devices are considered.
 */
export function resolveHeatingSystemType(devices: DeviceConfig[]): string {
  let best = "";
  for (const d of devices) {
    if (d.type !== "trv") continue;
    const hst = d.heating_system_type ?? "";
    if ((HST_PRIORITY[hst] ?? 0) > (HST_PRIORITY[best] ?? 0)) best = hst;
  }
  return best;
}

export interface DeviceAbilities {
  heat: boolean;
  cool: boolean;
  /** Thermostats and climate devices in the same room. */
  mixed: boolean;
}

/** What the room's devices can do; a device without known hvac_modes counts as able. */
export function deviceAbilities(
  devices: DeviceConfig[],
  hass: Pick<HomeAssistant, "states">,
): DeviceAbilities {
  const can = (eid: string, wanted: string[]) => {
    const m = hass.states[eid]?.attributes?.hvac_modes;
    return !Array.isArray(m) || (m as string[]).some((x) => wanted.includes(x));
  };
  const trvs = devices.filter((d) => d.type === "trv");
  const acs = devices.filter((d) => d.type === "ac");
  return {
    heat: trvs.length > 0 || acs.some((d) => can(d.entity_id, ["heat", "heat_cool", "auto"])),
    cool: acs.some((d) => can(d.entity_id, ["cool", "heat_cool", "auto"])),
    mixed: trvs.length > 0 && acs.length > 0,
  };
}

/** Whether the devices can run a climate mode; a room without devices fits every mode. */
export function modeFits(
  mode: ClimateMode,
  devices: DeviceConfig[],
  ability: DeviceAbilities,
): boolean {
  if (devices.length === 0 || mode === "auto") return true;
  return mode === "heat_only" ? ability.heat : ability.cool;
}

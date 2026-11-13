import type { HomeAssistant } from "../types";

/** Home Assistant's slugify as the mobile app uses it for its notify service name. */
export function slugify(value: string): string {
  return value
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/['’]+/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Display name of a notification target: the entity's name, for a legacy
 * `notify.mobile_app_<device>` service the phone's device name, else the service name.
 */
export function notifyTargetName(
  hass: Pick<HomeAssistant, "states" | "devices">,
  entityId: string,
): string {
  const friendly = hass.states[entityId]?.attributes?.friendly_name;
  if (typeof friendly === "string" && friendly) return friendly;
  const service = entityId.replace(/^notify\./, "");
  const phone = service.match(/^mobile_app_(.+)$/)?.[1];
  if (phone) {
    for (const device of Object.values(hass.devices ?? {})) {
      const name = device.name_by_user || device.name;
      if (name && slugify(name) === phone) return name;
    }
  }
  return service;
}

/** Phones get a phone icon, everything else a bell. */
export function notifyTargetIcon(entityId: string): string {
  return /^notify\.mobile_app_/.test(entityId) ? "mdi:cellphone" : "mdi:bell-outline";
}

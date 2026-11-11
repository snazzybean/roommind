import type { PriceStatus } from "../types";
import { localize } from "./localize";

export type PriceStatusText =
  | { state: "waiting" }
  | { state: "unreadable" }
  | { state: "readable"; level: string; detail: string };

/**
 * What the settings say about the price source, shared by the price panel and its summary
 * in the settings list. `waiting` until rooms/list reports on the selected entity.
 */
export function describePriceStatus(
  status: PriceStatus | null,
  entityId: string,
  language: string,
): PriceStatusText {
  // The status comes with the next rooms/list poll after a change
  if (!status || status.entity_id !== entityId) return { state: "waiting" };
  if (!status.readable) return { state: "unreadable" };
  const level = status.level
    ? localize(`settings.price_level_${status.level}`, language)
    : localize("settings.price_level_unknown", language);
  let detail: string;
  if (status.kind === "forecast") {
    detail = localize("settings.price_kind_forecast", language, {
      hours: new Intl.NumberFormat(language, { maximumFractionDigits: 0 }).format(
        status.forecast_hours,
      ),
    });
  } else if (status.kind === "switch") {
    detail = localize("settings.price_kind_switch", language);
  } else {
    detail = localize(
      status.history_hours >= status.history_needed
        ? "settings.price_kind_history"
        : "settings.price_kind_history_learning",
      language,
      { hours: status.history_hours, needed: status.history_needed },
    );
  }
  return { state: "readable", level, detail };
}

import { html } from "lit";
import type { HomeAssistant } from "../../types";
import { formatNumber } from "../../utils/format";
import {
  MAX_TARGET_TEMP_C,
  MIN_TARGET_TEMP_C,
  tempUnit,
  toCelsius,
  toDisplay,
  usesFahrenheit,
} from "../../utils/temperature";
import "./rs-stepper";

/**
 * A target temperature row (icon, label, rs-stepper), styled by `tempRowStyles`. `celsius` in
 * °C; the stepper works in the user's unit (0.5 °C / 1 °F, 5-35 °C) and `onChange` gets °C.
 */
export function tempRow(opts: {
  hass: HomeAssistant;
  side: "heat" | "cool";
  label: string;
  /** Screen reader name when the visible label alone is ambiguous (e.g. "Comfort, heat below"). */
  ariaLabel?: string;
  celsius: number;
  onChange: (celsius: number) => void;
}) {
  const { hass, side, label } = opts;
  const step = usesFahrenheit(hass) ? 1 : 0.5;
  const shown = Math.round(toDisplay(opts.celsius, hass) / step) * step;
  return html`<div class="temp-row ${side}">
    <span
      ><ha-icon icon=${side === "heat" ? "mdi:fire" : "mdi:snowflake"} aria-hidden="true"></ha-icon
      >${label}</span
    >
    <rs-stepper
      .language=${hass.language}
      .label=${opts.ariaLabel || label}
      .value=${shown}
      .min=${Math.ceil(toDisplay(MIN_TARGET_TEMP_C, hass))}
      .max=${Math.floor(toDisplay(MAX_TARGET_TEMP_C, hass))}
      .step=${step}
      .display=${`${formatNumber(shown, hass, 0, 1)} ${tempUnit(hass)}`}
      @value-changed=${(e: CustomEvent<{ value: number }>) =>
        opts.onChange(toCelsius(e.detail.value, hass))}
    ></rs-stepper>
  </div>`;
}

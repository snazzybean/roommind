import { html, nothing } from "lit";
import type { HomeAssistant } from "../../types";
import {
  tempUnit,
  toCelsius,
  toCelsiusDelta,
  toDisplay,
  toDisplayDelta,
  usesFahrenheit,
} from "../../utils/temperature";
import "./rs-info-icon";
import "./rs-list-row";
import "./rs-stepper";

/**
 * A setting row with a number: heading (and secondary line) left, info icon and an editable
 * rs-stepper right, the settings-page counterpart of `tempRow`. `value`, `min`, `max` are in
 * the stored unit; with `kind` they are °C and the stepper works in the user's unit (0.5 °C /
 * 1 °F), `onChange` gets °C back.
 */
export function numberRow(opts: {
  hass: HomeAssistant;
  label: string;
  secondary?: string;
  info?: string;
  icon?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  /** Unit shown in the stepper; temperatures take the user's unit. */
  unit?: string;
  kind?: "temperature" | "temperature-delta";
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const { hass, kind } = opts;
  const toShown = (v: number) =>
    kind === "temperature" ? toDisplay(v, hass) : kind ? toDisplayDelta(v, hass) : v;
  const fromShown = (v: number) =>
    kind === "temperature" ? toCelsius(v, hass) : kind ? toCelsiusDelta(v, hass) : v;
  const step = opts.step ?? (kind ? (usesFahrenheit(hass) ? 1 : 0.5) : 1);
  return html`<rs-list-row
    wrap
    .icon=${opts.icon ?? ""}
    .heading=${opts.label}
    .secondary=${opts.secondary ?? ""}
    ?disabled=${opts.disabled}
  >
    ${opts.info ? html`<rs-info-icon slot="end" .text=${opts.info}></rs-info-icon>` : nothing}
    <rs-stepper
      slot="end"
      .editable=${true}
      .unit=${kind ? tempUnit(hass) : (opts.unit ?? "")}
      .language=${hass.language}
      .label=${opts.label}
      .value=${toShown(opts.value)}
      .min=${kind === "temperature" ? Math.ceil(toShown(opts.min)) : toShown(opts.min)}
      .max=${kind === "temperature" ? Math.floor(toShown(opts.max)) : toShown(opts.max)}
      .step=${step}
      .disabled=${!!opts.disabled}
      @value-changed=${(e: CustomEvent<{ value: number }>) => opts.onChange(fromShown(e.detail.value))}
    ></rs-stepper>
  </rs-list-row>`;
}

import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, ClimateMode } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit, toDisplay, toCelsius, tempStep, tempRange } from "../../utils/temperature";
import { tokens } from "../../styles/tokens";
import { inputStyles } from "../../styles/input-styles";

/**
 * Comfort and eco targets of a room (content of the temperatures dialog). Auto rooms get heat
 * and cool per level, heat_only/cool_only one value each. Fires `comfort-heat-changed`,
 * `comfort-cool-changed`, `eco-heat-changed`, `eco-cool-changed` with `{ value }` in °C.
 */
@customElement("rs-target-temps")
export class RsTargetTemps extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Number }) public comfortHeat = 21.0;
  @property({ type: Number }) public comfortCool = 24.0;
  @property({ type: Number }) public ecoHeat = 17.0;
  @property({ type: Number }) public ecoCool = 27.0;
  @property({ type: String }) public climateMode: ClimateMode = "auto";

  static styles = [
    tokens,
    inputStyles,
    css`
      :host {
        display: block;
      }

      .fallback-hint {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 4px;
        font-style: italic;
      }

      .temp-inputs {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }

      .temp-input-group {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      ha-textfield {
        flex: 1;
      }

      .temp-grid-auto {
        display: grid;
        grid-template-columns: auto 1fr 1fr;
        gap: 8px 12px;
        align-items: center;
      }
      .temp-grid-header {
        font-size: 12px;
        font-weight: 600;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.3px;
        text-align: center;
      }
      .temp-grid-row-label {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
        white-space: nowrap;
      }

      @media (max-width: 600px) {
        .temp-grid-auto {
          grid-template-columns: 1fr 1fr;
        }
        .temp-grid-row-label {
          grid-column: 1 / -1;
          margin-top: 8px;
        }
        /* the corner cell only; the column headers stay above the first pair of fields */
        .temp-grid-header.corner {
          display: none;
        }
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    const range = tempRange(5, 35, this.hass);
    const field = (celsius: number, onChange: (e: Event) => void, label = "") =>
      html`<ha-textfield
        type="number"
        label=${label}
        .value=${String(toDisplay(celsius, this.hass))}
        suffix=${tempUnit(this.hass)}
        step=${tempStep(this.hass)}
        min=${range.min}
        max=${range.max}
        @change=${onChange}
      ></ha-textfield>`;

    if (this.climateMode === "auto") {
      return html`
        <div class="temp-grid-auto">
          <div class="temp-grid-header corner"></div>
          <div class="temp-grid-header">${localize("schedule.column_comfort", l)}</div>
          <div class="temp-grid-header">${localize("schedule.column_eco", l)}</div>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:fire" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_heat", l)}
          </div>
          ${field(this.comfortHeat, this._onComfortHeatChange)}
          ${field(this.ecoHeat, this._onEcoHeatChange)}
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:snowflake" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_cool", l)}
          </div>
          ${field(this.comfortCool, this._onComfortCoolChange)}
          ${field(this.ecoCool, this._onEcoCoolChange)}
        </div>
      `;
    }

    const cool = this.climateMode === "cool_only";
    return html`
      <div class="temp-inputs">
        <div class="temp-input-group">
          ${field(
            cool ? this.comfortCool : this.comfortHeat,
            cool ? this._onComfortCoolChange : this._onComfortHeatChange,
            localize("schedule.comfort_label", l),
          )}
        </div>
        <div class="temp-input-group">
          ${field(
            cool ? this.ecoCool : this.ecoHeat,
            cool ? this._onEcoCoolChange : this._onEcoHeatChange,
            localize("schedule.eco_label", l),
          )}
        </div>
      </div>
      <div class="fallback-hint">${localize("schedule.comfort_hint", l)}</div>
    `;
  }

  private _fire(name: string, value: number) {
    this.dispatchEvent(new CustomEvent(name, { detail: { value }, bubbles: true, composed: true }));
  }

  private _read(e: Event, fallbackC: number): number {
    const target = e.target as HTMLElement & { value: string };
    return toCelsius(parseFloat(target.value) || toDisplay(fallbackC, this.hass), this.hass);
  }

  private _onComfortHeatChange = (e: Event) => {
    const val = this._read(e, 21.0);
    this._fire("comfort-heat-changed", val);
    if (this.comfortCool < val) this._fire("comfort-cool-changed", val);
  };

  private _onComfortCoolChange = (e: Event) => {
    const val = this._read(e, 24.0);
    this._fire("comfort-cool-changed", val);
    if (this.comfortHeat > val) this._fire("comfort-heat-changed", val);
  };

  private _onEcoHeatChange = (e: Event) => {
    const val = this._read(e, 17.0);
    this._fire("eco-heat-changed", val);
    if (this.ecoCool < val) this._fire("eco-cool-changed", val);
  };

  private _onEcoCoolChange = (e: Event) => {
    const val = this._read(e, 27.0);
    this._fire("eco-cool-changed", val);
    if (this.ecoHeat > val) this._fire("eco-heat-changed", val);
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-target-temps": RsTargetTemps;
  }
}

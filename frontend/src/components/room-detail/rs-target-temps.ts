import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, ClimateMode } from "../../types";
import { localize } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import { tempRowStyles } from "../../styles/temp-row-styles";
import { tempRow } from "../shared/temp-row";

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
    tempRowStyles,
    css`
      :host {
        display: block;
      }

      .level + .level {
        margin-top: var(--rs-space-5);
      }

      .level-title {
        margin: 0;
        font-size: var(--rs-font-md);
        font-weight: 500;
      }

      .hint {
        margin: var(--rs-space-4) 0 0;
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }
    `,
  ];

  private _row(
    side: "heat" | "cool",
    label: string,
    celsius: number,
    onChange: (celsius: number) => void,
  ) {
    return tempRow({ hass: this.hass, side, label, celsius, onChange });
  }

  render() {
    const l = this.hass.language;
    if (this.climateMode === "auto") {
      const level = (
        title: string,
        heat: number,
        cool: number,
        onHeat: (v: number) => void,
        onCool: (v: number) => void,
      ) =>
        html`<section class="level">
          <h4 class="level-title">${title}</h4>
          ${this._row("heat", localize("schedule_editor.heat_below", l), heat, onHeat)}
          ${this._row("cool", localize("schedule_editor.cool_above", l), cool, onCool)}
        </section>`;
      return html`
        ${level(
          localize("schedule.column_comfort", l),
          this.comfortHeat,
          this.comfortCool,
          this._onComfortHeat,
          this._onComfortCool,
        )}
        ${level(
          localize("schedule.column_eco", l),
          this.ecoHeat,
          this.ecoCool,
          this._onEcoHeat,
          this._onEcoCool,
        )}
      `;
    }

    const cool = this.climateMode === "cool_only";
    const side = cool ? "cool" : "heat";
    return html`
      ${this._row(
        side,
        localize("schedule.comfort_label", l),
        cool ? this.comfortCool : this.comfortHeat,
        cool ? this._onComfortCool : this._onComfortHeat,
      )}
      ${this._row(
        side,
        localize("schedule.eco_label", l),
        cool ? this.ecoCool : this.ecoHeat,
        cool ? this._onEcoCool : this._onEcoHeat,
      )}
      <p class="hint">${localize("schedule.comfort_hint", l)}</p>
    `;
  }

  private _fire(name: string, value: number) {
    this.dispatchEvent(new CustomEvent(name, { detail: { value }, bubbles: true, composed: true }));
  }

  private _onComfortHeat = (val: number) => {
    this._fire("comfort-heat-changed", val);
    if (this.comfortCool < val) this._fire("comfort-cool-changed", val);
  };

  private _onComfortCool = (val: number) => {
    this._fire("comfort-cool-changed", val);
    if (this.comfortHeat > val) this._fire("comfort-heat-changed", val);
  };

  private _onEcoHeat = (val: number) => {
    this._fire("eco-heat-changed", val);
    if (this.ecoCool < val) this._fire("eco-cool-changed", val);
  };

  private _onEcoCool = (val: number) => {
    this._fire("eco-cool-changed", val);
    if (this.ecoHeat > val) this._fire("eco-heat-changed", val);
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-target-temps": RsTargetTemps;
  }
}

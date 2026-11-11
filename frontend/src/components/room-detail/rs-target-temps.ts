import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, ClimateMode } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import { tempRowStyles } from "../../styles/temp-row-styles";
import { tempRow } from "../shared/temp-row";
import "../shared/rs-info-icon";

/**
 * Comfort and eco targets of a room (content of the temperatures dialog): a level each, with
 * the heat and/or cool side the climate mode uses. Fires `comfort-heat-changed`,
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
        display: flex;
        align-items: center;
        gap: var(--rs-space-1);
        margin: 0;
        font-size: var(--rs-font-md);
        font-weight: 500;
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    const heat = this.climateMode !== "cool_only";
    const cool = this.climateMode !== "heat_only";
    const level = (
      title: string,
      info: string,
      heatC: number,
      coolC: number,
      onHeat: (v: number) => void,
      onCool: (v: number) => void,
    ) => {
      const row = (
        side: "heat" | "cool",
        key: TranslationKey,
        celsius: number,
        cb: (v: number) => void,
      ) => {
        const label = localize(key, l);
        return tempRow({
          hass: this.hass,
          side,
          label,
          ariaLabel: `${title}, ${label}`,
          celsius,
          onChange: cb,
        });
      };
      return html`<section class="level">
        <h4 class="level-title">${title}<rs-info-icon .text=${info}></rs-info-icon></h4>
        ${heat ? row("heat", "schedule_editor.heat_below", heatC, onHeat) : nothing}
        ${cool ? row("cool", "schedule_editor.cool_above", coolC, onCool) : nothing}
      </section>`;
    };
    return html`
      ${level(
        localize("schedule.column_comfort", l),
        localize("schedule.comfort_hint", l),
        this.comfortHeat,
        this.comfortCool,
        this._onComfortHeat,
        this._onComfortCool,
      )}
      ${level(
        localize("schedule.column_eco", l),
        localize("schedule.eco_hint", l),
        this.ecoHeat,
        this.ecoCool,
        this._onEcoHeat,
        this._onEcoCool,
      )}
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

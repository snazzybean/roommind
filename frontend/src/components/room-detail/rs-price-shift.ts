import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, ClimateMode } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import { tokens } from "../../styles/tokens";
import "../shared/rs-segmented";
import "../shared/rs-list-row";

// Matches MAX_PRICE_SHIFT_K in const.py
const PRICE_SHIFT_STEPS = [0, 0.5, 1, 1.5, 2];

type PriceLevel = "cheap" | "normal" | "expensive" | null | undefined;

/** "±1 °C" style label of a shift step, in the user's unit. */
export function priceShiftLabel(k: number, hass: HomeAssistant): string {
  return `±${new Intl.NumberFormat(hass.language, { maximumFractionDigits: 1 }).format(
    toDisplayDelta(k, hass),
  )} ${tempUnit(hass)}`;
}

/**
 * Content of the room's price dialog: how far the schedule target may move with the electricity
 * price, plus what the price does to the room right now. Fires `price-shift-changed` with
 * `{ value }` (K).
 */
@customElement("rs-price-shift")
export class RsPriceShift extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Number }) public priceShift = 0;
  @property({ type: String }) public climateMode: ClimateMode = "auto";
  @property({ attribute: false }) public priceLevel: PriceLevel = null;
  /** Shift applied in this cycle per side (K, signed), from the room's live data. */
  @property({ type: Number }) public shiftHeat = 0;
  @property({ type: Number }) public shiftCool = 0;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
      }

      .intro {
        margin: 0 0 var(--rs-space-4);
        font-size: var(--rs-font-md);
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .label {
        font-size: var(--rs-font-md);
        margin-bottom: var(--rs-space-2);
      }

      .status {
        margin-top: var(--rs-space-2);
        --rs-list-row-padding: 0;
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    return html`
      <p class="intro">${localize("schedule.price_shift_hint", l)}</p>
      <div class="label" aria-hidden="true">${localize("detail.price.shift_label", l)}</div>
      <rs-segmented
        wrap
        .label=${localize("detail.price.shift_label", l)}
        .options=${PRICE_SHIFT_STEPS.map((k) => ({
          value: String(k),
          label: k === 0 ? localize("schedule.price_shift_off", l) : priceShiftLabel(k, this.hass),
        }))}
        .value=${this._selected()}
        @value-changed=${this._onChange}
      ></rs-segmented>
      <div class="status">
        <rs-list-row
          icon="mdi:cash-clock"
          .heading=${localize("detail.price.level_now", l)}
          .value=${localize(`settings.price_level_${this.priceLevel || "unknown"}`, l)}
        ></rs-list-row>
        ${
          this.priceShift > 0
            ? html`<rs-list-row
                icon="mdi:thermometer-lines"
                .heading=${localize("detail.price.shift_now", l)}
                .value=${this._shiftNowText()}
              ></rs-list-row>`
            : nothing
        }
      </div>
    `;
  }

  private _selected(): string {
    const step = PRICE_SHIFT_STEPS.find((k) => Math.abs(this.priceShift - k) < 0.01);
    return step === undefined ? "" : String(step);
  }

  private _signed(k: number): string {
    return `${new Intl.NumberFormat(this.hass.language, {
      maximumFractionDigits: 1,
      signDisplay: "exceptZero",
    }).format(toDisplayDelta(k, this.hass))} ${tempUnit(this.hass)}`;
  }

  private _shiftNowText(): string {
    const l = this.hass.language;
    const heat = this.shiftHeat || 0;
    const cool = this.shiftCool || 0;
    if (this.climateMode === "heat_only") {
      return heat ? this._signed(heat) : localize("detail.price.shift_none", l);
    }
    if (this.climateMode === "cool_only") {
      return cool ? this._signed(cool) : localize("detail.price.shift_none", l);
    }
    if (!heat && !cool) return localize("detail.price.shift_none", l);
    return `${localize("schedule.row_heat", l)} ${this._signed(heat)} · ${localize("schedule.row_cool", l)} ${this._signed(cool)}`;
  }

  private _onChange(e: CustomEvent<{ value: string }>) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("price-shift-changed", {
        detail: { value: Number(e.detail.value) },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-price-shift": RsPriceShift;
  }
}

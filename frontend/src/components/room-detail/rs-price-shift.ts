import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, ClimateMode, TouLimits, TouRoomLimits } from "../../types";
import { localize } from "../../utils/localize";
import {
  tempUnit,
  toCelsius,
  toCelsiusDelta,
  toDisplay,
  toDisplayDelta,
} from "../../utils/temperature";
import { DEFAULT_TOU_LIMITS, effectiveLimits } from "../../utils/tou-limits";
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
  /** Global master switch (D8): the store opt-in renders only while on. */
  @property({ type: Boolean }) public touEnabled = false;
  @property({ type: Boolean }) public touStore = false;
  /** Global store limits in force (the rooms/list `tou_limits` view). */
  @property({ attribute: false }) public globalLimits: TouLimits = DEFAULT_TOU_LIMITS;
  /** This room's optional overrides; a missing key inherits the global. */
  @property({ attribute: false }) public roomLimits: TouRoomLimits = {};

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

      .limits-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--rs-space-3);
        margin: var(--rs-space-3) 0;
      }
      .limits-grid ha-textfield {
        width: 100%;
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
        ${
          this.touEnabled
            ? html`<rs-list-row
                  switch
                  wrap
                  .heading=${localize("detail.energy.store_label", l)}
                  .checked=${this.touStore}
                  @toggle-changed=${(e: CustomEvent<boolean>) =>
                    this.dispatchEvent(
                      new CustomEvent("tou-store-changed", { detail: { value: e.detail } }),
                    )}
                ></rs-list-row>
                <p class="intro">${localize("detail.energy.store_hint", l)}</p>
                ${
                  this.touStore
                    ? html`<p class="intro">${this._limitsNote(l)}</p>
                        <div class="label">${localize("tou.room_limits_title", l)}</div>
                        <div class="limits-grid">
                          ${this._limitField("heat_min", localize("tou.limit_heat_min", l), tempUnit(this.hass))}
                          ${this._limitField("heat_max", localize("tou.limit_heat_max", l), tempUnit(this.hass))}
                          ${this._limitField("cool_min", localize("tou.limit_cool_min", l), tempUnit(this.hass))}
                          ${this._limitField("cool_max", localize("tou.limit_cool_max", l), tempUnit(this.hass))}
                          ${this._limitField("swing", localize("tou.limit_swing", l), `Δ${tempUnit(this.hass)}`)}
                          ${this._limitField("store_gap", localize("tou.limit_store_gap", l), "×")}
                        </div>
                        <p class="intro">${localize("tou.room_limits_hint", l)}</p>`
                    : nothing
                }`
            : nothing
        }
      </div>
    `;
  }

  /** The override value shown in a field: blank means "inherit the global". */
  private _limitValue(key: keyof TouLimits): string {
    const v = this.roomLimits[key];
    if (typeof v !== "number") return "";
    if (key === "store_gap") return String(v);
    if (key === "swing") return String(toDisplayDelta(v, this.hass));
    return String(toDisplay(v, this.hass));
  }

  /**
   * One per-room consent override. Clearing the field sends null: the engine
   * then inherits the global value (blank = inherit, both ways).
   */
  private _limitField(key: keyof TouLimits, label: string, unit: string) {
    return html`<ha-textfield
      type="number"
      step=${key === "store_gap" ? "0.1" : "0.5"}
      .value=${this._limitValue(key)}
      .label=${label}
      .suffix=${unit}
      @change=${(e: Event) => {
        const raw = (e.target as HTMLInputElement).value.trim();
        let value: number | null = null;
        if (raw !== "") {
          const v = parseFloat(raw);
          if (isNaN(v)) return;
          value =
            key === "store_gap"
              ? v
              : key === "swing"
                ? toCelsiusDelta(v, this.hass)
                : toCelsius(v, this.hass);
        }
        this.dispatchEvent(
          new CustomEvent("tou-limit-changed", { detail: { key: `tou_${key}`, value } }),
        );
      }}
    ></ha-textfield>`;
  }

  /** One sentence naming the band, the swing and the price gate the store
   * works inside — so the toggle is never a magic box. */
  private _limitsNote(l: string): string {
    const eff = effectiveLimits(this.globalLimits, this.roomLimits);
    return localize("tou.limits_note", l, {
      swing: String(toDisplayDelta(eff.swing, this.hass)),
      hmin: String(toDisplay(eff.heat_min, this.hass)),
      hmax: String(toDisplay(eff.heat_max, this.hass)),
      cmin: String(toDisplay(eff.cool_min, this.hass)),
      cmax: String(toDisplay(eff.cool_max, this.hass)),
      gap: String(eff.store_gap),
      unit: tempUnit(this.hass),
    });
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

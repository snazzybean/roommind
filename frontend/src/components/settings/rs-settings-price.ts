/**
 * rs-settings-price – Electricity price source and what RoomMind currently reads from it.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, PriceStatus } from "../../types";
import { localize } from "../../utils/localize";

// A price sensor (with or without a forecast attribute) or something that is on while cheap
const PRICE_DOMAINS = [
  "sensor",
  "input_number",
  "event",
  "binary_sensor",
  "input_boolean",
  "switch",
];

@customElement("rs-settings-price")
export class RsSettingsPrice extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public priceEntity = "";
  @property({ attribute: false }) public status: PriceStatus | null = null;

  render() {
    const l = this.hass.language;
    return html`
      <div class="settings-section first">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.priceEntity}
          .includeDomains=${PRICE_DOMAINS}
          .label=${localize("settings.price_entity", l)}
          allow-custom-entity
          @value-changed=${(e: CustomEvent) => {
            const v = (e.detail?.value as string) ?? "";
            if (v !== this.priceEntity) this._fire("priceEntity", v);
          }}
        ></ha-entity-picker>
        <span class="field-hint">${localize("settings.price_entity_hint", l)}</span>
        ${this.priceEntity ? this._renderStatus(l) : nothing}
      </div>
    `;
  }

  private _renderStatus(l: string) {
    const s = this.status;
    // The status comes with the next rooms/list poll after a change
    if (!s || s.entity_id !== this.priceEntity) {
      return html`<div class="price-status muted">${localize("settings.price_waiting", l)}</div>`;
    }
    if (!s.readable) {
      return html`<div class="price-status warning" role="status">
        ${localize("settings.price_unreadable", l)}
      </div>`;
    }
    const level = s.level
      ? localize(`settings.price_level_${s.level}`, l)
      : localize("settings.price_level_unknown", l);
    let detail: string;
    if (s.kind === "forecast") {
      detail = localize("settings.price_kind_forecast", l, {
        hours: new Intl.NumberFormat(l, { maximumFractionDigits: 0 }).format(s.forecast_hours),
      });
    } else if (s.kind === "switch") {
      detail = localize("settings.price_kind_switch", l);
    } else {
      detail = localize(
        s.history_hours >= s.history_needed
          ? "settings.price_kind_history"
          : "settings.price_kind_history_learning",
        l,
        { hours: s.history_hours, needed: s.history_needed },
      );
    }
    return html`<div class="price-status" role="status">
      <strong>${localize("settings.price_now", l, { level })}</strong> · ${detail}
    </div>`;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .price-status {
        margin-top: 8px;
        font-size: 13px;
        color: var(--primary-text-color);
      }

      .price-status.muted {
        color: var(--secondary-text-color);
      }

      .price-status.warning {
        color: var(--error-color, #db4437);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-price": RsSettingsPrice;
  }
}

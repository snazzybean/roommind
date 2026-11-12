/**
 * rs-settings-price – Electricity price source and what RoomMind currently reads from it.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, PriceStatus } from "../../types";
import { localize } from "../../utils/localize";
import { describePriceStatus } from "../../utils/price-status";

// A price sensor (with or without a forecast attribute), an event with rates (Octopus Energy)
// or something that is on while cheap
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
      <div class="settings-section">
        <p class="note">${localize("settings.price_room_hint", l)}</p>
      </div>
    `;
  }

  private _renderStatus(l: string) {
    const s = describePriceStatus(this.status, this.priceEntity, l);
    if (s.state === "waiting") {
      return html`<div class="price-status muted">${localize("settings.price_waiting", l)}</div>`;
    }
    if (s.state === "unreadable") {
      return html`<div class="price-status warning" role="status">
        ${localize("settings.price_unreadable", l)}
      </div>`;
    }
    return html`<div class="price-status" role="status">
      <strong>${localize("settings.price_now", l, { level: s.level })}</strong> · ${s.detail}
    </div>`;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .price-status {
        margin-top: var(--rs-space-3);
        font-size: 13px;
        color: var(--primary-text-color);
      }

      .price-status.muted {
        color: var(--secondary-text-color);
      }

      .price-status.warning {
        color: var(--rs-err-text);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-price": RsSettingsPrice;
  }
}

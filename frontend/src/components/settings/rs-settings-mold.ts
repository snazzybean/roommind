/**
 * rs-settings-mold – Mold risk detection & prevention settings.
 */
import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-number-field";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import { formatNumber } from "../../utils/format";
import "../shared/rs-segmented";

// DIN 4108-2 temperature factor f_Rsi of the coldest spot (corner, window reveal) per insulation level.
const INSULATION_LEVELS = [
  { f_rsi: 0.65, key: "mold.insulation_poor" },
  { f_rsi: 0.8, key: "mold.insulation_standard" },
  { f_rsi: 0.9, key: "mold.insulation_good" },
] as const;

@customElement("rs-settings-mold")
export class RsSettingsMold extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public moldDetectionEnabled = false;
  @property({ type: Number }) public moldHumidityThreshold = 70;
  @property({ type: Number }) public moldFRsi = 0.8;
  @property({ type: Number }) public moldSustainedMinutes = 30;
  @property({ type: Boolean }) public moldPreventionEnabled = false;
  @property({ type: String }) public moldPreventionIntensity: "light" | "medium" | "strong" =
    "medium";

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("mold.detection", l)}
          .secondary=${localize("mold.detection_desc", l)}
          .checked=${this.moldDetectionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("moldDetectionEnabled", e.detail)}
        ></rs-list-row>
        ${
          this.moldDetectionEnabled
            ? html`
                <div class="threshold-grid sub">
                  <rs-number-field
                    .label=${localize("mold.threshold", l)}
                    suffix="%"
                    .hint=${localize("mold.threshold_hint", l)}
                    .min=${50}
                    .max=${90}
                    .value=${this.moldHumidityThreshold}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._fire("moldHumidityThreshold", e.detail.value)}
                  ></rs-number-field>
                  <rs-number-field
                    .label=${localize("mold.sustained", l)}
                    suffix="min"
                    .hint=${localize("mold.sustained_hint", l)}
                    .min=${5}
                    .max=${120}
                    .value=${this.moldSustainedMinutes}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._fire("moldSustainedMinutes", e.detail.value)}
                  ></rs-number-field>
                </div>
              `
            : nothing
        }
      </div>

      <div class="settings-section">
        <rs-list-row
          switch
          wrap
          .heading=${localize("mold.prevention", l)}
          .secondary=${localize("mold.prevention_desc", l)}
          .checked=${this.moldPreventionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("moldPreventionEnabled", e.detail)}
        ></rs-list-row>
        ${
          this.moldPreventionEnabled
            ? html`
                <div class="sub">
                  <span class="field-label">${localize("mold.intensity", l)}</span>
                  <rs-segmented
                    wrap
                    .label=${localize("mold.intensity", l)}
                    .options=${(["light", "medium", "strong"] as const).map((v, i) => ({
                      value: v,
                      label: localize(`mold.intensity_${v}`, l, {
                        delta: formatNumber(toDisplayDelta(i + 1, this.hass), this.hass, 0, 1),
                        unit: tempUnit(this.hass),
                      }),
                    }))}
                    .value=${this.moldPreventionIntensity}
                    @value-changed=${(e: CustomEvent<{ value: string }>) => {
                      const v = e.detail.value as "light" | "medium" | "strong";
                      if (v && v !== this.moldPreventionIntensity)
                        this._fire("moldPreventionIntensity", v);
                    }}
                  ></rs-segmented>
                  <span class="field-hint">${localize("mold.intensity_hint", l)}</span>
                </div>
              `
            : nothing
        }
      </div>

      ${
        this.moldDetectionEnabled || this.moldPreventionEnabled
          ? html`
              <div class="settings-section">
                <div>
                  <span class="field-label">${localize("mold.insulation", l)}</span>
                  <rs-segmented
                    wrap
                    .label=${localize("mold.insulation", l)}
                    .options=${INSULATION_LEVELS.map((lvl) => ({
                      value: String(lvl.f_rsi),
                      label: localize(lvl.key, l),
                    }))}
                    .value=${this._insulationValue()}
                    @value-changed=${(e: CustomEvent<{ value: string }>) => {
                      const v = parseFloat(e.detail.value);
                      if (!isNaN(v) && v !== this.moldFRsi) this._fire("moldFRsi", v);
                    }}
                  ></rs-segmented>
                  <span class="field-hint">${localize("mold.insulation_hint", l)}</span>
                </div>
              </div>
            `
          : nothing
      }
    `;
  }

  private _insulationValue(): string {
    const nearest = INSULATION_LEVELS.reduce((best, lvl) =>
      Math.abs(lvl.f_rsi - this.moldFRsi) < Math.abs(best.f_rsi - this.moldFRsi) ? lvl : best,
    );
    return String(nearest.f_rsi);
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .sub {
        margin-top: var(--rs-space-3);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-mold": RsSettingsMold;
  }
}

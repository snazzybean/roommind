/**
 * rs-settings-coil-dry – Evaporator drying (anti-odour) settings.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { numberRow } from "../shared/number-row";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { fanModeLabel, type FanModeOption } from "../../utils/device-utils";
import "../shared/rs-segmented";
import "../shared/rs-info-icon";
import "../shared/rs-field";

const KEEP = "__keep__";

@customElement("rs-settings-coil-dry")
export class RsSettingsCoilDry extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public coilDryEnabled = false;
  @property({ type: Number }) public coilDryMinutes = 20;
  @property({ type: String }) public coilDryMode: "fan_only" | "dry" = "fan_only";
  @property({ type: String }) public coilDryFanMode = "low";
  @property({ type: Number }) public coilDryMinCoolingMinutes = 10;
  @property({ type: Number }) public coilDryDrainMinutes = 0;
  /** Union of fan_modes across all configured AC entities, named as Home Assistant names them. */
  @property({ attribute: false }) public availableFanModes: FanModeOption[] = [];

  private _numberField(
    key: string,
    value: number,
    labelKey: TranslationKey,
    suffixKey: TranslationKey,
    hintKey: TranslationKey,
    min: number,
    max: number,
  ) {
    const l = this.hass.language;
    return numberRow({
      hass: this.hass,
      label: localize(labelKey, l),
      info: localize(hintKey, l),
      unit: localize(suffixKey, l),
      min,
      max,
      value,
      onChange: (v) => this._fire(key, v),
    });
  }

  render() {
    const l = this.hass.language;
    // Fall back to HA's documented fan mode constants when no AC reports any.
    const fanModes = this.availableFanModes.length
      ? this.availableFanModes
      : ["low", "medium", "high"].map((value) => ({
          value,
          label: fanModeLabel(this.hass, value),
        }));

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("coil_dry.switch", l)}
          .checked=${this.coilDryEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("coilDryEnabled", e.detail)}
        >
          <rs-info-icon slot="end" .text=${localize("coil_dry.hint", l)}></rs-info-icon>
        </rs-list-row>
      </div>

      ${
        this.coilDryEnabled
          ? html`
              <div class="settings-section">
                ${this._numberField(
                  "coilDryMinutes",
                  this.coilDryMinutes,
                  "coil_dry.duration_label",
                  "coil_dry.duration_suffix",
                  "coil_dry.duration_hint",
                  1,
                  60,
                )}
                ${this._numberField(
                  "coilDryMinCoolingMinutes",
                  this.coilDryMinCoolingMinutes,
                  "coil_dry.min_cooling_label",
                  "coil_dry.min_cooling_suffix",
                  "coil_dry.min_cooling_hint",
                  1,
                  240,
                )}
                ${this._numberField(
                  "coilDryDrainMinutes",
                  this.coilDryDrainMinutes,
                  "coil_dry.drain_label",
                  "coil_dry.drain_suffix",
                  "coil_dry.drain_hint",
                  0,
                  15,
                )}
              </div>

              <div class="settings-section stack">
                <div class="threshold-field">
                  <rs-field .info=${localize("coil_dry.fan_mode_hint", l)}>
                    <ha-select
                      .label=${localize("coil_dry.fan_mode_label", l)}
                      .value=${this.coilDryFanMode === "" ? KEEP : this.coilDryFanMode}
                      .options=${[
                        { value: KEEP, label: localize("coil_dry.fan_mode_keep", l) },
                        ...fanModes,
                      ]}
                      @selected=${(e: Event) => {
                        const v = getSelectValue(e);
                        const current = this.coilDryFanMode === "" ? KEEP : this.coilDryFanMode;
                        if (v && v !== current) this._fire("coilDryFanMode", v === KEEP ? "" : v);
                      }}
                      @closed=${(e: Event) => e.stopPropagation()}
                      fixedMenuPosition
                    >
                      <ha-list-item value="${KEEP}"
                        >${localize("coil_dry.fan_mode_keep", l)}</ha-list-item
                      >
                      ${fanModes.map(
                        (fm) => html`<ha-list-item value=${fm.value}>${fm.label}</ha-list-item>`,
                      )}
                    </ha-select>
                  </rs-field>
                </div>

                <rs-field
                  .label=${localize("coil_dry.mode_label", l)}
                  .info=${localize("coil_dry.mode_hint", l)}
                >
                  <rs-segmented
                    wrap
                    .label=${localize("coil_dry.mode_label", l)}
                    .options=${[
                      { value: "fan_only", label: localize("coil_dry.mode_fan_only", l) },
                      { value: "dry", label: localize("coil_dry.mode_dry", l) },
                    ]}
                    .value=${this.coilDryMode}
                    @value-changed=${(e: CustomEvent<{ value: string }>) => {
                      const v = e.detail.value as "fan_only" | "dry";
                      if (v && v !== this.coilDryMode) this._fire("coilDryMode", v);
                    }}
                  ></rs-segmented>
                  ${
                    this.coilDryMode === "dry"
                      ? html`<span class="field-hint warning"
                          >${localize("coil_dry.mode_dry_warning", l)}</span
                        >`
                      : nothing
                  }
                </rs-field>
              </div>
            `
          : nothing
      }
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .field-hint.warning {
        color: var(--rs-warn-text);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-coil-dry": RsSettingsCoilDry;
  }
}

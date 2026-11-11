import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ClimateMode, HomeAssistant } from "../types";
import { localize } from "../utils/localize";
import { tokens } from "../styles/tokens";
import { formStyles } from "../styles/form-styles";
import { formatNumber } from "../utils/format";
import { formatTempLocale, tempUnit, toDisplayDelta } from "../utils/temperature";
import "./shared/rs-number-field";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";

/** Mirrors HEAT_SOURCE_HYSTERESIS / HEAT_SOURCE_LARGE_GAP_MULTIPLIER (const.py). */
const HYSTERESIS_K = 0.3;
const BOTH_MULTIPLIER = 2;

@customElement("rs-heat-source-section")
export class RsHeatSourceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public enabled = false;
  @property({ type: Number }) public primaryDelta = 1.5;
  @property({ type: Number }) public outdoorThreshold = 5.0;
  @property({ type: Number }) public acMinOutdoor = -15.0;
  @property({ type: Boolean }) public editing = false;
  @property({ type: Boolean }) public priceAware = false;
  /** A price source is set in the settings; without one the option is hidden. */
  @property({ type: Boolean }) public priceConfigured = false;
  /**
   * Current outdoor temperature; null = none, then the gap decides between the sources.
   * Undefined (not passed) reads as known.
   */
  @property({ attribute: false }) public outdoorTemp: number | null | undefined = undefined;
  @property({ type: String }) public climateMode: ClimateMode = "auto";

  static styles = [
    tokens,
    formStyles,
    css`
      :host {
        display: block;
        --rs-form-inline: var(--rs-space-4);
      }
    `,
  ];

  private _abs(c: number): string {
    return `${formatTempLocale(c, this.hass, 0, 1)} ${tempUnit(this.hass)}`;
  }

  private _delta(k: number): string {
    return `${formatNumber(toDisplayDelta(k, this.hass), this.hass, 0, 1)} ${tempUnit(this.hass)}`;
  }

  /** What decides the source now, in one line. */
  private _ruleText(): string {
    const l = this.hass.language;
    if (!this.enabled) {
      return localize(
        this.climateMode === "heat_only"
          ? "heat_source.summary_disabled_heat_only"
          : "heat_source.summary_disabled",
        l,
      );
    }
    const rule =
      this.outdoorTemp !== null
        ? localize("heat_source.rule_outdoor", l, { temp: this._abs(this.outdoorThreshold) })
        : localize("heat_source.rule_gap", l, { delta: this._delta(this.primaryDelta) });
    return this.priceConfigured && this.priceAware
      ? `${localize("heat_source.price_aware_summary", l)} · ${rule}`
      : rule;
  }

  render() {
    const l = this.hass.language;

    if (!this.editing) {
      return html`<rs-list-row
        clickable
        chevron
        icon="mdi:swap-horizontal"
        .heading=${localize("heat_source.toggle", l)}
        .secondary=${this._ruleText()}
        .value=${localize(this.enabled ? "detail.on" : "detail.off", l)}
        @row-click=${this._fireEdit}
      ></rs-list-row>`;
    }

    const both = this.primaryDelta * BOTH_MULTIPLIER + HYSTERESIS_K;
    return html`
      <div class="group">
        <rs-list-row
          switch
          wrap
          .heading=${localize("heat_source.toggle", l)}
          .secondary=${this._ruleText()}
          .checked=${this.enabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._emit("heat_source_orchestration", e.detail)}
        >
          <rs-info-icon slot="end" .text=${localize("heat_source.toggle_hint", l)}></rs-info-icon>
        </rs-list-row>
      </div>
      ${
        this.enabled
          ? html`<div class="group">
              <h4 class="group-title">${localize("heat_source.group_rules", l)}</h4>
              <rs-number-field
                .hass=${this.hass}
                kind="temperature"
                .label=${localize("heat_source.outdoor_threshold", l)}
                .info=${localize("heat_source.outdoor_threshold_hint", l)}
                .value=${this.outdoorThreshold}
                .min=${-20}
                .max=${25}
                .step=${1}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._emit("heat_source_outdoor_threshold", e.detail.value)}
              ></rs-number-field>
              <rs-number-field
                .hass=${this.hass}
                kind="temperature-delta"
                .label=${localize("heat_source.primary_delta", l)}
                .info=${localize("heat_source.primary_delta_hint", l)}
                .hint=${localize("heat_source.both_from", l, { delta: this._delta(both) })}
                .value=${this.primaryDelta}
                .min=${0.5}
                .max=${5.0}
                .step=${0.1}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._emit("heat_source_primary_delta", e.detail.value)}
              ></rs-number-field>
              <rs-number-field
                .hass=${this.hass}
                kind="temperature"
                .label=${localize("heat_source.ac_min_outdoor", l)}
                .info=${localize("heat_source.ac_min_outdoor_hint", l)}
                .value=${this.acMinOutdoor}
                .min=${-30}
                .max=${5}
                .step=${1}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._emit("heat_source_ac_min_outdoor", e.detail.value)}
              ></rs-number-field>
              ${
                this.priceConfigured
                  ? html`<rs-list-row
                      switch
                      wrap
                      .heading=${localize("heat_source.price_aware", l)}
                      .checked=${this.priceAware}
                      @toggle-changed=${(e: CustomEvent<boolean>) =>
                        this._emit("heat_source_price_aware", e.detail)}
                    >
                      <rs-info-icon
                        slot="end"
                        .text=${localize("heat_source.price_aware_hint", l)}
                      ></rs-info-icon>
                    </rs-list-row>`
                  : nothing
              }
            </div>`
          : nothing
      }
    `;
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _fireEdit(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-heat-source-section": RsHeatSourceSection;
  }
}

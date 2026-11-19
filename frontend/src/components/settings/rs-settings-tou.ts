/**
 * rs-settings-tou – Time-of-Use tariff awareness: source bindings and the
 * tier dictionary. Tariff *scheduling* lives on the device card
 * (follow-up PR): the rooms' `tou_overrides` rows anchor actions to the
 * tiers defined here.
 *
 * The tariff source is structured as two exclusive choices so the panel only
 * shows the fields the selected source actually needs:
 *
 * * "Current tier from" — period sensor, cost sensor (+ thresholds) or flags;
 *   mirrors the manager cascade. Selecting a radio writes an explicit
 *   ``tou_tier_source``; "auto" (never touched) derives from what is bound.
 * * "Plan the tariff future from" — calendars, next-change sensor, or none;
 *   drives whether pre-conditioning/schedule rows can see beyond the current
 *   tier (``tou_lookahead``).
 *
 * Bound-but-unselected sources stay in settings (ignored by the manager).
 * The dictionary block ("Tiers as your source feeds them") pulls the live
 * prices and vocabulary from those sources and lets the user assign words
 * the built-in recognition could not place.
 */
import { html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  TouCalendarBinding,
  TouExtraTier,
  TouLookahead,
  TouRateWindow,
  TouTier,
  TouTierInfo,
  TouTierInfoTier,
  TouTierSource,
} from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import {
  tempRange,
  tempStep,
  tempUnit,
  toCelsius,
  toCelsiusDelta,
  toDisplay,
  toDisplayDelta,
} from "../../utils/temperature";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-duration-field";

const TOU_TIERS: TouTier[] = ["peak", "mid", "off", "ultra_low"];
const ANY_TIER = "__any";
const WEEKDAYS = [
  { value: "monday", abbr: "Mo", key: "mon" },
  { value: "tuesday", abbr: "Tu", key: "tue" },
  { value: "wednesday", abbr: "We", key: "wed" },
  { value: "thursday", abbr: "Th", key: "thu" },
  { value: "friday", abbr: "Fr", key: "fri" },
  { value: "saturday", abbr: "Sa", key: "sat" },
  { value: "sunday", abbr: "Su", key: "sun" },
] as const;
const CLOSE_ICON =
  "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";
const CHEVRON_UP = "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z";
const CHEVRON_DOWN = "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z";

@customElement("rs-settings-tou")
export class RsSettingsTou extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public touEnabled = false;
  @property({ type: String }) public touTierSource: TouTierSource = "auto";
  @property({ type: String }) public touLookahead: TouLookahead = "auto";
  @property({ type: String }) public touRateEntity = "";
  @property({ type: String }) public touPeriodEntity = "";
  @property({ type: String }) public touNextChangeEntity = "";
  @property({ type: String }) public touNextRateEntity = "";
  @property({ type: String }) public touNextPeriodEntity = "";
  @property({ type: String }) public touNextChangeTier: TouTier | "" = "";
  @property({ type: Array }) public touCalendarEntities: TouCalendarBinding[] = [];
  @property({ type: Array }) public touRateWindows: TouRateWindow[] = [];
  @property({ attribute: false }) public touFlagEntities: Partial<Record<TouTier, string>> = {};
  @property({ attribute: false }) public touPeakThreshold: number | null = null;
  @property({ attribute: false }) public touMidThreshold: number | null = null;
  @property({ attribute: false }) public touUltraThreshold: number | null = null;
  /** Tier dictionary (prices + vocabulary) observed from the live sources. */
  @property({ attribute: false }) public touTierInfo: TouTierInfo | null = null;
  /** User-assigned period vocabulary: raw lower-cased state -> tier. */
  @property({ attribute: false }) public touPeriodAliases: Record<string, string> = {};
  /** Sensor-driven energy tier registry (S6), edited by _renderExtraTiers. */
  @property({ type: Array }) public touExtraTiers: TouExtraTier[] = [];
  /**
   * Global store limits (defaults mirror const.py DEFAULT_TOU_*). Shown in
   * the fine-tune section; per-room overrides on the room card win per key.
   */
  @property({ type: Number }) public touHeatMin = 17;
  @property({ type: Number }) public touHeatMax = 28;
  @property({ type: Number }) public touCoolMin = 18;
  @property({ type: Number }) public touCoolMax = 30;
  @property({ type: Number }) public touSwing = 3;
  @property({ type: Number }) public touStoreGap = 1;
  /** Price-weighted MPC: energy cost competes with comfort in the plan. */
  @property({ type: Boolean }) public touPriceWeighting = true;
  @state() private _fineTuneOpen = false;

  static styles = [
    ...RsSettingsBase.settingsBaseStyles,
    css`
      .hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin: 4px 0 12px;
      }
      .tier-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-top: 12px;
      }
      .tier-grid ha-textfield,
      .tier-grid ha-entity-picker,
      .tier-grid ha-select {
        width: 100%;
      }
      .dic-rows {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin: 8px 0;
      }
      .dic-row {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        font-size: 13px;
      }
      .dic-tier {
        font-weight: 500;
        min-width: 150px;
      }
      .dic-price {
        color: var(--secondary-text-color);
        min-width: 90px;
      }
      .dic-count {
        color: var(--secondary-text-color);
        font-size: 11px;
      }
      .dic-now {
        font-size: 11px;
        color: var(--success-color, #43a047);
        border: 1px solid currentColor;
        border-radius: 8px;
        padding: 0 6px;
        margin-left: 4px;
      }
      .dic-next {
        font-size: 11px;
        color: var(--warning-color, #ff9800);
        border: 1px solid currentColor;
        border-radius: 8px;
        padding: 0 6px;
        margin-left: 4px;
      }
      .dic-summary {
        font-size: 13px;
        color: var(--primary-text-color);
        background: rgba(0, 0, 0, 0.04);
        border-radius: 8px;
        padding: 6px 10px;
        margin: 6px 0 2px;
      }
      .dic-next-hint {
        font-size: 12px;
        color: var(--warning-color, #ff9800);
        margin: 2px 0 4px;
      }
      .dic-unmapped-title {
        font-weight: 500;
        margin-top: 10px;
      }
      .vocab-chip {
        font-family: var(--code-font-family, monospace);
        font-size: 12px;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        padding: 1px 6px;
      }
      .vocab-chip.alias {
        cursor: pointer;
        border-color: var(--primary-color, #0389ff);
      }
      .col-header {
        font-size: 12px;
        font-weight: 500;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .fine-tune-row {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-top: 16px;
        padding: 8px 0;
        cursor: pointer;
      }
      .fine-tune-row ha-icon {
        margin-top: 2px;
        color: var(--secondary-text-color);
      }
      .fine-tune-label {
        font-size: 14px;
        font-weight: 500;
      }
      .fine-tune-row .hint {
        margin-bottom: 0;
      }
      .shaping-grid {
        margin-top: 8px;
      }
      .col-header {
        font-size: 12px;
        font-weight: 500;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .col-span {
        grid-column: 1 / -1;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-top: 6px;
      }
      .section-label {
        font-size: 14px;
        font-weight: 500;
        margin: 16px 0 4px;
      }
      .radio-option {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 8px 0;
        cursor: pointer;
      }
      .radio-option input {
        margin-top: 3px;
        flex-shrink: 0;
        accent-color: var(--accent-color);
      }
      .radio-text {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }
      .radio-title {
        font-size: 14px;
        font-weight: 500;
      }
      .radio-desc {
        font-size: 12px;
        color: var(--secondary-text-color);
        line-height: 1.5;
      }
      .mode-fields {
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin: 4px 0 8px 26px;
      }
      .mode-fields ha-entity-picker,
      .mode-fields ha-select {
        width: 100%;
      }
      .picker-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .picker-row ha-entity-picker {
        flex: 1;
        min-width: 0;
      }
      .source-row {
        align-items: center;
      }
      .source-row .source-del {
        justify-self: end;
      }
      .source-tools {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 4px;
      }
      .source-enabled {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        cursor: pointer;
      }
      .window-row {
        display: flex;
        align-items: flex-end;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
      }
      .window-row ha-textfield {
        flex: 1;
        min-width: 90px;
      }
      .window-days {
        display: flex;
        gap: 2px;
      }
      .day-chip {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
        font-size: 11px;
        color: var(--secondary-text-color);
        cursor: pointer;
        padding: 2px 3px;
      }
      .day-chip input {
        accent-color: var(--accent-color);
      }
      .window-row--add {
        align-items: center;
        border: 1px dashed var(--divider-color);
        border-radius: 8px;
        padding: 10px 12px;
        cursor: pointer;
        color: var(--secondary-text-color);
        gap: 10px;
      }
      .rule-room {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
      }
      .add-button {
        margin-top: 8px;
      }
      @media (max-width: 500px) {
        .tier-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  /** The tier source the panel shows: explicit choice, else what is bound. */
  private _tierMode(): Exclude<TouTierSource, "auto"> {
    if (this.touTierSource !== "auto") return this.touTierSource;
    if (this.touPeriodEntity) return "period";
    if (Object.values(this.touFlagEntities || {}).some((v) => v)) return "flags";
    return "rate";
  }

  /** The lookahead source the panel shows: explicit choice, else what is bound. */
  private _lookaheadMode(): Exclude<TouLookahead, "auto"> {
    if (this.touLookahead !== "auto") return this.touLookahead;
    if (
      this.touCalendarEntities.some((c) => c.entity_id) ||
      this.touRateWindows.some((w) => w.start && w.end)
    )
      return "calendar";
    if (this.touNextRateEntity || this.touNextPeriodEntity) return "next_change_rate";
    if (this.touNextChangeEntity) return "next_change";
    return "next_change_rate";
  }

  render() {
    const l = this.hass.language;
    const tier = this._tierMode();
    const look = this._lookaheadMode();
    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("tou.enabled", l)}
          .checked=${this.touEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("touEnabled", e.detail)}
        ></rs-list-row>
        <p class="note">${localize("tou.enabled_hint", l)}</p>
      </div>
      ${
        this.touEnabled
          ? html`
              <div class="section-label">${localize("tou.source", l)}</div>
              <div class="hint">${localize("tou.source_hint", l)}</div>

              <div class="section-label">${localize("tou.tier_from", l)}</div>
              ${this._radioOption(
                "tou_src",
                "tou.src.rate",
                "tou.src.rate_desc",
                "rate",
                tier,
                (v) => this._fire("touTierSource", v),
              )}
              ${this._radioOption(
                "tou_src",
                "tou.src.period",
                "tou.src.period_desc",
                "period",
                tier,
                (v) => this._fire("touTierSource", v),
              )}
              ${this._radioOption(
                "tou_src",
                "tou.src.flags",
                "tou.src.flags_desc",
                "flags",
                tier,
                (v) => this._fire("touTierSource", v),
              )}
              <div class="mode-fields">
                ${
                  tier === "period"
                    ? html`<ha-entity-picker
                          .hass=${this.hass}
                          .value=${this.touPeriodEntity}
                          .includeDomains=${["sensor", "input_select"]}
                          .label=${localize("tou.period_entity", l)}
                          @value-changed=${(e: CustomEvent) =>
                            this._fire("touPeriodEntity", (e.detail?.value as string) ?? "")}
                        ></ha-entity-picker>
                        ${this._rateAuxPicker()}`
                    : nothing
                }
                ${
                  tier === "rate"
                    ? html`<ha-entity-picker
                          .hass=${this.hass}
                          .value=${this.touRateEntity}
                          .includeDomains=${["sensor", "input_number"]}
                          .label=${localize("tou.rate_entity", l)}
                          @value-changed=${(e: CustomEvent) =>
                            this._fire("touRateEntity", (e.detail?.value as string) ?? "")}
                        ></ha-entity-picker>
                        <div class="section-label">${localize("tou.thresholds", l)}</div>
                        <div class="hint">${localize("tou.thresholds_hint", l)}</div>
                        <div class="tier-grid">
                          ${this._thresholdField("touPeakThreshold", localize("tou.peak_threshold", l), this.touPeakThreshold)}
                          ${this._thresholdField("touMidThreshold", localize("tou.mid_threshold", l), this.touMidThreshold)}
                          ${this._thresholdField("touUltraThreshold", localize("tou.ultra_threshold", l), this.touUltraThreshold)}
                        </div>`
                    : nothing
                }
                ${
                  tier === "flags"
                    ? html`<div class="hint">${localize("tou.flags_hint", l)}</div>
                        <div class="tier-grid">
                          ${TOU_TIERS.map(
                            (t) =>
                              html`<ha-entity-picker
                                .hass=${this.hass}
                                .value=${this.touFlagEntities[t] ?? ""}
                                .includeDomains=${["input_boolean", "binary_sensor"]}
                                .label=${localize(`tou.tier.${t}`, l)}
                                @value-changed=${(e: CustomEvent) => {
                                  const updated = {
                                    ...this.touFlagEntities,
                                    [t]: (e.detail?.value as string) ?? "",
                                  };
                                  this._fire("touFlagEntities", updated);
                                }}
                              ></ha-entity-picker>`,
                          )}
                        </div>
                        ${this._rateAuxPicker()}`
                    : nothing
                }
              </div>

              <div class="section-label">${localize("tou.future_from", l)}</div>
              ${this._radioOption(
                "tou_look",
                "tou.lk.calendar",
                "tou.lk.calendar_desc",
                "calendar",
                look,
                (v) => this._fire("touLookahead", v),
              )}
              ${this._radioOption(
                "tou_look",
                "tou.lk.next_rate",
                "tou.lk.next_rate_desc",
                "next_change_rate",
                look,
                (v) => this._fire("touLookahead", v),
              )}
              ${this._radioOption(
                "tou_look",
                "tou.lk.next_change",
                "tou.lk.next_change_desc",
                "next_change",
                look,
                (v) => this._fire("touLookahead", v),
              )}
              ${this._radioOption(
                "tou_look",
                "tou.lk.none",
                "tou.lk.none_desc",
                "none",
                look,
                (v) => this._fire("touLookahead", v),
              )}
              <div class="mode-fields">
                ${
                  look === "calendar"
                    ? html`${this.touCalendarEntities.map((c, idx) => this._renderCalendarRow(c, idx))}
                        ${
                          this.touCalendarEntities.length < 4
                            ? html`<ha-button class="add-button" @click=${this._addCalendar}>
                                <ha-icon icon="mdi:plus" slot="icon"></ha-icon>
                                ${localize("tou.add_calendar", l)}
                              </ha-button>`
                            : nothing
                        }
                        <div class="section-label">${localize("tou.rate_windows", l)}</div>
                        <div class="hint">${localize("tou.rate_windows_hint", l)}</div>
                        ${this.touRateWindows.map((w, idx) => this._renderRateWindow(w, idx))}
                        <div class="window-row window-row--add" @click=${this._addRateWindow}>
                          <ha-icon icon="mdi:plus"></ha-icon>
                          <span>${localize("tou.add_window", l)}</span>
                        </div>`
                    : nothing
                }
                ${
                  look === "next_change_rate"
                    ? html`${this._nextChangeTimeRow()}
                        <div class="picker-row">
                          <ha-entity-picker
                            .hass=${this.hass}
                            .value=${this.touNextRateEntity}
                            .includeDomains=${["sensor", "input_number"]}
                            .label=${localize("tou.next_rate_entity", l)}
                            @value-changed=${(e: CustomEvent) =>
                              this._fire("touNextRateEntity", (e.detail?.value as string) ?? "")}
                          ></ha-entity-picker>
                          ${
                            this.touNextRateEntity
                              ? html`<ha-icon-button
                                  .path=${CLOSE_ICON}
                                  .label=${localize("tou.clear", l)}
                                  @click=${() => this._fire("touNextRateEntity", "")}
                                ></ha-icon-button>`
                              : nothing
                          }
                        </div>
                        <div class="hint">${localize("tou.next_rate_hint", l)}</div>
                        ${this._nextPeriodPicker()}`
                    : nothing
                }
                ${
                  look === "next_change"
                    ? html`${this._nextChangeTimeRow()} ${this._renderNextTierSelect()}
                        <div class="hint">${localize("tou.next_change_tier_hint", l)}</div>
                        ${this._nextPeriodPicker()}`
                    : nothing
                }
              </div>

              ${this._renderExtraTiers(l)} ${this._renderTierDictionary(l)}

              <div class="fine-tune-row" @click=${() => (this._fineTuneOpen = !this._fineTuneOpen)}>
                <ha-icon
                  icon=${this._fineTuneOpen ? "mdi:chevron-down" : "mdi:chevron-right"}
                ></ha-icon>
                <div>
                  <div class="fine-tune-label">${localize("tou.fine_tune", l)}</div>
                  <div class="hint">${localize("tou.fine_tune_hint", l)}</div>
                </div>
              </div>
              ${
                this._fineTuneOpen
                  ? html`
                      <div class="section-label">${localize("tou.shaping", l)}</div>
                      <div class="hint">${localize("tou.shaping_hint", l)}</div>
                      <div class="tier-grid shaping-grid">
                        <div class="col-header">${localize("tou.col_heating", l)}</div>
                        <div class="col-header">${localize("tou.col_cooling", l)}</div>
                        ${this._tempField("touHeatMin", localize("tou.clamp_min", l), this.touHeatMin, 5, 35)}
                        ${this._tempField("touCoolMin", localize("tou.clamp_min", l), this.touCoolMin, 5, 35)}
                        ${this._tempField("touHeatMax", localize("tou.clamp_max", l), this.touHeatMax, 10, 40)}
                        ${this._tempField("touCoolMax", localize("tou.clamp_max", l), this.touCoolMax, 10, 40)}
                        <div class="col-span">${localize("tou.both_steps", l)}</div>
                        ${this._deltaField("touSwing", localize("tou.swing", l), this.touSwing, 0, 10)}
                        ${this._gapField()}
                      </div>
                      <rs-list-row
                        switch
                        wrap
                        .heading=${localize("tou.price_weighting", l)}
                        .checked=${this.touPriceWeighting}
                        @toggle-changed=${(e: CustomEvent<boolean>) =>
                          this._fire("touPriceWeighting", e.detail)}
                      ></rs-list-row>
                      <div class="hint">${localize("tou.price_weighting_hint", l)}</div>
                    `
                  : nothing
              }
            `
          : nothing
      }
    `;
  }

  private _radioOption(
    group: string,
    titleKey: TranslationKey,
    descKey: TranslationKey,
    value: string,
    selected: string,
    onSelect: (v: string) => void,
  ) {
    const l = this.hass.language;
    return html`<label class="radio-option">
      <input
        type="radio"
        name=${group}
        .checked=${selected === value}
        @change=${() => onSelect(value)}
      />
      <span class="radio-text">
        <span class="radio-title">${localize(titleKey, l)}</span>
        <span class="radio-desc">${localize(descKey, l)}</span>
      </span>
    </label>`;
  }

  /** Cost sensor shown as auxiliary input in period/flags modes: it still
   * feeds the rate sensors and price-weighted planning without deciding the
   * tier there. */
  private _rateAuxPicker() {
    const l = this.hass.language;
    return html`<div>
      <ha-entity-picker
        .hass=${this.hass}
        .value=${this.touRateEntity}
        .includeDomains=${["sensor", "input_number"]}
        .label=${localize("tou.rate_entity", l)}
        @value-changed=${(e: CustomEvent) => this._fire("touRateEntity", (e.detail?.value as string) ?? "")}
      ></ha-entity-picker>
      <div class="hint">${localize("tou.rate_aux_hint", l)}</div>
    </div>`;
  }

  /** Timestamp picker shared by both next-change lookahead modes. */
  private _nextChangeTimeRow() {
    const l = this.hass.language;
    return html`<div class="picker-row">
      <ha-entity-picker
        .hass=${this.hass}
        .value=${this.touNextChangeEntity}
        .includeDomains=${["sensor", "input_datetime"]}
        .label=${localize("tou.next_change_entity", l)}
        @value-changed=${(e: CustomEvent) => this._fire("touNextChangeEntity", (e.detail?.value as string) ?? "")}
      ></ha-entity-picker>
      ${
        this.touNextChangeEntity
          ? html`<ha-icon-button
              .path=${CLOSE_ICON}
              .label=${localize("tou.clear", l)}
              @click=${() => this._fire("touNextChangeEntity", "")}
            ></ha-icon-button>`
          : nothing
      }
    </div>`;
  }

  /** Optional next-period *name* sensor: providers that label the upcoming
   * period ("ulo_mid_peak") let RoomMind learn the coming tier from the same
   * vocabulary recognition as the current period, thresholds not required. */
  private _nextPeriodPicker() {
    const l = this.hass.language;
    return html` <div class="picker-row">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.touNextPeriodEntity}
          .includeDomains=${["sensor", "input_select"]}
          .label=${localize("tou.next_period_entity", l)}
          @value-changed=${(e: CustomEvent) =>
            this._fire("touNextPeriodEntity", (e.detail?.value as string) ?? "")}
        ></ha-entity-picker>
        ${
          this.touNextPeriodEntity
            ? html`<ha-icon-button
                .path=${CLOSE_ICON}
                .label=${localize("tou.clear", l)}
                @click=${() => this._fire("touNextPeriodEntity", "")}
              ></ha-icon-button>`
            : nothing
        }
      </div>
      <div class="hint">${localize("tou.next_period_hint", l)}</div>`;
  }

  /** Next-change tier select; "Not set" ("" ) disables the lookahead step. */
  private _renderNextTierSelect() {
    const l = this.hass.language;
    return html`<ha-select
      .label=${localize("tou.next_change_tier", l)}
      .value=${this.touNextChangeTier || ANY_TIER}
      .options=${[
        { value: ANY_TIER, label: localize("tou.not_set", l) },
        ...TOU_TIERS.map((t) => ({ value: t, label: localize(`tou.tier.${t}`, l) })),
      ]}
      @selected=${(e: Event) => {
        const v = getSelectValue(e);
        if (v) this._fire("touNextChangeTier", v === ANY_TIER ? "" : v);
      }}
      @closed=${(e: Event) => e.stopPropagation()}
      fixedMenuPosition
    ></ha-select>`;
  }

  /** Global consent-band bound, edited in the user's unit and stored in °C. */
  private _tempField(key: string, label: string, valueC: number, minC: number, maxC: number) {
    const range = tempRange(minC, maxC, this.hass);
    return html`<ha-textfield
      type="number"
      .value=${String(toDisplay(valueC, this.hass))}
      .label=${label}
      .suffix=${tempUnit(this.hass)}
      min=${range.min}
      max=${range.max}
      step=${tempStep(this.hass)}
      @change=${(e: Event) => {
        const v = parseFloat((e.target as HTMLInputElement).value);
        if (!isNaN(v)) this._fire(key, toCelsius(v, this.hass));
      }}
    ></ha-textfield>`;
  }

  /** A deviation allowance (swing): a delta, not a point on the scale. */
  private _deltaField(key: string, label: string, deltaC: number, minC: number, maxC: number) {
    return html`<ha-textfield
      type="number"
      .value=${String(toDisplayDelta(deltaC, this.hass))}
      .label=${label}
      .suffix=${`Δ${tempUnit(this.hass)}`}
      min=${String(toDisplayDelta(minC, this.hass))}
      max=${String(toDisplayDelta(maxC, this.hass))}
      step=${tempStep(this.hass)}
      @change=${(e: Event) => {
        const v = parseFloat((e.target as HTMLInputElement).value);
        if (!isNaN(v)) this._fire(key, toCelsiusDelta(v, this.hass));
      }}
    ></ha-textfield>`;
  }

  /** Price ratio, not a temperature: no unit conversion, just a number. */
  private _gapField() {
    const l = this.hass.language;
    return html`<ha-textfield
      type="number"
      .value=${String(this.touStoreGap)}
      .label=${localize("tou.store_gap", l)}
      .suffix=${"×"}
      min="1"
      max="10"
      step="0.1"
      @change=${(e: Event) => {
        const v = parseFloat((e.target as HTMLInputElement).value);
        if (!isNaN(v)) this._fire("touStoreGap", Math.max(1, v));
      }}
    ></ha-textfield>`;
  }

  private _thresholdField(field: string, label: string, value: number | null) {
    return html`<ha-textfield
      type="number"
      step="0.001"
      .value=${value == null ? "" : String(value)}
      .label=${label}
      @change=${(e: Event) => {
        const raw = (e.target as HTMLInputElement).value.trim();
        const v = raw === "" ? null : parseFloat(raw);
        this._fire(field, v == null || isNaN(v) ? null : v);
      }}
    ></ha-textfield>`;
  }

  private _renderCalendarRow(binding: TouCalendarBinding, idx: number) {
    return html`
      <div class="rule-room">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${binding.entity_id}
          .includeDomains=${["calendar"]}
          style="flex:1"
          @value-changed=${(e: CustomEvent) => {
            const updated = [...this.touCalendarEntities];
            updated[idx] = { ...updated[idx], entity_id: (e.detail?.value as string) ?? "" };
            this._fire("touCalendarEntities", updated);
          }}
        ></ha-entity-picker>
        <ha-select
          .value=${binding.tier}
          .options=${TOU_TIERS.map((t) => ({ value: t, label: localize(`tou.tier.${t}`, this.hass.language) }))}
          @selected=${(e: Event) => {
            const v = getSelectValue(e);
            if (v) {
              const updated = [...this.touCalendarEntities];
              updated[idx] = { ...updated[idx], tier: v as TouTier };
              this._fire("touCalendarEntities", updated);
            }
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
        ></ha-select>
        <ha-icon-button
          .path=${CLOSE_ICON}
          @click=${() =>
            this._fire(
              "touCalendarEntities",
              this.touCalendarEntities.filter((_, i) => i !== idx),
            )}
        ></ha-icon-button>
      </div>
    `;
  }

  private _addCalendar() {
    this._fire("touCalendarEntities", [
      ...this.touCalendarEntities,
      { entity_id: "", tier: "peak" as TouTier },
    ]);
  }

  private _addRateWindow() {
    this._fire("touRateWindows", [
      ...this.touRateWindows,
      {
        id: self.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        rate: 0,
        start: "",
        end: "",
        days: [],
      },
    ]);
  }

  private _renderRateWindow(win: TouRateWindow, idx: number) {
    const l = this.hass.language;
    const update = (patch: Partial<TouRateWindow>) => {
      const updated = [...this.touRateWindows];
      updated[idx] = { ...updated[idx], ...patch };
      this._fire("touRateWindows", updated);
    };
    const toggleDay = (day: string) =>
      update({
        days: win.days.includes(day) ? win.days.filter((d) => d !== day) : [...win.days, day],
      });
    return html`<div class="window-row">
      <ha-textfield
        type="number"
        step="0.001"
        .value=${String(win.rate)}
        .label=${localize("tou.win_rate", l)}
        @change=${(e: Event) => {
          const v = parseFloat((e.target as HTMLInputElement).value);
          if (!isNaN(v)) update({ rate: v });
        }}
      ></ha-textfield>
      <ha-textfield
        .value=${win.start}
        .label=${localize("tou.win_start", l)}
        pattern="[0-9]{1,2}:[0-9]{2}"
        @change=${(e: Event) => update({ start: (e.target as HTMLInputElement).value })}
      ></ha-textfield>
      <ha-textfield
        .value=${win.end}
        .label=${localize("tou.win_end", l)}
        pattern="[0-9]{1,2}:[0-9]{2}"
        @change=${(e: Event) => update({ end: (e.target as HTMLInputElement).value })}
      ></ha-textfield>
      <div class="window-days">
        ${WEEKDAYS.map(
          (d) =>
            html`<label class="day-chip" title=${localize(`tou.day.${d.key}`, l)}>
              <input
                type="checkbox"
                .checked=${win.days.includes(d.value)}
                @change=${() => toggleDay(d.value)}
              />
              <span>${d.abbr}</span>
            </label>`,
        )}
      </div>
      <ha-icon-button
        .path=${CLOSE_ICON}
        .label=${localize("tou.clear", l)}
        @click=${() =>
          this._fire(
            "touRateWindows",
            this.touRateWindows.filter((_, i) => i !== idx),
          )}
      ></ha-icon-button>
    </div>`;
  }

  // ---- Tier dictionary: what the bound sources actually feed ----

  private _num(n: number): string {
    return new Intl.NumberFormat(this.hass.language, { maximumFractionDigits: 4 }).format(n);
  }

  private _rateText(info: TouTierInfoTier | undefined, unit: string, l: string): string {
    if (!info || info.rate == null || info.kind == null) return localize("tou.dic_no_price", l);
    const suffix = unit ? ` ${unit}` : "";
    // Two or more price points in the rolling window: show the range the
    // provider actually charges, not a single spot sample.
    const range =
      info.count != null &&
      info.count >= 2 &&
      info.min != null &&
      info.max != null &&
      info.min < info.max
        ? `${this._num(info.min)}–${this._num(info.max)}${suffix}`
        : null;
    const base = range ?? `${this._num(info.rate)}${suffix}`;
    if (info.kind === "cutoff") return `≥ ${base}`;
    if (info.kind === "last") return `${base} (${localize("tou.dic_last_known", l)})`;
    return base;
  }

  private _clock(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString(this.hass.language || undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /** One line pulling the pertinent future forward: what is active now and
   * what the sources say is coming, with cost — live reads, last-known
   * values marked. */
  private _summaryLine(info: TouTierInfo, l: string) {
    const parts: string[] = [];
    if (info.current) {
      const unit = info.unit ? ` ${info.unit}` : "";
      const stale = info.current.stale ? ` (${localize("tou.dic_last_known", l)})` : "";
      parts.push(
        `${localize("tou.dic_now_label", l)} ${this._tierName(info.current.tier, info, l)} · ${this._num(info.current.rate)}${unit}${stale}`,
      );
    }
    if (info.next) {
      const price =
        info.next.rate != null
          ? ` · ${this._num(info.next.rate)}${info.unit ? ` ${info.unit}` : ""}`
          : "";
      const stale = info.next.stale ? ` (${localize("tou.dic_last_known", l)})` : "";
      const clock = info.next.ts != null ? ` ${this._clock(info.next.ts)}` : "";
      parts.push(
        `${localize("tou.dic_next_label", l)} ${this._tierName(info.next.tier, info, l)}${clock}${price}${stale}`,
      );
    }
    const hint = info.next_hint ? localize(`tou.dic_next_hint_${info.next_hint}`, l) : "";
    if (parts.length === 0 && !hint) return nothing;
    return html`${parts.length ? html`<div class="dic-summary">${parts.join(" — ")}</div>` : nothing}${
      hint ? html`<div class="dic-next-hint">${hint}</div>` : nothing
    }`;
  }

  private _assignAlias(state: string, tier: string) {
    const next = { ...this.touPeriodAliases };
    if (tier === "") delete next[state];
    else next[state] = tier;
    this._fire("touPeriodAliases", next);
  }

  /** Registry name for an extra tier, else the localized grid label. The
   * dictionary may hold ids the tou.tier.* table never knew (S6). */
  private _tierName(tier: string, info: TouTierInfo, l: string): string {
    return info.tiers[tier]?.label ?? localize(`tou.tier.${tier}` as TranslationKey, l);
  }

  /**
   * Sensor-driven energy tiers (S6): on-site sources the grid tariff cannot
   * describe — a generator burning gas, solar production, export credit.
   * Each row binds a sensor: a flag or switch (binary_on), a number compared
   * in an explicit direction (providers' meter signs differ; RoomMind never
   * guesses), or a text/select state set. "Sustained for" debounces the ON
   * transition; OFF is instant. Cost is the typed price per kWh — 0 free
   * solar, negative credit, blank unpriced. Listed order = priority, and the
   * grid tariff keeps being tracked underneath while a tier holds.
   */
  private _renderExtraTiers(l: string) {
    const tiers = this.touExtraTiers ?? [];
    const set = (i: number, patch: Partial<TouExtraTier>) =>
      this._fire(
        "touExtraTiers",
        tiers.map((t, j) => (j === i ? { ...t, ...patch } : t)),
      );
    const remove = (i: number) =>
      this._fire(
        "touExtraTiers",
        tiers.filter((_, j) => j !== i),
      );
    /** List order IS priority (the first holding entry wins): reorder matters. */
    const move = (i: number, delta: number) => {
      const to = i + delta;
      if (to < 0 || to >= tiers.length) return;
      const next = [...tiers];
      const [entry] = next.splice(i, 1);
      next.splice(to, 0, entry);
      this._fire("touExtraTiers", next);
    };
    const add = () =>
      this._fire("touExtraTiers", [
        ...tiers,
        {
          id: `x${Date.now().toString(36)}`,
          name: localize("tou.source_default_name", l),
          entity_id: "",
          kind: "binary_on" as const,
          for_seconds: 300,
          cost: null,
          enabled: true,
        },
      ]);
    return html`
      <div class="section-label">${localize("tou.sources_title", l)}</div>
      <div class="hint">${localize("tou.sources_hint", l)}</div>
      ${tiers.map(
        (t, i) =>
          html`<div class="tier-grid source-row">
            <ha-textfield
              .label=${localize("tou.source_name", l)}
              .value=${t.name ?? ""}
              @change=${(e: Event) => set(i, { name: (e.target as HTMLInputElement).value.trim() })}
            ></ha-textfield>
            <div class="picker-row">
              <ha-entity-picker
                .hass=${this.hass}
                .value=${t.entity_id ?? ""}
                .includeDomains=${[
                  "sensor",
                  "binary_sensor",
                  "select",
                  "input_boolean",
                  "input_select",
                  "input_number",
                ]}
                .label=${localize("tou.source_entity", l)}
                @value-changed=${(e: CustomEvent) => set(i, { entity_id: (e.detail?.value as string) ?? "" })}
              ></ha-entity-picker>
              <ha-icon-button
                class="source-del"
                .path=${CLOSE_ICON}
                .label=${localize("tou.source_delete", l)}
                @click=${() => remove(i)}
              ></ha-icon-button>
            </div>
            <ha-select
              .label=${localize("tou.source_kind", l)}
              .value=${t.kind ?? "binary_on"}
              .options=${[
                { value: "binary_on", label: localize("tou.source_kind.binary_on", l) },
                { value: "numeric_above", label: localize("tou.source_kind.numeric_above", l) },
                { value: "numeric_below", label: localize("tou.source_kind.numeric_below", l) },
                { value: "state", label: localize("tou.source_kind.state", l) },
              ]}
              @selected=${(e: Event) => {
                const v = getSelectValue(e);
                if (
                  v === "binary_on" ||
                  v === "numeric_above" ||
                  v === "numeric_below" ||
                  v === "state"
                )
                  set(i, { kind: v });
              }}
              @closed=${(e: Event) => e.stopPropagation()}
              fixedMenuPosition
            ></ha-select>
            ${
              t.kind === "numeric_above" || t.kind === "numeric_below"
                ? html`<ha-textfield
                    type="number"
                    .label=${localize("tou.source_threshold", l)}
                    .value=${String(t.threshold ?? 0)}
                    @change=${(e: Event) =>
                      set(i, { threshold: parseFloat((e.target as HTMLInputElement).value) || 0 })}
                  ></ha-textfield>`
                : t.kind === "state"
                  ? html`<ha-textfield
                      .label=${localize("tou.source_states", l)}
                      .value=${(t.states ?? []).join(", ")}
                      @change=${(e: Event) =>
                        set(i, {
                          states: (e.target as HTMLInputElement).value
                            .split(",")
                            .map((s) => s.trim())
                            .filter((s) => s),
                        })}
                    ></ha-textfield>`
                  : html`<div></div>`
            }
            <rs-duration-field
              .label=${localize("tou.source_for", l)}
              .value=${t.for_seconds ?? 300}
              @value-changed=${(e: CustomEvent) => set(i, { for_seconds: e.detail.value })}
            ></rs-duration-field>
            <ha-textfield
              type="number"
              .label=${localize("tou.source_cost", l)}
              .value=${t.cost == null ? "" : String(t.cost)}
              step="0.001"
              @change=${(e: Event) => {
                const raw = (e.target as HTMLInputElement).value.trim();
                set(i, { cost: raw === "" ? null : parseFloat(raw) });
              }}
            ></ha-textfield>
            <div class="source-tools">
              <label class="source-enabled">
                <input
                  type="checkbox"
                  .checked=${t.enabled !== false}
                  @change=${(e: Event) => set(i, { enabled: (e.target as HTMLInputElement).checked })}
                />
                <span>${localize("tou.source_enabled", l)}</span>
              </label>
              <ha-icon-button
                .path=${CHEVRON_UP}
                .label=${localize("tou.row_up", l)}
                .disabled=${i === 0}
                @click=${() => move(i, -1)}
              ></ha-icon-button>
              <ha-icon-button
                .path=${CHEVRON_DOWN}
                .label=${localize("tou.row_down", l)}
                .disabled=${i >= tiers.length - 1}
                @click=${() => move(i, 1)}
              ></ha-icon-button>
            </div>
          </div>`,
      )}
      ${tiers.length > 0 ? html`<div class="hint">${localize("tou.sources_cost_hint", l)}</div>` : nothing}
      <div class="window-row window-row--add" @click=${add}>
        <ha-icon icon="mdi:plus"></ha-icon>
        <span>${localize("tou.source_add", l)}</span>
      </div>
    `;
  }

  private _renderTierDictionary(l: string) {
    const info = this.touTierInfo;
    if (info === null) {
      return html`
        <div class="section-label">${localize("tou.dic_title", l)}</div>
        <div class="hint">${localize("tou.dic_hint", l)}</div>
        <div class="hint">${localize("tou.dic_not_running", l)}</div>
      `;
    }
    return html`
      <div class="section-label">${localize("tou.dic_title", l)}</div>
      <div class="hint">${localize("tou.dic_hint", l)}</div>
      ${this._summaryLine(info, l)}
      <div class="dic-rows">
        ${Object.keys(info.tiers).map((t) => this._renderDicRow(t, info, l))}
      </div>
      ${(info.unmapped ?? []).length > 0 ? this._renderUnmapped(info, l) : nothing}
      <div class="hint">${localize("tou.dic_cutoff_hint", l)}</div>
    `;
  }

  private _renderDicRow(t: string, info: TouTierInfo, l: string) {
    const ti = info.tiers[t];
    const now = ti?.current
      ? html`<span class="dic-now">${localize("tou.dic_now", l)}</span>`
      : nothing;
    const next =
      info.next?.tier === t
        ? html`<span class="dic-next">${localize("tou.dic_next_badge", l)}</span>`
        : nothing;
    const chips = (ti?.names ?? []).map((n) => this._renderVocabChip(n, l));
    return html`
      <div class="dic-row">
        <span class="dic-tier"
          >${ti?.label || localize(`tou.tier.${t}` as TranslationKey, l)}${now}${next}</span
        >
        <span class="dic-price">${this._rateText(ti, info.unit, l)}</span>
        <span>${chips}</span>
      </div>
    `;
  }

  /** A period name that resolved to this tier; user-assigned ones carry the
   * vocabulary and can be un-assigned with a click. */
  private _renderVocabChip(name: string, l: string) {
    if (!this.touPeriodAliases[name]) {
      return html`<span class="vocab-chip">${name}</span>`;
    }
    return html`<span
      class="vocab-chip alias"
      title=${localize("tou.dic_remove_alias", l)}
      @click=${() => this._assignAlias(name, "")}
      >${name} ×</span
    >`;
  }

  private _renderUnmapped(info: TouTierInfo, l: string) {
    return html`
      <div class="dic-unmapped-title">${localize("tou.dic_unmapped_title", l)}</div>
      <div class="hint">${localize("tou.dic_unmapped_hint", l)}</div>
      <div class="dic-rows">${info.unmapped.map((u) => this._renderUnmappedRow(u, l))}</div>
    `;
  }

  private _renderUnmappedRow(u: { state: string; count: number }, l: string) {
    return html`
      <div class="dic-row">
        <span class="vocab-chip">${u.state}</span>
        <span class="dic-count">×${u.count}</span>
        <ha-select
          .label=${localize("tou.dic_assign", l)}
          .value=${this.touPeriodAliases[u.state] ?? ""}
          .options=${TOU_TIERS.map((t) => ({ value: t, label: localize(`tou.tier.${t}`, l) }))}
          @selected=${(e: Event) => {
            const v = getSelectValue(e);
            if (v) this._assignAlias(u.state, v);
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
        ></ha-select>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-tou": RsSettingsTou;
  }
}

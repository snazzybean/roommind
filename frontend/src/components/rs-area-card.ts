import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomConfig } from "../types";
import { getModeClass, formatMode } from "../utils/room-state";
import { modeStyles } from "../styles/shared-mode-styles";
import { localize } from "../utils/localize";
import { mdiEyeOff } from "../utils/icons";
import { formatTemp, tempUnit, toDisplayDelta } from "../utils/temperature";

// mdi:brain
const BRAIN_PATH =
  "M21.33,12.91C21.42,14.46 20.71,15.95 19.44,16.86L20.21,18.35C20.44,18.8 20.47,19.33 20.27,19.8C20.08,20.27 19.69,20.64 19.21,20.8L18.42,21.05C18.25,21.11 18.06,21.14 17.88,21.14C17.14,21.14 16.46,20.68 16.18,19.97L15.46,18.12C14.96,18.19 14.46,18.19 13.96,18.12L13.24,19.97C12.96,20.68 12.28,21.14 11.54,21.14C11.36,21.14 11.17,21.11 11,21.05L10.21,20.8C9.73,20.64 9.34,20.27 9.15,19.8C8.95,19.33 8.98,18.8 9.21,18.35L9.98,16.86C8.71,15.95 8,14.46 8.09,12.91L6.34,11.65C5.93,11.36 5.67,10.9 5.62,10.4C5.57,9.89 5.74,9.39 6.07,9.02L6.6,8.4C7.17,7.74 8.13,7.58 8.9,7.99L10.57,8.87C11.49,7.93 12.73,7.37 14.04,7.3C15.36,7.24 16.64,7.69 17.63,8.56L19.43,7.63C20.12,7.27 20.97,7.4 21.5,7.96L22.06,8.58C22.4,8.94 22.58,9.44 22.53,9.94C22.47,10.44 22.2,10.9 21.78,11.18L21.33,12.91Z";

@customElement("rs-area-card")
export class RsAreaCard extends LitElement {
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ type: Number }) public climateEntityCount = 0;
  @property({ type: Number }) public tempSensorCount = 0;
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "bangbang";
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: Boolean }) public reordering = false;
  @property({ type: Boolean }) public canMoveUp = false;
  @property({ type: Boolean }) public canMoveDown = false;

  static styles = [
    modeStyles,
    css`
    :host {
      display: block;
    }

    ha-card {
      cursor: pointer;
      transition: box-shadow 0.2s ease, transform 0.15s ease;
      overflow: hidden;
      position: relative;
      height: 100%;
      box-sizing: border-box;
    }

    ha-card:hover {
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
      transform: translateY(-1px);
    }

    .hide-btn {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
      color: var(--secondary-text-color);
      opacity: 0;
      transition: opacity 0.2s ease;
      position: absolute;
      top: 8px;
      right: 8px;
    }

    ha-card:hover .hide-btn {
      opacity: 0.4;
    }

    .hide-btn:hover {
      opacity: 1 !important;
    }

    /* Colored left accent based on mode */
    .accent {
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
    }

    .accent-heating {
      background: var(--warning-color, #ff9800);
    }

    .accent-cooling {
      background: #2196f3;
    }

    .accent-idle {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .accent-unconfigured {
      background: transparent;
    }

    .card-inner {
      padding: 20px 20px 16px;
    }

    /* Header row: name + badge */
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .area-name {
      font-size: 15px;
      font-weight: 500;
      color: var(--primary-text-color);
      margin: 0;
      letter-spacing: 0.01em;
    }

    /* Card-specific mode-pill overrides (smaller than default) */
    .mode-pill {
      gap: 5px;
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 12px;
    }

    .mode-dot {
      width: 7px;
      height: 7px;
    }

    /* Temperature display */
    .temp-section {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin: 12px 0 0 0;
    }

    .current-temp {
      font-size: 36px;
      font-weight: 300;
      color: var(--primary-text-color);
      line-height: 1;
    }

    .temp-unit {
      font-size: 18px;
      font-weight: 300;
      color: var(--secondary-text-color);
    }

    .target-info {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-left: auto;
    }

    .target-value {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .override-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .window-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .away-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--info-color, #2196f3);
    }

    /* Footer row: humidity + MPC status */
    .card-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 8px;
      min-height: 20px;
    }

    .humidity-info {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .mpc-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mpc-badge.active {
      color: var(--success-color, #4caf50);
      background: rgba(76, 175, 80, 0.12);
    }

    .mpc-badge.learning {
      color: var(--secondary-text-color);
      background: rgba(158, 158, 158, 0.1);
    }

    .mold-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mold-badge.warning {
      color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.12);
    }

    .mold-badge.critical {
      color: var(--error-color, #db4437);
      background: rgba(219, 68, 55, 0.12);
    }

    .mold-badge.prevention {
      color: var(--info-color, #2196f3);
      background: rgba(33, 150, 243, 0.12);
    }

    .badge-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .no-temp {
      font-size: 24px;
      font-weight: 300;
      color: var(--secondary-text-color);
      line-height: 1;
    }

    .uncontrolled-hint {
      font-size: 11px;
      color: var(--disabled-text-color, #9e9e9e);
      margin-top: 6px;
    }

    .reorder-overlay {
      position: absolute;
      inset: 0;
      z-index: 2;
      display: flex;
      pointer-events: none;
      border-radius: inherit;
      overflow: hidden;
    }

    .reorder-half {
      pointer-events: auto;
      flex: 0 0 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 0.15s ease;
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.05);
    }

    .reorder-half.left {
      border-radius: inherit;
      border-top-right-radius: 0;
      border-bottom-right-radius: 0;
      border-right: 1px solid rgba(var(--rgb-primary-text-color, 0,0,0), 0.08);
    }

    .reorder-half.right {
      border-radius: inherit;
      border-top-left-radius: 0;
      border-bottom-left-radius: 0;
      border-left: 1px solid rgba(var(--rgb-primary-text-color, 0,0,0), 0.08);
      margin-left: auto;
    }

    .reorder-half:hover {
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.1);
    }

    .reorder-half ha-icon-button {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      pointer-events: none;
    }

    .reorder-half:hover ha-icon-button {
      color: var(--primary-text-color);
    }

    .reorder-half.disabled {
      opacity: 0.25;
      cursor: default;
    }

    .reorder-half.disabled:hover {
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.05);
    }

    /* Device summary for unconfigured cards */
    .device-summary {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 8px;
    }

    .device-summary.empty {
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
    }

    /* Configure prompt for unconfigured areas */
    .configure-prompt {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .configure-text {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .configure-arrow {
      font-size: 18px;
      color: var(--primary-color);
    }

    /* Waiting state */
    .waiting {
      font-size: 13px;
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
      margin-top: 8px;
    }
  `,
  ];

  render() {
    const hasClimateDevices = this.climateEntityCount > 0;
    const hasClimateSelected = (this.config?.thermostats?.length ?? 0) > 0 || (this.config?.acs?.length ?? 0) > 0;
    const isConfigured = this.config !== null && hasClimateSelected;
    const live = this.config?.live;
    const mode = live?.mode;

    const hasSensorData = !isConfigured && live && (live.current_temp !== null || live.current_humidity !== null);
    const accentClass = isConfigured
      ? mode === "heating"
        ? "accent-heating"
        : mode === "cooling"
          ? "accent-cooling"
          : "accent-idle"
      : hasSensorData
        ? "accent-idle"
        : "accent-unconfigured";

    return html`
      <ha-card
        @click=${this._onCardClick}
      >
        <div class="accent ${accentClass}"></div>
        ${!this.reordering
          ? html`<ha-icon-button
              class="hide-btn"
              .path=${mdiEyeOff}
              @click=${this._onHideClick}
            ></ha-icon-button>`
          : nothing}
        ${this.reordering
          ? html`<div class="reorder-overlay">
              <div
                class="reorder-half left ${!this.canMoveUp ? "disabled" : ""}"
                @click=${this._onMoveUp}
              >
                <ha-icon-button
                  .path=${"M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"}
                ></ha-icon-button>
              </div>
              <div
                class="reorder-half right ${!this.canMoveDown ? "disabled" : ""}"
                @click=${this._onMoveDown}
              >
                <ha-icon-button
                  .path=${"M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"}
                ></ha-icon-button>
              </div>
            </div>`
          : nothing}
        <div class="card-inner">
          <div class="card-header">
            <h3 class="area-name">${this.config?.display_name || this.area.name}</h3>
            ${isConfigured && live
              ? html`
                  <span class="mode-pill ${getModeClass(live.mode)}">
                    <span class="mode-dot"></span>
                    ${formatMode(live.mode, this.hass.language)}${
                      live.heating_power > 0 && live.heating_power < 100
                        ? html` ${live.heating_power}%`
                        : nothing
                    }
                  </span>
                `
              : nothing}
          </div>

          ${isConfigured
            ? this._renderConfigured()
            : this.config?.live && (this.config.live.current_temp !== null || this.config.live.current_humidity !== null)
              ? this._renderSensorOnly()
              : this._renderUnconfigured(hasClimateDevices)}
        </div>
      </ha-card>
    `;
  }

  private _renderConfigured() {
    const live = this.config?.live;

    if (!live) {
      return html`<div class="waiting">${localize("card.waiting", this.hass.language)}</div>`;
    }

    const showMpcIcon = this.controlMode === "mpc";

    return html`
      <div class="temp-section">
        ${live.current_temp !== null
          ? html`
              <span class="current-temp">${formatTemp(live.current_temp, this.hass)}</span>
              <span class="temp-unit">${tempUnit(this.hass)}</span>
            `
          : html`<span class="no-temp">--</span>`}
        ${this._renderTargetInfo(live)}
      </div>
      <div class="card-footer">
        <span class="humidity-info">
          ${live.current_humidity !== null
            ? localize("card.humidity", this.hass.language, { value: live.current_humidity.toFixed(0) })
            : nothing}
        </span>
        <span class="badge-row">
          ${live.mold_risk_level && live.mold_risk_level !== "ok"
            ? html`<span class="mold-badge ${live.mold_risk_level}">
                <ha-icon icon="mdi:water-alert"></ha-icon>
                ${live.mold_risk_level === "critical"
                  ? localize("card.mold_critical", this.hass.language)
                  : localize("card.mold_warning", this.hass.language)}
              </span>`
            : nothing}
          ${live.mold_prevention_active
            ? html`<span class="mold-badge prevention">
                <ha-icon icon="mdi:shield-check"></ha-icon>
                ${localize("card.mold_prevention", this.hass.language, { delta: toDisplayDelta(live.mold_prevention_delta, this.hass).toFixed(0), unit: tempUnit(this.hass) })}
              </span>`
            : nothing}
          ${showMpcIcon
            ? html`<span class="mpc-badge ${live.mpc_active ? "active" : "learning"}">
                <ha-icon .icon=${live.mpc_active ? "mdi:brain" : "mdi:school-outline"}></ha-icon>
                ${live.mpc_active
                  ? localize("card.mpc_active", this.hass.language)
                  : localize("card.mpc_learning", this.hass.language)}
              </span>`
            : nothing}
        </span>
      </div>
      ${!this.climateControlActive
        ? html`<div class="uncontrolled-hint">${localize("card.not_controlled", this.hass.language)}</div>`
        : nothing}
    `;
  }

  private _renderTargetInfo(live: NonNullable<RoomConfig["live"]>) {
    if (live.target_temp === null && live.heat_target === null) return nothing;

    // Show range for auto mode with different heat/cool targets
    const climateMode = this.config?.climate_mode ?? "auto";
    const showRange = climateMode === "auto"
      && live.heat_target != null
      && live.cool_target != null
      && live.heat_target !== live.cool_target;

    const targetDisplay = showRange
      ? html`<span class="target-value">${formatTemp(live.heat_target!, this.hass)} – ${formatTemp(live.cool_target!, this.hass)}${tempUnit(this.hass)}</span>`
      : html`<span class="target-value">${formatTemp((live.target_temp ?? live.heat_target)!, this.hass)}${tempUnit(this.hass)}</span>`;

    return html`
      <span class="target-info">
        ${localize("card.target", this.hass.language)} ${targetDisplay}
        ${live.override_active
          ? html`<ha-icon class="override-icon" icon="mdi:timer-outline"></ha-icon>`
          : nothing}
        ${live.window_open
          ? html`<ha-icon class="window-icon" icon="mdi:window-open-variant"></ha-icon>`
          : nothing}
        ${live.presence_away
          ? html`<ha-icon class="away-icon" icon="mdi:home-off-outline"></ha-icon>`
          : nothing}
      </span>
    `;
  }

  private _renderSensorOnly() {
    const live = this.config!.live!;

    return html`
      <div class="temp-section">
        ${live.current_temp !== null
          ? html`
              <span class="current-temp">${formatTemp(live.current_temp, this.hass)}</span>
              <span class="temp-unit">${tempUnit(this.hass)}</span>
            `
          : html`<span class="no-temp">--</span>`}
      </div>
      <div class="card-footer">
        <span class="humidity-info">
          ${live.current_humidity !== null
            ? localize("card.humidity", this.hass.language, { value: live.current_humidity.toFixed(0) })
            : nothing}
        </span>
        <span class="badge-row">
          ${live.mold_risk_level && live.mold_risk_level !== "ok"
            ? html`<span class="mold-badge ${live.mold_risk_level}">
                <ha-icon icon="mdi:water-alert"></ha-icon>
                ${live.mold_risk_level === "critical"
                  ? localize("card.mold_critical", this.hass.language)
                  : localize("card.mold_warning", this.hass.language)}
              </span>`
            : nothing}
        </span>
      </div>
    `;
  }

  private _renderUnconfigured(hasClimateDevices: boolean) {
    const l = this.hass.language;
    if (!hasClimateDevices) {
      return html`<div class="device-summary empty">${localize("card.no_climate", l)}</div>`;
    }

    const ce = this.climateEntityCount;
    const ts = this.tempSensorCount;
    return html`
      <div class="device-summary">
        ${ce} ${localize(ce !== 1 ? "card.climate_devices" : "card.climate_device", l)}${ts > 0
          ? ` \u00B7 ${ts} ${localize(ts !== 1 ? "card.temp_sensors" : "card.temp_sensor", l)}`
          : ""}
      </div>
      <div class="configure-prompt">
        <span class="configure-text">${localize("card.tap_configure", l)}</span>
        <span class="configure-arrow">\u203A</span>
      </div>
    `;
  }

  private _onCardClick() {
    this.dispatchEvent(
      new CustomEvent("area-selected", {
        detail: { areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onMoveUp(e: Event) {
    e.stopPropagation();
    if (!this.canMoveUp) return;
    this.dispatchEvent(
      new CustomEvent("move-room-up", {
        detail: { areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onMoveDown(e: Event) {
    e.stopPropagation();
    if (!this.canMoveDown) return;
    this.dispatchEvent(
      new CustomEvent("move-room-down", {
        detail: { areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onHideClick(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("hide-room", {
        detail: { areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      })
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-area-card": RsAreaCard;
  }
}

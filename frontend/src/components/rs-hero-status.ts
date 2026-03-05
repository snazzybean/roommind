import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomConfig, OverrideType } from "../types";
import { getModeClass, formatMode } from "../utils/room-state";
import { modeStyles } from "../styles/shared-mode-styles";
import { localize } from "../utils/localize";
import { formatTemp, tempUnit, toDisplayDelta } from "../utils/temperature";

const PENCIL_PATH =
  "M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z";
const CHECK_PATH =
  "M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";

@customElement("rs-hero-status")
export class RsHeroStatus extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ type: Boolean }) public climateControlActive = true;
  /** Optimistic override state passed from parent for instant feedback. */
  @property({ attribute: false }) public overrideInfo: {
    active: boolean;
    type: OverrideType | null;
    temp: number | null;
    until: number | null;
  } | null = null;
  @state() private _countdown = "";
  @state() private _editingName = false;
  @state() private _nameInput = "";
  private _countdownTimer?: ReturnType<typeof setInterval>;

  static styles = [
    modeStyles,
    css`
      :host {
        display: block;
      }

      ha-card {
        padding: 28px 24px;
        position: relative;
        overflow: hidden;
      }

      .hero-accent {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
      }

      .hero-accent-heating {
        background: linear-gradient(90deg, var(--warning-color, #ff9800), #ffb74d);
      }

      .hero-accent-cooling {
        background: linear-gradient(90deg, #2196f3, #64b5f6);
      }

      .hero-accent-idle {
        background: linear-gradient(
          90deg,
          var(--disabled-text-color, #bdbdbd),
          #e0e0e0
        );
      }

      .hero-accent-none {
        background: var(--divider-color, #e0e0e0);
      }

      .hero-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
      }

      .area-name {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        margin: 0;
      }

      .hero-temps {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .hero-current {
        font-size: 48px;
        font-weight: 300;
        color: var(--primary-text-color);
        line-height: 1;
      }

      .hero-unit {
        font-size: 24px;
        font-weight: 300;
        color: var(--secondary-text-color);
      }

      .hero-target {
        margin-left: auto;
        text-align: right;
      }

      .hero-target-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .hero-target-value {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
      }

      /* Override-aware target styling */
      .hero-target-label.override-boost {
        color: var(--warning-color, #ff9800);
      }

      .hero-target-label.override-eco {
        color: #4caf50;
      }

      .hero-target-label.override-custom {
        color: #2196f3;
      }

      .hero-target-label ha-icon {
        --mdc-icon-size: 12px;
        vertical-align: middle;
      }

      .hero-target-countdown {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }

      .hero-metric {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 14px;
        color: var(--secondary-text-color);
        margin-top: 6px;
      }

      .hero-metric ha-icon {
        --mdc-icon-size: 16px;
        flex-shrink: 0;
      }

      .hero-metric.warning {
        color: var(--warning-color, #ff9800);
      }

      .hero-metric.critical {
        color: var(--error-color, #db4437);
      }

      .hero-metric.info {
        color: var(--info-color, #2196f3);
      }

      .hero-no-data {
        font-size: 14px;
        color: var(--disabled-text-color, #9e9e9e);
        font-style: italic;
        padding: 8px 0;
      }

      .hero-window-open {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        margin-bottom: 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.1);
      }

      .hero-window-open ha-icon {
        --mdc-icon-size: 18px;
      }

      .name-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-edit-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--secondary-text-color);
        opacity: 0;
        transition: opacity 0.15s;
      }

      .name-row:hover .name-edit-btn {
        opacity: 1;
      }

      @media (hover: none) {
        .name-edit-btn {
          opacity: 0.5;
        }
      }

      .name-edit-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-input {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        background: transparent;
        border: none;
        border-bottom: 2px solid var(--primary-color);
        outline: none;
        padding: 0 0 2px;
        width: 100%;
        font-family: inherit;
      }

      .name-done-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--primary-color);
      }

      .name-clear-btn {
        background: none;
        border: none;
        color: var(--secondary-text-color);
        font-size: 12px;
        cursor: pointer;
        padding: 2px 0;
        text-decoration: underline;
      }

      .uncontrolled-hint {
        font-size: 12px;
        color: var(--disabled-text-color, #9e9e9e);
        margin-top: 8px;
      }
    `,
  ];

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._clearCountdownTimer();
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has("overrideInfo") || changed.has("config")) {
      this._updateCountdown();
    }
  }

  private _clearCountdownTimer(): void {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = undefined;
    }
  }

  private _getOverrideUntil(): number | null {
    if (this.overrideInfo?.active) return this.overrideInfo.until;
    return null;
  }

  private _updateCountdown(): void {
    this._clearCountdownTimer();
    const until = this._getOverrideUntil();
    if (!until) { this._countdown = ""; return; }

    const update = () => {
      const u = this._getOverrideUntil();
      if (!u) { this._countdown = ""; this._clearCountdownTimer(); return; }
      const remaining = u - Date.now() / 1000;
      if (remaining <= 0) { this._countdown = ""; this._clearCountdownTimer(); return; }
      const h = Math.floor(remaining / 3600);
      const m = Math.floor((remaining % 3600) / 60);
      this._countdown = h > 0 ? `${h}h ${m}m` : `${m}m`;
    };

    update();
    this._countdownTimer = setInterval(update, 30_000);
  }

  private _getEffectiveOverride() {
    if (this.overrideInfo?.active) return this.overrideInfo;
    return null;
  }

  private _renderTargetSection(live: NonNullable<RoomConfig["live"]>) {
    const targetTemp = live.target_temp;
    const l = this.hass?.language ?? "en";
    const ov = this._getEffectiveOverride();

    if (ov) {
      const icon = ov.type === "boost" ? "mdi:fire" : ov.type === "eco" ? "mdi:leaf" : "mdi:thermometer";
      const label = ov.type === "boost" ? localize("override.comfort", l) : ov.type === "eco" ? localize("override.eco", l) : localize("override.custom", l);
      const colorClass = `override-${ov.type}`;
      const displayTemp = ov.temp ?? targetTemp;

      return html`
        <div class="hero-target">
          <div class="hero-target-label ${colorClass}">
            <ha-icon icon=${icon}></ha-icon>
            ${label} ${localize("hero.override", l)}
          </div>
          <div class="hero-target-value">
            ${displayTemp !== null ? html`${formatTemp(displayTemp, this.hass)}${tempUnit(this.hass)}` : "--"}
          </div>
          ${this._countdown
            ? html`<div class="hero-target-countdown">${localize("hero.remaining", l, { time: this._countdown })}</div>`
            : nothing}
        </div>
      `;
    }

    if (targetTemp !== null || (live.heat_target != null && live.cool_target != null)) {
      const climateMode = this.config?.climate_mode ?? "auto";
      const showRange = climateMode === "auto"
        && live.heat_target != null
        && live.cool_target != null
        && live.heat_target !== live.cool_target;

      const display = showRange
        ? html`${formatTemp(live.heat_target!, this.hass)} – ${formatTemp(live.cool_target!, this.hass)}${tempUnit(this.hass)}`
        : html`${formatTemp((targetTemp ?? live.heat_target)!, this.hass)}${tempUnit(this.hass)}`;

      return html`
        <div class="hero-target">
          <div class="hero-target-label">${localize("hero.target", l)}</div>
          <div class="hero-target-value">${display}</div>
        </div>
      `;
    }

    return nothing;
  }

  private _onEditName(): void {
    this._nameInput = this.config?.display_name || "";
    this._editingName = true;
    this.updateComplete.then(() => {
      const input = this.renderRoot.querySelector<HTMLInputElement>(".name-input");
      input?.focus();
      input?.select();
    });
  }

  private _onNameInput(e: Event): void {
    this._nameInput = (e.target as HTMLInputElement).value;
  }

  private _onNameKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter") this._onNameDone();
    else if (e.key === "Escape") this._editingName = false;
  }

  private _onNameDone(): void {
    const value = this._nameInput.trim();
    this.dispatchEvent(
      new CustomEvent("display-name-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
    this._editingName = false;
  }

  private _onNameClear(): void {
    this.dispatchEvent(
      new CustomEvent("display-name-changed", {
        detail: { value: "" },
        bubbles: true,
        composed: true,
      })
    );
    this._editingName = false;
    this._nameInput = "";
  }

  render() {
    const live = this.config?.live;
    const mode = live?.mode;
    const accentClass = live
      ? mode === "heating"
        ? "hero-accent-heating"
        : mode === "cooling"
          ? "hero-accent-cooling"
          : "hero-accent-idle"
      : "hero-accent-none";

    return html`
      <ha-card>
        <div class="hero-accent ${accentClass}"></div>
        <div class="hero-header">
          ${this._editingName
            ? html`
                <div class="name-edit-row">
                  <input
                    class="name-input"
                    type="text"
                    .value=${this._nameInput}
                    placeholder=${localize("room.alias.placeholder", this.hass?.language ?? "en")}
                    @input=${this._onNameInput}
                    @keydown=${this._onNameKeydown}
                  />
                  <ha-icon-button
                    class="name-done-btn"
                    .path=${CHECK_PATH}
                    @click=${this._onNameDone}
                  ></ha-icon-button>
                </div>
                ${this.config?.display_name
                  ? html`<button class="name-clear-btn" @click=${this._onNameClear}>
                      ${localize("room.alias.clear", this.hass?.language ?? "en")}
                    </button>`
                  : nothing}
              `
            : html`
                <div class="name-row">
                  <h2 class="area-name">${this.config?.display_name || this.area.name}</h2>
                  <ha-icon-button
                    class="name-edit-btn"
                    .path=${PENCIL_PATH}
                    @click=${this._onEditName}
                  ></ha-icon-button>
                </div>
              `}
          ${live
            ? html`
                <span class="mode-pill ${getModeClass(live.mode)}">
                  <span class="mode-dot"></span>
                  ${formatMode(live.mode, this.hass?.language ?? "en")}${
                    live.heating_power > 0 && live.heating_power < 100
                      ? html` ${live.heating_power}%`
                      : nothing
                  }
                </span>
              `
            : nothing}
        </div>
        ${live
          ? html`
              ${live.window_open
                ? html`<div class="hero-window-open">
                    <ha-icon icon="mdi:window-open-variant"></ha-icon>
                    ${localize("hero.window_open", this.hass?.language ?? "en")}
                  </div>`
                : nothing}
              <div class="hero-temps">
                ${live.current_temp !== null
                  ? html`
                      <span class="hero-current">${formatTemp(live.current_temp, this.hass)}</span>
                      <span class="hero-unit">${tempUnit(this.hass)}</span>
                    `
                  : html`<span class="hero-current" style="opacity: 0.3">--</span>`}
                ${this._renderTargetSection(live)}
              </div>
              ${live.current_humidity !== null
                ? html`<div class="hero-metric">
                    <ha-icon icon="mdi:water-percent"></ha-icon>
                    ${localize("hero.humidity", this.hass?.language ?? "en", { value: live.current_humidity.toFixed(0) })}
                  </div>`
                : nothing}
              ${live.trv_setpoint != null
                ? html`<div class="hero-metric">
                    <ha-icon icon="mdi:radiator"></ha-icon>
                    ${localize("hero.trv_setpoint", this.hass?.language ?? "en", { value: formatTemp(live.trv_setpoint, this.hass), unit: tempUnit(this.hass) })}
                  </div>`
                : nothing}
              ${live.mold_surface_rh != null
                ? html`<div class="hero-metric ${live.mold_risk_level === "critical" ? "critical" : live.mold_risk_level === "warning" ? "warning" : ""}">
                    <ha-icon icon="mdi:water-alert"></ha-icon>
                    ${localize("room.mold_surface_rh", this.hass?.language ?? "en", { value: String(live.mold_surface_rh.toFixed(0)) })}
                  </div>`
                : nothing}
              ${live.mold_prevention_active
                ? html`<div class="hero-metric info">
                    <ha-icon icon="mdi:shield-check"></ha-icon>
                    ${localize("card.mold_prevention", this.hass?.language ?? "en", { delta: toDisplayDelta(live.mold_prevention_delta, this.hass).toFixed(0), unit: tempUnit(this.hass) })}
                  </div>`
                : nothing}
              ${!this.climateControlActive
                ? html`<div class="uncontrolled-hint">${localize("card.not_controlled", this.hass?.language ?? "en")}</div>`
                : nothing}
            `
          : this.config
            ? html`<div class="hero-no-data">${localize("hero.waiting", this.hass?.language ?? "en")}</div>`
            : html`<div class="hero-no-data">${localize("hero.not_configured", this.hass?.language ?? "en")}</div>`}
      </ha-card>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-hero-status": RsHeroStatus;
  }
}

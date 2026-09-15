import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, ClimateMode, OverrideType } from "../types";
import { localize } from "../utils/localize";
import { inputStyles } from "../styles/input-styles";
import { tempUnit, toDisplay, toCelsius, tempStep, tempRange } from "../utils/temperature";

@customElement("rs-override-section")
export class RsOverrideSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: RoomConfig;
  @property() public climateMode: ClimateMode = "auto";
  @property({ type: Number }) public comfortHeat = 21.0;
  @property({ type: Number }) public comfortCool = 24.0;
  @property({ type: Number }) public ecoHeat = 17.0;
  @property({ type: Number }) public ecoCool = 27.0;
  @property() public language = "en";

  @state() private _overridePending: OverrideType | null = null;
  @state() private _overrideCustomHeat = 21;
  @state() private _overrideCustomCool = 24;
  @state() private _overrideError = "";
  @state() private _optimisticOverride: {
    type: OverrideType;
    heat: number | null;
    cool: number | null;
    until: number | null;
  } | null = null;
  @state() private _optimisticClear = false;

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }

      .override-divider {
        border: none;
        border-top: 1px solid var(--divider-color, #e0e0e0);
        margin: 16px 0 12px;
      }

      .override-label {
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
        margin-bottom: 10px;
      }

      .override-presets {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }

      .override-preset {
        cursor: pointer;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 13px;
        background: transparent;
        color: var(--primary-text-color);
        display: flex;
        align-items: center;
        gap: 6px;
        transition:
          background 0.15s,
          border-color 0.15s;
      }

      .override-preset:hover {
        background: rgba(0, 0, 0, 0.04);
      }

      .override-preset.pending {
        border-color: var(--primary-color);
        background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
      }

      .override-preset.active.boost {
        border-color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.15);
        color: var(--warning-color, #ff9800);
      }

      .override-preset.active.eco {
        border-color: #4caf50;
        background: rgba(76, 175, 80, 0.15);
        color: #4caf50;
      }

      .override-preset.active.custom {
        border-color: #2196f3;
        background: rgba(33, 150, 243, 0.15);
        color: #2196f3;
      }

      .override-preset:disabled {
        opacity: 0.35;
        cursor: default;
      }

      .override-preset:disabled:hover {
        background: transparent;
      }

      .override-preset ha-icon {
        --mdc-icon-size: 16px;
      }

      .override-target {
        display: block;
        width: 160px;
        margin-top: 12px;
      }

      .override-duration {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 12px;
        align-items: center;
      }

      .override-duration-label {
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .override-dur-chips {
        display: flex;
        gap: 6px;
      }

      .override-dur-chip {
        cursor: pointer;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 6px 14px;
        font-size: 13px;
        font-weight: 500;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        transition:
          border-color 0.15s ease,
          background 0.15s ease;
      }

      .override-dur-chip:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: rgba(3, 169, 244, 0.4);
      }

      .override-dur-chip:disabled {
        opacity: 0.5;
        pointer-events: none;
      }

      .override-error {
        color: var(--error-color, #d32f2f);
        font-size: 12px;
        margin-top: 6px;
      }
    `,
  ];

  updated(changedProps: Map<string, unknown>) {
    // Clear optimistic override state once server data catches up
    if (changedProps.has("config") && this.config?.live) {
      const live = this.config.live;
      if (this._optimisticOverride && live.override_active) {
        this._optimisticOverride = null;
      }
      if (this._optimisticClear && !live.override_active) {
        this._optimisticClear = false;
      }
    }
  }

  /** Compute effective override state from optimistic + server data. */
  getEffectiveOverride(): {
    active: boolean;
    type: OverrideType | null;
    heat: number | null;
    cool: number | null;
    until: number | null;
  } {
    if (this._optimisticClear) {
      return { active: false, type: null, heat: null, cool: null, until: null };
    }
    if (this._optimisticOverride) {
      return {
        active: true,
        type: this._optimisticOverride.type,
        heat: this._optimisticOverride.heat,
        cool: this._optimisticOverride.cool,
        until: this._optimisticOverride.until,
      };
    }
    const live = this.config?.live;
    if (live?.override_active && live.override_type) {
      return {
        active: true,
        type: live.override_type,
        heat: live.override_heat,
        cool: live.override_cool,
        until: live.override_until,
      };
    }
    return { active: false, type: null, heat: null, cool: null, until: null };
  }

  render() {
    const ov = this.getEffectiveOverride();

    return html`
      <hr class="override-divider" />
      <div class="override-label">${localize("override.label", this.language)}</div>
      ${this._renderOverrideButtons(ov)}
      ${
        this._overrideError
          ? html`<div class="override-error">${this._overrideError}</div>`
          : nothing
      }
    `;
  }

  private _renderOverrideButtons(ov: ReturnType<typeof this.getEffectiveOverride>) {
    const activeType = ov.active ? ov.type : null;
    const showDuration = !activeType && this._overridePending;

    return html`
      <div class="override-presets">
        ${(["boost", "eco", "custom"] as OverrideType[]).map((t) => {
          const isActive = activeType === t;
          const isDisabled = activeType !== null && !isActive;
          const isPending = !activeType && this._overridePending === t;

          return html`
            <button
              class="override-preset ${t} ${isActive ? "active" : ""} ${isPending ? "pending" : ""}"
              ?disabled=${isDisabled}
              @click=${() => (isActive ? this._onClearOverride() : this._onOverridePreset(t))}
            >
              <ha-icon
                icon=${t === "boost" ? "mdi:fire" : t === "eco" ? "mdi:leaf" : "mdi:thermometer"}
              ></ha-icon>
              ${
                t === "boost"
                  ? localize("override.comfort", this.language)
                  : t === "eco"
                    ? localize("override.eco", this.language)
                    : localize("override.custom", this.language)
              }
            </button>
          `;
        })}
      </div>
      ${
        showDuration
          ? html`
              ${this._overridePending === "custom" ? this._renderCustomInputs() : nothing}
              <div class="override-duration">
                <span class="override-duration-label"
                  >${localize("override.activate_for", this.language)}</span
                >
                <div class="override-dur-chips">
                  ${[
                    { label: "1h", hours: 1 },
                    { label: "2h", hours: 2 },
                    { label: "4h", hours: 4 },
                  ].map(
                    (opt) => html`
                      <button
                        class="override-dur-chip"
                        @click=${() => this._onOverrideActivate(opt.hours)}
                      >
                        ${opt.label}
                      </button>
                    `,
                  )}
                </div>
              </div>
            `
          : nothing
      }
    `;
  }

  private _renderCustomInputs() {
    const range = tempRange(5, 35, this.hass);
    const heatField = html`
      <ha-textfield
        class="override-target"
        type="number"
        .label=${localize(
          this.climateMode === "auto" ? "override.heat_to" : "override.target",
          this.language,
        )}
        .suffix=${tempUnit(this.hass)}
        min=${range.min}
        max=${range.max}
        step=${tempStep(this.hass)}
        .value=${String(toDisplay(this._overrideCustomHeat, this.hass))}
        @input=${this._onCustomHeatInput}
      ></ha-textfield>
    `;
    const coolField = html`
      <ha-textfield
        class="override-target"
        type="number"
        .label=${localize(
          this.climateMode === "auto" ? "override.cool_above" : "override.target",
          this.language,
        )}
        .suffix=${tempUnit(this.hass)}
        min=${range.min}
        max=${range.max}
        step=${tempStep(this.hass)}
        .value=${String(toDisplay(this._overrideCustomCool, this.hass))}
        @input=${this._onCustomCoolInput}
      ></ha-textfield>
    `;
    if (this.climateMode === "heat_only") return heatField;
    if (this.climateMode === "cool_only") return coolField;
    return html`${heatField} ${coolField}`;
  }

  private _onOverridePreset(type: OverrideType): void {
    if (this._overridePending === type) {
      this._overridePending = null;
    } else {
      this._overridePending = type;
      if (type === "custom") {
        this._overrideCustomHeat = this.comfortHeat;
        this._overrideCustomCool = this.comfortCool;
      }
    }
    this._overrideError = "";
  }

  private _onCustomHeatInput(e: Event): void {
    this._overrideCustomHeat = toCelsius(
      Number((e.target as HTMLInputElement).value) || toDisplay(21, this.hass),
      this.hass,
    );
  }

  private _onCustomCoolInput(e: Event): void {
    this._overrideCustomCool = toCelsius(
      Number((e.target as HTMLInputElement).value) || toDisplay(24, this.hass),
      this.hass,
    );
  }

  private async _onOverrideActivate(hours: number): Promise<void> {
    if (!this._overridePending || !this.config) return;

    const pendingType = this._overridePending;
    let heat: number | null;
    let cool: number | null;
    if (pendingType === "boost") {
      heat = this.comfortHeat;
      cool = this.comfortCool;
    } else if (pendingType === "eco") {
      heat = this.ecoHeat;
      cool = this.ecoCool;
    } else {
      heat = this._overrideCustomHeat;
      cool = this._overrideCustomCool;
    }
    if (this.climateMode === "heat_only") cool = null;
    if (this.climateMode === "cool_only") heat = null;

    if (heat != null && cool != null && cool < heat) {
      this._overrideError = localize("override.invalid_band", this.language);
      return;
    }

    this._optimisticOverride = {
      type: pendingType,
      heat,
      cool,
      until: Date.now() / 1000 + hours * 3600,
    };
    this._optimisticClear = false;
    this._overridePending = null;
    this._overrideError = "";

    const msg: Record<string, unknown> = {
      type: "roommind/override/set",
      area_id: this.config.area_id,
      override_type: pendingType,
      duration: hours,
    };
    if (pendingType === "custom") {
      if (this.climateMode !== "cool_only") msg.heat = this._overrideCustomHeat;
      if (this.climateMode !== "heat_only") msg.cool = this._overrideCustomCool;
    }

    try {
      await this.hass.callWS(msg);
      this._fireRoomUpdated();
    } catch (err) {
      this._optimisticOverride = null;
      this._overrideError =
        err instanceof Error ? err.message : localize("override.error_set", this.language);
      // eslint-disable-next-line no-console
      console.error("Override set failed:", err);
    }
  }

  private async _onClearOverride(): Promise<void> {
    if (!this.config) return;

    this._optimisticClear = true;
    this._optimisticOverride = null;
    this._overrideError = "";

    try {
      await this.hass.callWS({
        type: "roommind/override/clear",
        area_id: this.config.area_id,
      });
      this._fireRoomUpdated();
    } catch (err) {
      this._optimisticClear = false;
      this._overrideError =
        err instanceof Error ? err.message : localize("override.error_clear", this.language);
      // eslint-disable-next-line no-console
      console.error("Override clear failed:", err);
    }
  }

  private _fireRoomUpdated(): void {
    this.dispatchEvent(new CustomEvent("room-updated", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-override-section": RsOverrideSection;
  }
}

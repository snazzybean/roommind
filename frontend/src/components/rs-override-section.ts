import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, ClimateMode, OverrideType } from "../types";
import { localize } from "../utils/localize";
import { errorText } from "../utils/errors";
import { inputStyles } from "../styles/input-styles";
import { tokens } from "../styles/tokens";
import { tempUnit, toDisplay, toCelsius, tempStep, tempRange } from "../utils/temperature";
import {
  NO_OVERRIDE,
  OVERRIDE_DURATIONS_H,
  OVERRIDE_PERMANENT_H,
  QUICK_OVERRIDE_FALLBACK_H,
  isInvalidBand,
  liveOverride,
  overrideBand,
  overrideSetMessage,
  type EffectiveOverride,
} from "../utils/override";
import { formatClock, scheduleNextChange } from "../utils/room-state";
import { formatHours } from "../utils/format";
import type { RsSegmentOption } from "./shared/rs-segmented";
import "./shared/rs-segmented";

type Choice = "schedule" | OverrideType;
const UNTIL_CHANGE = "next";
const PERMANENT = "perm";
/** How long an optimistic state waits for the poll to confirm it. */
const OPTIMISTIC_TIMEOUT_MS = 15000;

/**
 * Temporary override of a room: schedule (no override), comfort, eco or a custom band, then
 * how long. Picking a type only arms it; the duration sends it. Shows the user's choice at
 * once (optimistic) and fires `override-state` with the effective override whenever that
 * changes, so the hero can show it before the poll confirms.
 */
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
  @state() private _optimisticOverride: Omit<EffectiveOverride, "active"> | null = null;
  @state() private _optimisticClear = false;
  private _optimisticSince = 0;
  private _lastFired = "";

  static styles = [
    tokens,
    inputStyles,
    css`
      :host {
        display: block;
      }

      .qlabel {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        margin: var(--rs-space-4) 0 6px;
      }

      .qlabel:first-child {
        margin-top: 0;
      }

      .custom {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        margin-top: var(--rs-space-3);
      }

      .custom ha-textfield {
        flex: 1 1 140px;
        min-width: 0;
        max-width: 200px;
      }

      .error {
        color: var(--rs-err);
        font-size: var(--rs-font-sm);
        margin-top: var(--rs-space-2);
      }
    `,
  ];

  updated(changedProps: Map<string, unknown>) {
    // Clear optimistic state once server data catches up (or never will).
    if (changedProps.has("config") && this.config?.live) {
      const live = this.config.live;
      const expired = Date.now() - this._optimisticSince > OPTIMISTIC_TIMEOUT_MS;
      if (
        this._optimisticOverride &&
        ((live.override_active && live.override_type === this._optimisticOverride.type) || expired)
      ) {
        this._optimisticOverride = null;
      }
      if (this._optimisticClear && (!live.override_active || expired)) {
        this._optimisticClear = false;
      }
    }
    const effective = this.getEffectiveOverride();
    const key = JSON.stringify(effective);
    if (key !== this._lastFired) {
      this._lastFired = key;
      this.dispatchEvent(
        new CustomEvent<EffectiveOverride>("override-state", {
          detail: effective,
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  /** Effective override state: optimistic clear > optimistic set > server data. */
  getEffectiveOverride(): EffectiveOverride {
    if (this._optimisticClear) return NO_OVERRIDE;
    if (this._optimisticOverride) return { active: true, ...this._optimisticOverride };
    return liveOverride(this.config?.live);
  }

  render() {
    const l = this.language;
    const ov = this.getEffectiveOverride();
    const value: Choice = this._overridePending ?? (ov.active && ov.type ? ov.type : "schedule");
    const hasSchedule = (this.config?.schedules ?? []).some((s) => !!s.entity_id);
    const options: RsSegmentOption[] = [
      {
        value: "schedule",
        label: localize(hasSchedule ? "card.quick.schedule" : "card.quick.normal", l),
        icon: hasSchedule ? "mdi:calendar-clock" : "mdi:home-thermometer-outline",
      },
      { value: "boost", label: localize("override.comfort", l), icon: "mdi:sofa" },
      { value: "eco", label: localize("override.eco", l), icon: "mdi:leaf" },
      { value: "custom", label: localize("override.custom", l), icon: "mdi:thermometer" },
    ];

    return html`
      <div class="qlabel">${localize("detail.override.label", l)}</div>
      <rs-segmented
        .label=${localize("detail.override.label", l)}
        .options=${options}
        .value=${value}
        @value-changed=${this._onChoice}
      ></rs-segmented>
      ${this._overridePending ? this._renderPending(this._overridePending) : nothing}
      <div class="error" role="alert">${this._overrideError}</div>
    `;
  }

  private _renderPending(type: OverrideType) {
    const l = this.language;
    const options: RsSegmentOption[] = OVERRIDE_DURATIONS_H.map((h) => ({
      value: String(h),
      label: formatHours(h, l),
    }));
    const next = this._nextChange();
    if (next != null) {
      options.push({
        value: UNTIL_CHANGE,
        label: localize("detail.override.until_change", l, { time: formatClock(next, l) }),
      });
    }
    options.push({ value: PERMANENT, label: localize("hero.permanent", l) });
    return html`
      ${type === "custom" ? this._renderCustomInputs() : nothing}
      <div class="qlabel">${localize("detail.override.duration", l)}</div>
      <rs-segmented
        size="sm"
        wrap
        .label=${localize("detail.override.duration", l)}
        .options=${options}
        .value=${null}
        @value-changed=${this._onDuration}
      ></rs-segmented>
    `;
  }

  private _renderCustomInputs() {
    const range = tempRange(5, 35, this.hass);
    const field = (
      labelKey: "override.heat_to" | "override.cool_above" | "override.target",
      heat: boolean,
    ) => html`
      <ha-textfield
        type="number"
        .label=${localize(labelKey, this.language)}
        .suffix=${tempUnit(this.hass)}
        min=${range.min}
        max=${range.max}
        step=${tempStep(this.hass)}
        .value=${String(toDisplay(heat ? this._overrideCustomHeat : this._overrideCustomCool, this.hass))}
        @input=${heat ? this._onCustomHeatInput : this._onCustomCoolInput}
      ></ha-textfield>
    `;
    if (this.climateMode === "heat_only")
      return html`<div class="custom">${field("override.target", true)}</div>`;
    if (this.climateMode === "cool_only")
      return html`<div class="custom">${field("override.target", false)}</div>`;
    return html`<div class="custom">
      ${field("override.heat_to", true)} ${field("override.cool_above", false)}
    </div>`;
  }

  /** Next change of the active schedule, if the room has one and it lies ahead. */
  private _nextChange(): number | null {
    const next = scheduleNextChange(this.config, this.hass?.states);
    return next != null && next > Date.now() / 1000 ? next : null;
  }

  private _onChoice(e: CustomEvent<{ value: Choice }>): void {
    e.stopPropagation();
    const choice = e.detail.value;
    this._overrideError = "";
    if (choice === "schedule") {
      this._overridePending = null;
      if (this.getEffectiveOverride().active) this._onClearOverride();
      return;
    }
    this._overridePending = choice;
    if (choice === "custom") {
      const ov = this.getEffectiveOverride();
      this._overrideCustomHeat =
        ov.type === "custom" && ov.heat != null ? ov.heat : this.comfortHeat;
      this._overrideCustomCool =
        ov.type === "custom" && ov.cool != null ? ov.cool : this.comfortCool;
    }
  }

  private _onDuration(e: CustomEvent<{ value: string }>): void {
    e.stopPropagation();
    const v = e.detail.value;
    if (v === UNTIL_CHANGE) this._onOverrideActivate(QUICK_OVERRIDE_FALLBACK_H, true);
    else if (v === PERMANENT) this._onOverrideActivate(OVERRIDE_PERMANENT_H);
    else this._onOverrideActivate(Number(v));
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

  private async _onOverrideActivate(hours: number, untilScheduleChange = false): Promise<void> {
    if (!this._overridePending || !this.config) return;

    const pendingType = this._overridePending;
    const custom = { heat: this._overrideCustomHeat, cool: this._overrideCustomCool };
    const { heat, cool } = overrideBand(
      pendingType,
      this.climateMode,
      {
        comfortHeat: this.comfortHeat,
        comfortCool: this.comfortCool,
        ecoHeat: this.ecoHeat,
        ecoCool: this.ecoCool,
      },
      custom,
    );
    if (isInvalidBand(heat, cool)) {
      this._overrideError = localize("override.invalid_band", this.language);
      return;
    }
    const nowS = Date.now() / 1000;
    const next = untilScheduleChange ? this._nextChange() : null;
    const until = next ?? (hours > 0 ? nowS + hours * 3600 : null);
    const previous = this._optimisticOverride;
    this._optimisticOverride = { type: pendingType, heat, cool, until };
    this._optimisticSince = Date.now();
    this._optimisticClear = false;
    this._overridePending = null;
    this._overrideError = "";
    const msg = overrideSetMessage(
      this.config.area_id,
      pendingType,
      hours,
      this.climateMode,
      custom,
      untilScheduleChange,
    );
    try {
      await this.hass.callWS(msg);
      this._fireRoomUpdated();
    } catch (err) {
      this._optimisticOverride = previous;
      this._overrideError = errorText(
        err,
        localize("override.error_set", this.language),
        this.language,
      );
      // eslint-disable-next-line no-console
      console.error("Override set failed:", err);
    }
  }

  private async _onClearOverride(): Promise<void> {
    if (!this.config) return;

    this._optimisticClear = true;
    this._optimisticSince = Date.now();
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
      this._overrideError = errorText(
        err,
        localize("override.error_clear", this.language),
        this.language,
      );
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

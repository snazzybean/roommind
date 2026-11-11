import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ScheduleEntry, ClimateMode, ScheduleTempWarning } from "../types";
import { localize } from "../utils/localize";
import {
  formatTempLocale,
  tempUnit,
  toDisplay,
  toDisplayDelta,
  toCelsius,
  isPlausibleTargetTemp,
  MIN_TARGET_TEMP_C,
  MAX_TARGET_TEMP_C,
  tempStep,
  tempRange,
} from "../utils/temperature";
import { formatNumber } from "../utils/format";
import { RsScheduleBase } from "./shared/rs-schedule-base";
import { inputStyles } from "../styles/input-styles";
import "./shared/rs-toggle-row";
import "./shared/rs-chip-group";
import "./shared/rs-list-row";

/** Mirrors _WEEKDAYS in the backend's schedule_utils.py. */
const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

// Matches MAX_PRICE_SHIFT_K in const.py
const PRICE_SHIFT_STEPS = [0, 0.5, 1, 1.5, 2];

@customElement("rs-schedule-settings")
export class RsScheduleSettings extends RsScheduleBase {
  @property({ attribute: false }) public schedules: ScheduleEntry[] = [];
  /** Alias: parent passes .scheduleSelectorEntity, base uses selectorEntity. */
  @property({ type: String }) public set scheduleSelectorEntity(v: string) {
    this.selectorEntity = v;
  }
  public get scheduleSelectorEntity(): string {
    return this.selectorEntity;
  }
  /** Alias: parent passes .activeScheduleIndex, base uses activeIndex. */
  @property({ type: Number }) public set activeScheduleIndex(v: number) {
    this.activeIndex = v;
  }
  public get activeScheduleIndex(): number {
    return this.activeIndex;
  }
  @property({ type: Number }) public comfortHeat = 21.0;
  @property({ type: Number }) public comfortCool = 24.0;
  @property({ type: Number }) public ecoHeat = 17.0;
  @property({ type: Number }) public ecoCool = 27.0;
  @property({ type: String }) public climateMode: ClimateMode = "auto";
  @property({ attribute: false }) public scheduleTempWarnings: ScheduleTempWarning[] = [];
  @property({ type: Boolean }) public preheatEnabled = true;
  @property({ type: Boolean }) public showPreheat = false;
  @property({ type: Boolean }) public followDeviceSetpoint = false;
  /** K the schedule target may move with the electricity price (0 = off). */
  @property({ type: Number }) public priceShift = 0;
  /** A price source is set in the settings; without one the option is hidden. */
  @property({ type: Boolean }) public priceConfigured = false;

  static styles = [
    RsScheduleBase.sharedStyles,
    inputStyles,
    css`
      .fallback-hint {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 4px;
        font-style: italic;
      }

      .temp-inputs {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-top: 16px;
      }

      .temp-input-group {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      ha-textfield {
        flex: 1;
      }

      .preheat-toggle,
      .follow-device-toggle,
      .price-shift {
        margin-top: 16px;
      }

      .price-shift-label {
        font-size: 14px;
        margin-bottom: 4px;
      }

      .price-shift-hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 8px;
      }

      .inline-warning.in-list {
        margin: 0 16px 8px;
      }

      .temp-grid-auto {
        display: grid;
        grid-template-columns: auto 1fr 1fr;
        gap: 8px 12px;
        align-items: center;
        margin-top: 16px;
      }
      .temp-grid-header {
        font-size: 12px;
        font-weight: 600;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.3px;
        text-align: center;
      }
      .temp-grid-row-label {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
        white-space: nowrap;
      }

      @media (max-width: 600px) {
        .temp-grid-auto {
          grid-template-columns: 1fr 1fr;
        }
        .temp-grid-row-label {
          grid-column: 1 / -1;
          margin-top: 8px;
        }
        .temp-grid-header {
          display: none;
        }
      }
    `,
  ];

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  // ─── View mode ─────────────────────────────────────────────────

  private _renderViewMode() {
    const l = this.hass.language;
    const hasMultiple = this.schedules.length >= 2;
    const unit = tempUnit(this.hass);
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const band = (heat: number, cool: number) =>
      this.climateMode === "auto"
        ? `${fmt(heat)}–${fmt(cool)} ${unit}`
        : `${fmt(this.climateMode === "cool_only" ? cool : heat)} ${unit}`;

    return html`
      ${
        this.schedules.length > 0
          ? this.schedules.map((schedule, index) => {
              const state = this._getScheduleState(index, this.schedules.length);
              const name = this._getFriendlyName(schedule.entity_id);
              return html`
                <rs-list-row
                  clickable
                  chevron
                  icon="mdi:calendar-clock"
                  icon-label=${localize("detail.more_info", l)}
                  .iconColor=${state === "active" ? "var(--primary-color)" : ""}
                  .heading=${hasMultiple ? `${index + 1} · ${name}` : name}
                  .secondary=${this._getStatusText(index, state)}
                  @row-click=${this._onEditClick}
                  @icon-click=${() => this._openEntityInfo(schedule.entity_id)}
                ></rs-list-row>
                ${this._renderRejectedTempWarning(state, true)}
              `;
            })
          : html`<rs-list-row
              clickable
              plain-icon
              variant="primary"
              icon="mdi:plus"
              .heading=${localize("detail.schedule.add", l)}
              .secondary=${localize("schedule.no_schedules", l)}
              @row-click=${this._onEditClick}
            ></rs-list-row>`
      }
      ${
        this.scheduleSelectorEntity
          ? html`<rs-list-row
              clickable
              chevron
              icon="mdi:swap-horizontal-circle-outline"
              icon-label=${localize("detail.more_info", l)}
              .heading=${this._getFriendlyName(this.scheduleSelectorEntity)}
              .secondary=${localize("schedule.view_selector_prefix", l).replace(/:\s*$/, "")}
              .value=${this._getSelectorValueText(l)}
              @row-click=${this._onEditClick}
              @icon-click=${() => this._openEntityInfo(this.scheduleSelectorEntity)}
            ></rs-list-row>`
          : nothing
      }
      <rs-list-row
        clickable
        chevron
        icon="mdi:sofa"
        .heading=${localize("override.comfort", l)}
        .secondary=${localize("detail.schedule.comfort_sub", l)}
        .value=${band(this.comfortHeat, this.comfortCool)}
        @row-click=${this._onEditClick}
      ></rs-list-row>
      <rs-list-row
        clickable
        chevron
        icon="mdi:leaf"
        .heading=${localize("override.eco", l)}
        .secondary=${localize("detail.schedule.eco_sub", l)}
        .value=${band(this.ecoHeat, this.ecoCool)}
        @row-click=${this._onEditClick}
      ></rs-list-row>
      ${
        this.showPreheat
          ? html`<rs-list-row
              switch
              icon="mdi:clock-fast"
              .heading=${localize("schedule.preheat_label", l)}
              .secondary=${localize("detail.schedule.preheat_sub", l)}
              .checked=${this.preheatEnabled}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._fireValue("preheat-changed", e.detail)}
            ></rs-list-row>`
          : nothing
      }
      <rs-list-row
        switch
        icon="mdi:gesture-tap"
        .heading=${localize("schedule.follow_device_setpoint_label", l)}
        .secondary=${localize("detail.schedule.follow_sub", l)}
        .checked=${this.followDeviceSetpoint}
        @toggle-changed=${(e: CustomEvent<boolean>) =>
          this._fireValue("follow-device-setpoint-changed", e.detail)}
      ></rs-list-row>
      ${
        this.priceConfigured
          ? html`<rs-list-row
              clickable
              chevron
              icon="mdi:cash-clock"
              .heading=${localize("schedule.price_shift_label", l)}
              .secondary=${localize("detail.schedule.price_sub", l)}
              .value=${
                this.priceShift > 0
                  ? `±${this._shiftLabel(this.priceShift)}`
                  : localize("schedule.price_shift_off", l)
              }
              @row-click=${this._onEditClick}
            ></rs-list-row>`
          : nothing
      }
    `;
  }

  private _onEditClick(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }

  private _fireValue(name: string, value: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail: { value }, bubbles: true, composed: true }));
  }

  // ─── Edit mode ─────────────────────────────────────────────────

  private _renderEditMode() {
    const l = this.hass.language;
    const count = this.schedules.length;
    const usedIds = new Set(this.schedules.map((s) => s.entity_id));

    return html`
      ${this._renderScheduleList()}
      ${this._renderAddRow(
        localize("schedule.select_schedule", l),
        this._getAvailableEntities(usedIds),
        (eid) => this._addSchedule(eid),
        localize("schedule.create_helper_hint", l),
      )}
      ${this._renderSelectorSection(
        count,
        localize("schedule.selector_label", l),
        this.scheduleSelectorEntity ? this._getSelectorValueText(l) : "",
        localize("schedule.selector_warning", l),
        (value) => this._onSelectorEntityChange(value),
      )}
      ${this._renderTemperatureInputs(l)}
      ${
        this.showPreheat
          ? html`<rs-toggle-row
              class="preheat-toggle"
              .label=${localize("schedule.preheat_label", l)}
              .hint=${localize("schedule.preheat_hint", l)}
              .checked=${this.preheatEnabled}
              @toggle-changed=${this._onPreheatToggle}
            ></rs-toggle-row>`
          : nothing
      }
      <rs-toggle-row
        class="follow-device-toggle"
        .label=${localize("schedule.follow_device_setpoint_label", l)}
        .hint=${localize("schedule.follow_device_setpoint_hint", l)}
        .checked=${this.followDeviceSetpoint}
        @toggle-changed=${this._onFollowDeviceSetpointToggle}
      ></rs-toggle-row>
      ${this.priceConfigured ? this._renderPriceShift(l) : nothing}
    `;
  }

  private _renderPriceShift(l: string) {
    return html`<div class="price-shift">
      <div class="price-shift-label">${localize("schedule.price_shift_label", l)}</div>
      <div class="price-shift-hint">${localize("schedule.price_shift_hint", l)}</div>
      <rs-chip-group
        .chips=${PRICE_SHIFT_STEPS.map((k) => ({
          id: String(k),
          label: k === 0 ? localize("schedule.price_shift_off", l) : `±${this._shiftLabel(k)}`,
          active: Math.abs(this.priceShift - k) < 0.01,
        }))}
        @chip-clicked=${this._onPriceShiftChip}
      ></rs-chip-group>
    </div>`;
  }

  private _shiftLabel(k: number): string {
    return `${new Intl.NumberFormat(this.hass.language, { maximumFractionDigits: 1 }).format(
      toDisplayDelta(k, this.hass),
    )}\u00A0${tempUnit(this.hass)}`;
  }

  private _onPriceShiftChip(e: CustomEvent<string>) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("price-shift-changed", {
        detail: { value: Number(e.detail) },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onFollowDeviceSetpointToggle(e: CustomEvent<boolean>) {
    e.stopPropagation();
    this._fireValue("follow-device-setpoint-changed", e.detail);
  }

  private _onPreheatToggle(e: CustomEvent<boolean>) {
    e.stopPropagation();
    this._fireValue("preheat-changed", e.detail);
  }

  // ─── Schedule list ─────────────────────────────────────────────

  private _renderScheduleList() {
    const l = this.hass.language;
    const count = this.schedules.length;

    if (count === 0) {
      return html`<div class="no-schedules">${localize("schedule.no_schedules", l)}</div>`;
    }

    return html`
      <div class="schedule-list">
        ${this.schedules.map((schedule, index) => {
          const state = this._getScheduleState(index, count);
          return html`
            <div class="schedule-row ${state}">
              ${count >= 2 ? html`<span class="schedule-number">${index + 1}</span>` : nothing}
              <span class="schedule-status-dot"></span>
              <span class="schedule-name">${this._getFriendlyName(schedule.entity_id)}</span>
              <span class="schedule-status">${this._getStatusText(index, state)}</span>
              ${this._renderScheduleControls(
                index,
                count,
                (i, dir) => this._moveSchedule(i, dir),
                (i) => this._removeSchedule(i),
              )}
            </div>
            ${this._renderRejectedTempWarning(state)}
          `;
        })}
      </div>
    `;
  }

  /**
   * Warn about block temperatures the backend discarded (#395).
   *
   * Sourced from the backend's whole-week scan, so a typo in the 03:00 block is
   * visible at any time of day — not just while that block is running. The scan
   * covers the active schedule only, hence the warning hangs off that row.
   */
  private _renderRejectedTempWarning(state: "active" | "inactive" | "unreachable", inList = false) {
    if (state !== "active") return nothing;
    const warnings = this.scheduleTempWarnings ?? [];
    if (warnings.length === 0) return nothing;

    const range = tempRange(MIN_TARGET_TEMP_C, MAX_TARGET_TEMP_C, this.hass);
    return html`
      <div class="inline-warning ${inList ? "in-list" : ""}">
        <ha-icon icon="mdi:alert-outline"></ha-icon>
        ${localize("schedule.block_temp_rejected", this.hass.language, {
          values: warnings.map((w) => this._formatWarning(w)).join(", "),
          min: range.min,
          max: range.max,
          unit: tempUnit(this.hass),
        })}
      </div>
    `;
  }

  /** "110 (Mon 00:00)" — weekday localised via Intl, so no extra locale keys. */
  private _formatWarning(w: ScheduleTempWarning): string {
    const index = WEEKDAYS.indexOf(w.day);
    let when = w.from.slice(0, 5);
    if (index >= 0) {
      // 2024-01-01 was a Monday, so +index lands on the right weekday.
      const date = new Date(Date.UTC(2024, 0, 1 + index));
      const weekday = new Intl.DateTimeFormat(this.hass.language, {
        weekday: "short",
        timeZone: "UTC",
      }).format(date);
      when = `${weekday} ${when}`;
    }
    return `${w.value} (${when})`;
  }

  // ─── Temperature inputs ────────────────────────────────────────

  private _renderTemperatureInputs(l: string) {
    if (this.climateMode === "auto") {
      return html`
        <div class="temp-grid-auto">
          <div class="temp-grid-header"></div>
          <div class="temp-grid-header">${localize("schedule.column_comfort", l)}</div>
          <div class="temp-grid-header">${localize("schedule.column_eco", l)}</div>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:fire" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_heat", l)}
          </div>
          <ha-textfield
            type="number"
            .value=${String(toDisplay(this.comfortHeat, this.hass))}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${this._onComfortHeatChange}
          ></ha-textfield>
          <ha-textfield
            type="number"
            .value=${String(toDisplay(this.ecoHeat, this.hass))}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${this._onEcoHeatChange}
          ></ha-textfield>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:snowflake" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_cool", l)}
          </div>
          <ha-textfield
            type="number"
            .value=${String(toDisplay(this.comfortCool, this.hass))}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${this._onComfortCoolChange}
          ></ha-textfield>
          <ha-textfield
            type="number"
            .value=${String(toDisplay(this.ecoCool, this.hass))}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${this._onEcoCoolChange}
          ></ha-textfield>
        </div>
      `;
    }

    return html`
      <div class="temp-inputs">
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${localize("schedule.comfort_label", l)}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            .value=${String(
              toDisplay(
                this.climateMode === "cool_only" ? this.comfortCool : this.comfortHeat,
                this.hass,
              ),
            )}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${
              this.climateMode === "cool_only"
                ? this._onComfortCoolChange
                : this._onComfortHeatChange
            }
          ></ha-textfield>
        </div>
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${localize("schedule.eco_label", l)}
            suffix=${tempUnit(this.hass)}
            step=${tempStep(this.hass)}
            .value=${String(
              toDisplay(this.climateMode === "cool_only" ? this.ecoCool : this.ecoHeat, this.hass),
            )}
            min=${tempRange(5, 35, this.hass).min}
            max=${tempRange(5, 35, this.hass).max}
            @change=${
              this.climateMode === "cool_only" ? this._onEcoCoolChange : this._onEcoHeatChange
            }
          ></ha-textfield>
        </div>
      </div>
      <div class="fallback-hint">${localize("schedule.comfort_hint", l)}</div>
    `;
  }

  // ─── Selector value text ───────────────────────────────────────

  private _getSelectorValueText(l: string): string {
    const selectorState = this.hass?.states?.[this.scheduleSelectorEntity];
    if (!selectorState) return "";
    if (this.scheduleSelectorEntity.startsWith("input_boolean.")) {
      return localize("schedule.selector_value_boolean", l, {
        value: selectorState.state === "on" ? "On" : "Off",
      });
    }
    return localize("schedule.selector_value_number", l, {
      value: selectorState.state,
    });
  }

  // ─── Status text (temperature-specific) ────────────────────────

  /**
   * Read the active block's temperatures from the schedule entity's attributes.
   *
   * Implausible values are dropped by the backend (#395), so they must not be
   * shown as the active target here either. The *warning* about them comes from
   * `scheduleTempWarnings` instead — the backend scans the whole week, while
   * these attributes only ever describe the block running right now.
   */
  private _readBlockTemps(index: number): {
    blockTemp?: number;
    heatTemp?: number;
    coolTemp?: number;
  } {
    const entityState = this.hass?.states?.[this.schedules[index].entity_id];
    const attrs = entityState?.attributes ?? {};
    const usable = (v: unknown): number | undefined =>
      v != null && isPlausibleTargetTemp(v, this.hass) ? (v as number) : undefined;

    return {
      blockTemp: usable(attrs.temperature),
      heatTemp: usable(attrs.heat_temperature),
      coolTemp: usable(attrs.cool_temperature),
    };
  }

  private _getStatusText(index: number, state: "active" | "inactive" | "unreachable"): string {
    const l = this.hass.language;

    if (state === "unreachable") return localize("schedule.state_unreachable", l);
    if (state === "inactive") return localize("schedule.state_inactive", l);

    const schedule = this.schedules[index];
    const entityState = this.hass?.states?.[schedule.entity_id];
    if (!entityState) return localize("schedule.state_active", l);

    const isOn = entityState.state === "on";
    if (isOn) {
      const { blockTemp, heatTemp, coolTemp } = this._readBlockTemps(index);
      if (blockTemp != null) {
        return localize("schedule.from_schedule", l, {
          temp: formatNumber(Number(blockTemp), this.hass, 0, 1),
          unit: tempUnit(this.hass),
        });
      }
      if (heatTemp != null || coolTemp != null) {
        // heatTemp/coolTemp are entity attributes (already display units); the
        // comfort fallbacks are backend Celsius and need converting.
        return localize("schedule.from_schedule_split", l, {
          heat:
            heatTemp != null
              ? formatNumber(Number(heatTemp), this.hass, 0, 1)
              : formatTempLocale(this.comfortHeat, this.hass),
          cool:
            coolTemp != null
              ? formatNumber(Number(coolTemp), this.hass, 0, 1)
              : formatTempLocale(this.comfortCool, this.hass),
          unit: tempUnit(this.hass),
        });
      }
      return localize("schedule.fallback", l, {
        temp: formatTempLocale(
          this.climateMode === "cool_only" ? this.comfortCool : this.comfortHeat,
          this.hass,
        ),
        unit: tempUnit(this.hass),
      });
    }

    return localize("schedule.eco_detail", l, {
      temp: formatTempLocale(
        this.climateMode === "cool_only" ? this.ecoCool : this.ecoHeat,
        this.hass,
      ),
      unit: tempUnit(this.hass),
    });
  }

  // ─── Schedule management ───────────────────────────────────────

  private _addSchedule(entityId: string) {
    this._emitSchedules([...this.schedules, { entity_id: entityId }]);
  }

  private _removeSchedule(index: number) {
    this._emitSchedules(this.schedules.filter((_, i) => i !== index));
  }

  private _moveSchedule(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= this.schedules.length) return;
    const next = [...this.schedules];
    [next[index], next[target]] = [next[target], next[index]];
    this._emitSchedules(next);
  }

  private _emitSchedules(value: ScheduleEntry[]) {
    this.dispatchEvent(
      new CustomEvent("schedules-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onSelectorEntityChange(value: string) {
    this.dispatchEvent(
      new CustomEvent("schedule-selector-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ─── Temperature change handlers ──────────────────────────────

  private _onComfortHeatChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(21.0, this.hass), this.hass);
    this.dispatchEvent(
      new CustomEvent("comfort-heat-changed", {
        detail: { value: val },
        bubbles: true,
        composed: true,
      }),
    );
    if (this.comfortCool < val) {
      this.dispatchEvent(
        new CustomEvent("comfort-cool-changed", {
          detail: { value: val },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onComfortCoolChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(24.0, this.hass), this.hass);
    this.dispatchEvent(
      new CustomEvent("comfort-cool-changed", {
        detail: { value: val },
        bubbles: true,
        composed: true,
      }),
    );
    if (this.comfortHeat > val) {
      this.dispatchEvent(
        new CustomEvent("comfort-heat-changed", {
          detail: { value: val },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onEcoHeatChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(17.0, this.hass), this.hass);
    this.dispatchEvent(
      new CustomEvent("eco-heat-changed", {
        detail: { value: val },
        bubbles: true,
        composed: true,
      }),
    );
    if (this.ecoCool < val) {
      this.dispatchEvent(
        new CustomEvent("eco-cool-changed", {
          detail: { value: val },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onEcoCoolChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(27.0, this.hass), this.hass);
    this.dispatchEvent(
      new CustomEvent("eco-cool-changed", {
        detail: { value: val },
        bubbles: true,
        composed: true,
      }),
    );
    if (this.ecoHeat > val) {
      this.dispatchEvent(
        new CustomEvent("eco-heat-changed", {
          detail: { value: val },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-settings": RsScheduleSettings;
  }
}

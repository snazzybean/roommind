import { html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ScheduleEntry, ClimateMode, ScheduleTempWarning } from "../types";
import { localize } from "../utils/localize";
import {
  formatTempLocale,
  tempUnit,
  isPlausibleTargetTemp,
  MIN_TARGET_TEMP_C,
  MAX_TARGET_TEMP_C,
  tempRange,
} from "../utils/temperature";
import { formatNumber } from "../utils/format";
import { RsScheduleBase } from "./shared/rs-schedule-base";
import { inputStyles } from "../styles/input-styles";
import { priceShiftLabel } from "./room-detail/rs-price-shift";
import { isAdmin, isEditableSchedule } from "../utils/schedule-api";
import "./shared/rs-list-row";
import "./shared/rs-info-icon";
import "./schedule/rs-schedule-create";

/** Mirrors _WEEKDAYS in the backend's schedule_utils.py. */
const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

/** Which dialog a row of the card opens (`edit-click` detail `{ part }`). */
export type ScheduleCardPart = "schedule" | "temperatures" | "price";

/**
 * The room's "Schedule & temperatures" card. View mode: one row per schedule, comfort, eco,
 * pre-heat, device changes and price; each clickable row fires `edit-click` with the dialog it
 * belongs to. Edit mode is the content of the schedule dialog (assigned helpers, adding one,
 * selector); temperatures and price have their own dialog components.
 */
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
  /** What the room does while its schedule is off / everybody is away (global settings). */
  @property({ type: String }) public scheduleOffAction: "eco" | "off" = "eco";
  @property({ type: String }) public presenceAwayAction: "eco" | "off" = "eco";
  /** Presence detection applies to this room (on globally, persons to watch, not ignored). */
  @property({ type: Boolean }) public presenceActive = false;
  /** An empty room drops to eco (occupancy eco with sensors). */
  @property({ type: Boolean }) public occupancyEco = false;
  /** Default name of a schedule created from the dialog. */
  @property({ type: String }) public roomName = "";

  @state() private _creating = false;
  protected readonly _kind = "climate";

  static styles = [
    RsScheduleBase.sharedStyles,
    inputStyles,
    css`
      .inline-warning.in-list {
        margin: 0 16px 8px;
      }

      /* The edit button needs room: on phones it moves to a second line instead of the name. */
      .schedule-row {
        flex-wrap: wrap;
      }

      .schedule-row .schedule-name {
        flex: 1 1 140px;
      }

      .schedule-row ha-button {
        flex: none;
        margin-left: auto;
      }

      .create-row {
        margin: 0 -16px 8px;
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
        ? `${fmt(heat)}–${fmt(cool)}\u00a0${unit}`
        : `${fmt(this.climateMode === "cool_only" ? cool : heat)}\u00a0${unit}`;
    const open = (part: ScheduleCardPart) => (e: Event) => this._onEditClick(e, part);

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
                  .secondary=${[this._getStatusText(index, state), this._usage(schedule.entity_id)]
                    .filter(Boolean)
                    .join(" · ")}
                  @row-click=${open("schedule")}
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
              @row-click=${open("schedule")}
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
              .value=${this.selectorStateText()}
              @row-click=${open("schedule")}
              @icon-click=${() => this._openEntityInfo(this.scheduleSelectorEntity)}
            ></rs-list-row>`
          : nothing
      }
      <rs-list-row
        clickable
        chevron
        icon="mdi:sofa"
        .heading=${localize("override.comfort", l)}
        .secondary=${this._comfortSub()}
        .value=${band(this.comfortHeat, this.comfortCool)}
        @row-click=${open("temperatures")}
      ></rs-list-row>
      <rs-list-row
        clickable
        chevron
        icon="mdi:leaf"
        .heading=${localize("override.eco", l)}
        .secondary=${this._ecoSub()}
        .value=${band(this.ecoHeat, this.ecoCool)}
        @row-click=${open("temperatures")}
      ></rs-list-row>
      ${
        this.showPreheat
          ? html`<rs-list-row
              switch
              wrap
              icon="mdi:clock-fast"
              .heading=${localize("schedule.preheat_label", l)}
              .secondary=${localize("detail.schedule.preheat_sub", l)}
              .checked=${this.preheatEnabled}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._fireValue("preheat-changed", e.detail)}
            >
              <rs-info-icon slot="end" .text=${localize("schedule.preheat_hint", l)}></rs-info-icon>
            </rs-list-row>`
          : nothing
      }
      <rs-list-row
        switch
        wrap
        icon="mdi:gesture-tap"
        .heading=${localize("schedule.follow_device_setpoint_label", l)}
        .secondary=${localize(
          this.schedules.length
            ? "detail.schedule.follow_sub"
            : "detail.schedule.follow_sub_no_schedule",
          l,
        )}
        .checked=${this.followDeviceSetpoint}
        @toggle-changed=${(e: CustomEvent<boolean>) =>
          this._fireValue("follow-device-setpoint-changed", e.detail)}
      >
        <rs-info-icon
          slot="end"
          .text=${localize("schedule.follow_device_setpoint_hint", l)}
        ></rs-info-icon>
      </rs-list-row>
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
                  ? priceShiftLabel(this.priceShift, this.hass)
                  : localize("schedule.price_shift_off", l)
              }
              @row-click=${open("price")}
            ></rs-list-row>`
          : nothing
      }
    `;
  }

  /** When comfort applies in this room. */
  private _comfortSub(): string {
    const l = this.hass.language;
    if (this.schedules.length) return localize("detail.schedule.comfort_sub", l);
    return localize(
      this.presenceActive
        ? "detail.schedule.comfort_sub_home"
        : "detail.schedule.comfort_sub_always",
      l,
    );
  }

  /** When eco applies in this room: schedule off, nobody home, room empty, else only by choice. */
  private _ecoSub(): string {
    const l = this.hass.language;
    const when: string[] = [];
    if (this.schedules.length && this.scheduleOffAction === "eco") {
      when.push(localize("detail.schedule.when_schedule_off", l));
    }
    if (this.presenceActive && this.presenceAwayAction === "eco") {
      when.push(localize("detail.schedule.when_away", l));
    }
    if (this.occupancyEco) when.push(localize("detail.schedule.when_empty", l));
    if (!when.length) return localize("detail.schedule.eco_sub_manual", l);
    const list = new Intl.ListFormat(l, { type: "disjunction" }).format(when);
    return localize("detail.schedule.eco_sub", l, { when: list });
  }

  private _onEditClick(e: Event, part: ScheduleCardPart) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("edit-click", { detail: { part }, bubbles: true, composed: true }),
    );
  }

  private _fireValue(name: string, value: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail: { value }, bubbles: true, composed: true }));
  }

  // ─── Edit mode (schedule dialog) ───────────────────────────────

  private _renderEditMode() {
    const l = this.hass.language;
    return html`
      ${this._renderScheduleList()} ${this._renderAddSource()}
      ${this._renderSelectorSection(
        this.schedules.length,
        localize("schedule.selector_label", l),
        "",
        localize("schedule.selector_warning", l),
        (value) => this._onSelectorEntityChange(value),
      )}
    `;
  }

  /**
   * Ways to give the room a schedule: create one here (admins), or pick an existing Home
   * Assistant schedule helper.
   */
  private _renderAddSource() {
    const l = this.hass.language;
    const usedIds = new Set(this.schedules.map((s) => s.entity_id));
    return html`
      ${isAdmin(this.hass) ? this._renderCreate() : nothing}
      ${this._renderAddRow(
        localize("schedule_editor.add_existing", l),
        this._getAvailableEntities(usedIds),
        (eid) => this._addSchedule(eid),
      )}
    `;
  }

  private _renderCreate() {
    const l = this.hass.language;
    if (!this._creating) {
      return html`<rs-list-row
        class="create-row"
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("schedule_editor.create", l)}
        @row-click=${this._startCreate}
      ></rs-list-row>`;
    }
    return html`<rs-schedule-create
      .hass=${this.hass}
      .defaultName=${this.roomName}
      @create-cancelled=${() => (this._creating = false)}
      @schedule-created=${(e: CustomEvent<{ entityId: string }>) => {
        this._creating = false;
        this._emitSchedules([...this.schedules, { entity_id: e.detail.entityId }]);
        this._openEditor(e.detail.entityId);
      }}
    ></rs-schedule-create>`;
  }

  private _startCreate() {
    this._creating = true;
  }

  /** "Edit" for storage helpers (admins), "View" for YAML helpers and non-admins. */
  private _renderEditorButton(entityId: string) {
    const l = this.hass.language;
    const edit = isAdmin(this.hass) && isEditableSchedule(this.hass, entityId);
    if (!this.hass.states[entityId]) return nothing;
    return html`<ha-button appearance="outlined" @click=${() => this._openEditor(entityId)}>
      <ha-icon slot="start" .icon=${edit ? "mdi:pencil" : "mdi:eye-outline"}></ha-icon>
      ${localize(edit ? "schedule_editor.edit" : "schedule_editor.view", l)}
    </ha-button>`;
  }

  private _openEditor(entityId: string) {
    this.dispatchEvent(
      new CustomEvent("open-schedule-editor", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      }),
    );
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
              <span class="schedule-status"
                >${[this._getStatusText(index, state), this._usage(schedule.entity_id)]
                  .filter(Boolean)
                  .join(" · ")}</span
              >
              ${this._renderEditorButton(schedule.entity_id)}
              ${this._renderScheduleControls(
                index,
                count,
                (i, dir) => this._moveSchedule(i, dir),
                (i) => this._removeSchedule(i),
                this._getFriendlyName(schedule.entity_id),
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

    const unit = tempUnit(this.hass);
    // Block temperatures are entity attributes (display units); comfort/eco are °C
    const shown = (v: number) => formatNumber(v, this.hass, 0, 1);
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const band = (heat: string, cool: string) =>
      this.climateMode === "auto"
        ? `${heat}–${cool}\u00a0${unit}`
        : `${this.climateMode === "cool_only" ? cool : heat}\u00a0${unit}`;

    if (entityState.state === "on") {
      const { blockTemp, heatTemp, coolTemp } = this._readBlockTemps(index);
      if (blockTemp != null) {
        return localize("schedule.from_schedule", l, { temp: `${shown(blockTemp)}\u00a0${unit}` });
      }
      if (heatTemp != null || coolTemp != null) {
        return localize("schedule.from_schedule", l, {
          temp: band(
            heatTemp != null ? shown(heatTemp) : fmt(this.comfortHeat),
            coolTemp != null ? shown(coolTemp) : fmt(this.comfortCool),
          ),
        });
      }
      return localize("schedule.fallback", l, {
        temp: band(fmt(this.comfortHeat), fmt(this.comfortCool)),
      });
    }
    if (this.scheduleOffAction === "off") return localize("schedule.off_detail", l);
    return localize("schedule.eco_detail", l, {
      temp: band(fmt(this.ecoHeat), fmt(this.ecoCool)),
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
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-settings": RsScheduleSettings;
  }
}

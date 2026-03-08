import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, HassArea, CoverScheduleEntry } from "../types";
import { localize } from "../utils/localize";
import { getEntitiesForArea } from "../utils/room-state";
import "./shared/rs-toggle-row";
import "./shared/rs-threshold-field";
import "./rs-cover-schedule";

@customElement("rs-covers-section")
export class RsCoverSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public selectedCovers: Set<string> = new Set();
  @property({ type: Boolean }) public editing = false;
  @property({ type: Boolean }) public autoEnabled = false;
  @property({ type: Number }) public deployThreshold = 1.5;
  @property({ type: Number }) public minPosition = 0;
  @property({ type: Number, attribute: false }) public outdoorMinTemp: number | null = 10.0;
  @property({ type: Number }) public overrideMinutes = 60;
  @property({ type: Boolean }) public autoPaused = false;
  @property({ attribute: false }) public coverSchedules: CoverScheduleEntry[] = [];
  @property({ type: String }) public coverScheduleSelectorEntity = "";
  @property({ type: Number }) public activeCoverScheduleIndex = -1;
  @property({ type: Boolean }) public nightClose = false;
  @property({ type: Number }) public nightPosition = 0;
  @property({ type: String }) public forcedReason = "";

  static styles = css`
    :host { display: block; }
    .cover-list { display: flex; flex-direction: column; gap: 8px; }
    .cover-row { display: flex; align-items: center; gap: 8px; }
    .pos-badge {
      font-size: 0.8em; padding: 1px 6px; border-radius: 10px;
      background: var(--primary-color); color: var(--text-primary-color);
    }

    /* Device-row style (matches rs-device-section) */
    .device-list-scroll {
      max-height: 210px;
      overflow-y: auto;
    }
    .device-row {
      display: flex;
      align-items: center;
      padding: 4px 0;
      margin-bottom: 2px;
      border-radius: 8px;
      transition: background 0.15s;
    }
    .device-row:hover { background: rgba(0, 0, 0, 0.02); }
    .device-row.selected { background: rgba(3, 169, 244, 0.035); }
    .device-row ha-checkbox { flex-shrink: 0; }
    .device-info { flex: 1; min-width: 0; }
    .device-name-row { display: flex; align-items: center; gap: 6px; }
    .device-name { font-size: 14px; font-weight: 450; }
    .device-value {
      margin-left: auto;
      font-size: 13px;
      font-weight: 500;
      padding-right: 4px;
      white-space: nowrap;
    }
    .device-entity {
      font-family: var(--code-font-family, monospace);
      font-size: 11px;
      color: var(--secondary-text-color);
      opacity: 0.7;
    }
    .external-badge {
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 500;
      color: var(--secondary-text-color);
      background: var(--divider-color, rgba(0,0,0,0.06));
      padding: 1px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .no-devices {
      color: var(--secondary-text-color);
      font-size: 13px;
      padding: 8px 0;
    }

    .entity-picker-wrap { margin-top: 8px; }
    ha-entity-picker { width: 100%; }
    .settings-group { margin-top: 16px; display: flex; flex-direction: column; gap: 12px; }
    .sub-section {
      margin-top: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .sub-section:first-child { margin-top: 8px; }
    .sub-section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.3px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.12));
    }
    .sub-section-header ha-icon { --mdc-icon-size: 18px; }
    .field-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    @media (max-width: 450px) {
      .field-row { grid-template-columns: 1fr; }
    }
    .no-items { color: var(--secondary-text-color); font-size: 0.9em; margin: 0; }
    .status-hint {
      display: flex; align-items: center; gap: 6px;
      color: var(--secondary-text-color); font-size: 0.85em;
    }
    .status-hint.paused { color: var(--warning-color, #ff9800); }
  `;

  render() {
    const l = this.hass.language;
    return this.editing ? this._renderEdit(l) : this._renderView(l);
  }

  private _renderView(l: string) {
    const covers = [...this.selectedCovers];
    if (covers.length === 0) {
      return html`<p class="no-items">${localize("covers.no_covers", l)}</p>`;
    }
    return html`
      <div class="cover-list">
        ${covers.map(eid => {
          const st = this.hass.states[eid];
          const name = st?.attributes?.friendly_name as string ?? eid;
          const pos = st?.attributes?.current_position as number | undefined;
          return html`
            <div class="cover-row">
              <ha-icon icon="mdi:blinds-horizontal"></ha-icon>
              <span>${name}</span>
              ${pos !== undefined ? html`<span class="pos-badge">${pos}%</span>` : nothing}
            </div>
          `;
        })}
        ${this.autoPaused ? html`
          <div class="status-hint paused">
            <ha-icon icon="mdi:hand-back-right"></ha-icon>
            <span>${localize("covers.auto_paused", l)}</span>
          </div>
        ` : this.autoEnabled ? html`
          <div class="status-hint">
            <ha-icon icon="mdi:sun-angle-outline"></ha-icon>
            <span>${localize("covers.shading_active", l)}</span>
          </div>
        ` : nothing}
        ${this.forcedReason === "schedule_active" ? html`
          <div class="status-hint">
            <ha-icon icon="mdi:calendar-clock"></ha-icon>
            <span>${localize("covers.schedule_active", l)}</span>
          </div>
        ` : this.forcedReason === "night_close" ? html`
          <div class="status-hint">
            <ha-icon icon="mdi:weather-night"></ha-icon>
            <span>${localize("covers.night_close_active", l)}</span>
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _entityFilter = (entity: { entity_id: string }): boolean => {
    return entity.entity_id.startsWith("cover.") && !this.selectedCovers.has(entity.entity_id);
  };

  private _renderCoverRow(entityId: string, external: boolean) {
    const isSelected = this.selectedCovers.has(entityId);
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const pos = entityState?.attributes?.current_position as number | undefined;
    const l = this.hass.language;

    return html`
      <div class="device-row ${isSelected ? "selected" : ""}">
        <ha-checkbox
          .checked=${isSelected}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onToggle(entityId, target.checked);
          }}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge">${localize("devices.other_area", l)}</span>`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        ${pos !== undefined
          ? html`<span class="device-value">${pos}%</span>`
          : nothing}
      </div>
    `;
  }

  private _renderEdit(l: string) {
    // Discover cover entities in this area
    const allAreaEntities = getEntitiesForArea(
      this.area.area_id,
      this.hass?.entities,
      this.hass?.devices,
    );
    const areaCoverEntities = allAreaEntities.filter(
      (e) => e.entity_id.startsWith("cover."),
    );
    const areaCoverIds = new Set(areaCoverEntities.map((e) => e.entity_id));

    // Find selected covers not in this area (externally added)
    const externalCoverIds = [...this.selectedCovers].filter(
      (id) => !areaCoverIds.has(id),
    );

    const hasAnySelected = this.selectedCovers.size > 0;

    return html`
      <div class="device-list-scroll">
        ${areaCoverEntities.length > 0
          ? areaCoverEntities.map((entity) =>
              this._renderCoverRow(entity.entity_id, false)
            )
          : html`<div class="no-devices">
              ${localize("covers.no_covers_in_area", l)}
            </div>`}
        ${externalCoverIds.map((id) => this._renderCoverRow(id, true))}
      </div>

      <div class="entity-picker-wrap">
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["cover"]}
          .entityFilter=${this._entityFilter}
          .value=${""}
          .label=${localize("covers.add_cover", l)}
          @value-changed=${this._onEntityPicked}
        ></ha-entity-picker>
      </div>

      ${hasAnySelected ? html`
        <div class="settings-group">
          <rs-toggle-row
            .label=${localize("covers.auto_control", l)}
            .hint=${localize("covers.auto_control_hint", l)}
            .checked=${this.autoEnabled}
            @toggle-changed=${(e: CustomEvent) => this._emit("covers_auto_enabled", e.detail)}
          ></rs-toggle-row>

          ${this.autoEnabled ? html`
            <div class="sub-section">
              <div class="sub-section-header">
                <ha-icon icon="mdi:calendar-clock"></ha-icon>
                ${localize("covers.schedule_group_title", l)}
              </div>
              <rs-cover-schedule
                .hass=${this.hass}
                .schedules=${this.coverSchedules}
                .selectorEntity=${this.coverScheduleSelectorEntity}
                .activeIndex=${this.activeCoverScheduleIndex}
                .editing=${true}
                @cover-schedules-changed=${(e: CustomEvent) =>
                  this._emit("cover_schedules", e.detail.value)}
                @cover-schedule-selector-changed=${(e: CustomEvent) =>
                  this._emit("cover_schedule_selector_entity", e.detail.value)}
              ></rs-cover-schedule>
              <rs-toggle-row
                .label=${localize("covers.night_close", l)}
                .hint=${localize("covers.night_close_hint", l)}
                .checked=${this.nightClose}
                @toggle-changed=${(e: CustomEvent) => this._emit("covers_night_close", e.detail)}
              ></rs-toggle-row>
              ${this.nightClose ? html`
                <rs-threshold-field
                  .label=${localize("covers.night_position", l)}
                  .hint=${localize("covers.night_position_hint", l)}
                  .value=${this.nightPosition}
                  .min=${0} .max=${100} .step=${5}
                  suffix="%"
                  @value-changed=${(e: CustomEvent) => this._emit("covers_night_position", e.detail)}
                ></rs-threshold-field>
              ` : nothing}
            </div>

            <div class="sub-section">
              <div class="sub-section-header">
                <ha-icon icon="mdi:white-balance-sunny"></ha-icon>
                ${localize("covers.solar_group_title", l)}
              </div>
              <div class="field-row">
                <rs-threshold-field
                  .label=${localize("covers.deploy_threshold", l)}
                  .hint=${localize("covers.deploy_threshold_hint", l)}
                  .value=${this.deployThreshold}
                  .min=${0.5} .max=${5.0} .step=${0.5}
                  suffix="°C"
                  @value-changed=${(e: CustomEvent) => this._emit("covers_deploy_threshold", e.detail)}
                ></rs-threshold-field>
                <rs-threshold-field
                  .label=${localize("covers.min_position", l)}
                  .hint=${localize("covers.min_position_hint", l)}
                  .value=${this.minPosition}
                  .min=${0} .max=${80} .step=${5}
                  suffix="%"
                  @value-changed=${(e: CustomEvent) => this._emit("covers_min_position", e.detail)}
                ></rs-threshold-field>
              </div>
              <rs-toggle-row
                .label=${localize("covers.outdoor_gate", l)}
                .hint=${localize("covers.outdoor_gate_hint", l)}
                .checked=${this.outdoorMinTemp !== null}
                @toggle-changed=${(e: CustomEvent) => {
                  if (e.detail) {
                    this._emit("covers_outdoor_min_temp", 10.0);
                  } else {
                    this._emit("covers_outdoor_min_temp", null);
                  }
                }}
              ></rs-toggle-row>
              <div class="field-row">
                ${this.outdoorMinTemp !== null ? html`
                  <rs-threshold-field
                    .label=${localize("covers.outdoor_min_temp", l)}
                    .value=${this.outdoorMinTemp}
                    .min=${0} .max=${35} .step=${1}
                    suffix="°C"
                    @value-changed=${(e: CustomEvent) => this._emit("covers_outdoor_min_temp", e.detail)}
                  ></rs-threshold-field>
                ` : nothing}
                <rs-threshold-field
                  .label=${localize("covers.override_minutes", l)}
                  .hint=${localize("covers.override_minutes_hint", l)}
                  .value=${this.overrideMinutes}
                  .min=${0} .max=${480} .step=${15}
                  suffix="min"
                  @value-changed=${(e: CustomEvent) => this._emit("covers_override_minutes", e.detail)}
                ></rs-threshold-field>
              </div>
            </div>
          ` : nothing}
        </div>
      ` : nothing}
    `;
  }

  private _onEntityPicked(ev: CustomEvent) {
    ev.stopPropagation();
    const eid = ev.detail.value as string;
    if (!eid) return;
    this._onToggle(eid, true);
    // Reset picker value
    const picker = ev.target as HTMLElement & { value: string };
    picker.value = "";
  }

  private _onToggle(eid: string, checked: boolean) {
    this.dispatchEvent(new CustomEvent("covers-toggle", {
      detail: { entityId: eid, checked },
      bubbles: true, composed: true,
    }));
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(new CustomEvent("setting-changed", {
      detail: { key, value },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-covers-section": RsCoverSection;
  }
}

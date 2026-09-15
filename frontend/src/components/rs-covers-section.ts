import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, CoverScheduleEntry } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { getEntitiesForArea } from "../utils/room-state";
import { getSelectValue } from "../utils/events";
import { masterDetailStyles } from "../styles/master-detail-styles";
import { inputStyles } from "../styles/input-styles";
import "./shared/rs-toggle-row";
import "./shared/rs-threshold-field";
import "./shared/rs-master-detail";
import "./shared/rs-info-icon";
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
  @property({ type: Number }) public overrideMinutes = 60;
  @property({ type: Boolean }) public autoPaused = false;
  @property({ type: Number }) public overrideUntil: number | null = null;
  @property({ attribute: false }) public coverSchedules: CoverScheduleEntry[] = [];
  @property({ type: String }) public coverScheduleSelectorEntity = "";
  @property({ type: Number }) public activeCoverScheduleIndex = -1;
  @property({ type: Boolean }) public nightClose = false;
  @property({ type: Number }) public nightPosition = 0;
  @property({ type: Boolean }) public snapDeploy = false;
  @property({ type: String }) public forcedReason = "";
  @property({ attribute: false }) public coverOrientations: Record<string, number> = {};
  @property({ type: Number }) public nightCloseElevation = 0;
  @property({ type: Number }) public nightCloseOffsetMinutes = 0;
  @property({ type: Number }) public outdoorMinTemp: number | null = 10;
  @property({ attribute: false }) public coverMinPositions: Record<string, number> = {};
  @state() private _selectedForEdit = "";
  @state() private _scheduleCollapsed = true;
  @state() private _solarCollapsed = true;

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("selectedCovers")) {
      if (this._selectedForEdit && !this.selectedCovers.has(this._selectedForEdit)) {
        this._selectedForEdit = "";
      }
      if (!this._selectedForEdit && this.selectedCovers.size > 0) {
        this._selectedForEdit = [...this.selectedCovers][0];
      }
    }
  }

  static styles = [
    masterDetailStyles,
    inputStyles,
    css`
      :host {
        display: block;
      }

      /* Tile view rows (match rs-sensor-section visual rhythm) */
      .view-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 0;
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .view-name {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .view-pill {
        font-size: 10px;
        font-weight: 500;
        padding: 1px 7px;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.05);
        color: var(--secondary-text-color);
        letter-spacing: 0.3px;
        text-transform: uppercase;
        flex-shrink: 0;
      }

      .view-value {
        font-weight: 500;
        flex-shrink: 0;
        color: var(--primary-text-color);
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
      .device-row:hover {
        background: rgba(0, 0, 0, 0.02);
      }
      .device-row.selected {
        background: rgba(3, 169, 244, 0.035);
      }
      .device-row ha-checkbox {
        flex-shrink: 0;
      }
      .device-info {
        flex: 1;
        min-width: 0;
      }
      .device-name-row {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .device-name {
        font-size: 14px;
        font-weight: 450;
      }
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
        background: var(--divider-color, rgba(0, 0, 0, 0.06));
        padding: 1px 6px;
        border-radius: 4px;
        white-space: nowrap;
      }
      .no-devices {
        color: var(--secondary-text-color);
        font-size: 13px;
        padding: 8px 0;
      }

      .entity-picker-wrap {
        margin-top: 8px;
      }
      ha-entity-picker {
        width: 100%;
      }
      .settings-group {
        margin-top: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .sub-section {
        margin-top: 20px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .sub-section:first-child {
        margin-top: 8px;
      }
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
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .sub-section-header ha-icon {
        --mdc-icon-size: 18px;
      }
      .field-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
      }
      @media (max-width: 450px) {
        .field-row {
          grid-template-columns: 1fr;
        }
      }
      .no-items {
        color: var(--secondary-text-color);
        font-size: 0.9em;
        margin: 0;
      }
      .status-hint {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px;
        color: var(--secondary-text-color);
        font-size: 0.85em;
      }
      .status-hint.paused {
        color: var(--warning-color, #ff9800);
      }
      .pill {
        font-size: 10px;
        font-weight: 500;
        padding: 1px 6px;
        border-radius: 10px;
        background: var(--divider-color, rgba(0, 0, 0, 0.08));
        color: var(--secondary-text-color);
        white-space: nowrap;
      }

      /* Editing layout — feature card + grouped sections */
      .feature-card {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 14px 16px;
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        background: var(--card-background-color);
        transition:
          border-color 0.2s ease,
          background 0.2s ease;
      }

      .feature-card.enabled {
        border-color: rgba(3, 169, 244, 0.4);
        background: rgba(3, 169, 244, 0.06);
      }

      .feature-text {
        flex: 1;
        min-width: 0;
      }

      .feature-title {
        font-size: 14px;
        font-weight: 500;
        margin: 0 0 4px;
      }

      .feature-description {
        font-size: 12px;
        color: var(--secondary-text-color);
        line-height: 1.5;
        margin: 0;
      }

      .feature-card ha-switch {
        flex-shrink: 0;
      }

      .group-card {
        margin-top: 16px;
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        background: var(--card-background-color);
        padding: 14px 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .group-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: var(--secondary-text-color);
        cursor: pointer;
        user-select: none;
      }

      .group-header > span:first-of-type {
        flex: 1;
        min-width: 0;
      }

      .group-header ha-icon {
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
      }

      .group-header .chevron {
        transition: transform 0.2s ease;
        margin-left: auto;
      }

      .group-header .chevron.collapsed {
        transform: rotate(-90deg);
      }

      .group-card.collapsed {
        gap: 0;
        padding-bottom: 14px;
      }

      .group-divider {
        height: 1px;
        background: var(--divider-color);
        margin: 4px -16px;
      }
    `,
  ];

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
      ${covers.map((eid) => {
        const st = this.hass.states[eid];
        const name = (st?.attributes?.friendly_name as string) ?? eid;
        const pos = st?.attributes?.current_position as number | undefined;
        const orient = this.coverOrientations[eid];
        const orientDir =
          orient !== undefined
            ? RsCoverSection._DIRECTIONS.find((d) => d.deg === orient)
            : undefined;
        const orientLabel = orientDir ? localize(orientDir.shortLabel, l) : undefined;
        const minPos = this.coverMinPositions[eid];
        return html`
          <div class="view-row">
            <span class="view-name">${name}</span>
            ${orientLabel ? html`<span class="view-pill">${orientLabel}</span>` : nothing}
            ${
              minPos !== undefined && minPos > 0
                ? html`<span class="view-pill"
                    >${localize("covers.per_cover_min_short", l)} ${minPos}%</span
                  >`
                : nothing
            }
            ${pos !== undefined ? html`<span class="view-value">${pos}%</span>` : nothing}
          </div>
        `;
      })}
      ${
        this.autoPaused
          ? html`
              <div class="status-hint paused">
                <ha-icon icon="mdi:hand-back-right"></ha-icon>
                <span>
                  ${
                    this.overrideUntil
                      ? `${localize("covers.auto_paused_until", l)} ${new Date(
                          this.overrideUntil * 1000,
                        ).toLocaleTimeString(l, { hour: "2-digit", minute: "2-digit" })}`
                      : localize("covers.auto_paused", l)
                  }
                </span>
                <ha-button @click=${this._onResumeAuto}
                  >${localize("covers.resume_auto", l)}</ha-button
                >
              </div>
            `
          : this.autoEnabled
            ? html`
                <div class="status-hint">
                  <ha-icon icon="mdi:sun-angle-outline"></ha-icon>
                  <span>${localize("covers.shading_active", l)}</span>
                </div>
              `
            : nothing
      }
      ${
        this.forcedReason === "schedule_active"
          ? html`
              <div class="status-hint">
                <ha-icon icon="mdi:calendar-clock"></ha-icon>
                <span>${localize("covers.schedule_active", l)}</span>
              </div>
            `
          : this.forcedReason === "night_close"
            ? html`
                <div class="status-hint">
                  <ha-icon icon="mdi:weather-night"></ha-icon>
                  <span>${localize("covers.night_close_active", l)}</span>
                </div>
              `
            : nothing
      }
    `;
  }

  private _entityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    if (id.startsWith("cover.roommind_")) return false;
    return id.startsWith("cover.") && !this.selectedCovers.has(id);
  };

  private _renderMasterRow(entityId: string, external: boolean) {
    const isInRoom = this.selectedCovers.has(entityId);
    const isFocused = this._selectedForEdit === entityId;
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const pos = entityState?.attributes?.current_position as number | undefined;
    const l = this.hass.language;
    const orient = this.coverOrientations[entityId];
    const orientDir =
      orient !== undefined ? RsCoverSection._DIRECTIONS.find((d) => d.deg === orient) : undefined;
    const orientLabel = orientDir ? localize(orientDir.shortLabel, l) : "";
    const minPos = this.coverMinPositions[entityId];

    return html`
      <div
        class="master-row ${isFocused ? "focused" : ""}"
        @click=${() => (this._selectedForEdit = entityId)}
      >
        <ha-checkbox
          .checked=${isInRoom}
          @click=${(e: Event) => e.stopPropagation()}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onToggle(entityId, target.checked);
            if (target.checked) this._selectedForEdit = entityId;
          }}
        ></ha-checkbox>
        <div class="master-info">
          <div class="master-name-row">
            <span class="master-name">${friendlyName}</span>
            ${
              external
                ? html`<span class="external-badge">${localize("devices.other_area", l)}</span>`
                : nothing
            }
          </div>
          <div class="master-meta">
            ${orientLabel ? html`<span class="meta-pill">${orientLabel}</span>` : nothing}
            ${
              minPos !== undefined && minPos > 0
                ? html`<span class="meta-pill">min ${minPos}%</span>`
                : nothing
            }
            ${
              pos !== undefined
                ? html`<span class="meta-pill" style="color: var(--primary-color);">${pos}%</span>`
                : nothing
            }
          </div>
        </div>
      </div>
    `;
  }

  private _renderCoverDetail(entityId: string) {
    const l = this.hass.language;
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const currentOrientation = this.coverOrientations[entityId];
    const currentMin = this.coverMinPositions[entityId];

    return html`
      <div class="detail-head">
        <div class="detail-title">${friendlyName}</div>
        <div class="detail-entity-id">${entityId}</div>
      </div>
      <div class="detail-field">
        <ha-select
          .label=${localize("covers.orientation_group_title", l)}
          .value=${currentOrientation !== undefined ? String(currentOrientation) : ""}
          .options=${[
            { value: "", label: localize("covers.orientation_none", l) },
            ...RsCoverSection._DIRECTIONS.map((d) => ({
              value: String(d.deg),
              label: localize(d.longLabel, l),
            })),
          ]}
          fixedMenuPosition
          @selected=${(e: Event) => {
            const val = getSelectValue(e);
            this._setOrientation(entityId, val === "" ? undefined : Number(val));
          }}
          @closed=${(e: Event) => e.stopPropagation()}
        >
          <ha-list-item value="">${localize("covers.orientation_none", l)}</ha-list-item>
          ${RsCoverSection._DIRECTIONS.map(
            (d) => html`
              <ha-list-item value=${String(d.deg)}>${localize(d.longLabel, l)}</ha-list-item>
            `,
          )}
        </ha-select>
      </div>
      <div class="detail-field">
        <rs-threshold-field
          .label=${localize("covers.per_cover_min_position", l)}
          .value=${currentMin ?? 0}
          .min=${0}
          .max=${99}
          .step=${1}
          suffix="%"
          @value-changed=${(e: CustomEvent) => this._setMinPosition(entityId, e.detail as number)}
        ></rs-threshold-field>
      </div>
    `;
  }

  private _renderEdit(l: string) {
    // Discover cover entities in this area
    // Exclude RoomMind's own entities to prevent self-assignment (#86)
    const allAreaEntities = getEntitiesForArea(
      this.area.area_id,
      this.hass?.entities,
      this.hass?.devices,
    ).filter((e) => {
      const idAfterDot = e.entity_id.substring(e.entity_id.indexOf(".") + 1);
      return !idAfterDot.startsWith("roommind_");
    });
    const areaCoverEntities = allAreaEntities.filter((e) => e.entity_id.startsWith("cover."));
    const areaCoverIds = new Set(areaCoverEntities.map((e) => e.entity_id));

    // Find selected covers not in this area (externally added)
    const externalCoverIds = [...this.selectedCovers].filter((id) => !areaCoverIds.has(id));

    const hasAnySelected = this.selectedCovers.size > 0;

    const detailId = this._selectedForEdit;
    const detailInRoom = detailId && this.selectedCovers.has(detailId);

    return html`
      <rs-master-detail>
        <div slot="master" class="master">
          <div class="block-title">${localize("covers.add_cover", l)}</div>
          <div class="master-list">
            ${
              areaCoverEntities.length > 0
                ? areaCoverEntities.map((e) => this._renderMasterRow(e.entity_id, false))
                : html`<div class="empty-list">${localize("covers.no_covers_in_area", l)}</div>`
            }
            ${externalCoverIds.map((id) => this._renderMasterRow(id, true))}
          </div>
          <div class="picker-wrap">
            <ha-entity-picker
              .hass=${this.hass}
              .includeDomains=${["cover"]}
              .entityFilter=${this._entityFilter}
              .value=${""}
              .label=${localize("covers.add_cover", l)}
              @value-changed=${this._onEntityPicked}
            ></ha-entity-picker>
          </div>
        </div>
        <div slot="detail">
          ${
            detailInRoom
              ? html`<div class="detail-panel">${this._renderCoverDetail(detailId)}</div>`
              : html`<div class="detail-panel">
                  <div class="empty-detail">
                    <ha-icon icon="mdi:gesture-tap"></ha-icon>
                    <span>${localize("devices.select_to_configure", l)}</span>
                  </div>
                </div>`
          }
        </div>
      </rs-master-detail>

      ${
        hasAnySelected
          ? html`
              <div class="block-divider"></div>
              <div class="feature-card ${this.autoEnabled ? "enabled" : ""}">
                <div class="feature-text">
                  <div class="feature-title">${localize("covers.auto_control", l)}</div>
                  <div class="feature-description">${localize("covers.auto_control_hint", l)}</div>
                </div>
                <ha-switch
                  .checked=${this.autoEnabled}
                  @change=${(e: Event) =>
                    this._emit("covers_auto_enabled", (e.target as HTMLInputElement).checked)}
                ></ha-switch>
              </div>

              ${
                this.autoEnabled
                  ? html`
                      <div class="group-card ${this._scheduleCollapsed ? "collapsed" : ""}">
                        <div
                          class="group-header"
                          @click=${() => (this._scheduleCollapsed = !this._scheduleCollapsed)}
                        >
                          <ha-icon icon="mdi:calendar-clock"></ha-icon>
                          <span>${localize("covers.schedule_group_title", l)}</span>
                          <rs-info-icon
                            .text=${localize("covers.schedule_section_hint", l)}
                          ></rs-info-icon>
                          <ha-icon
                            class="chevron ${this._scheduleCollapsed ? "collapsed" : ""}"
                            icon="mdi:chevron-down"
                          ></ha-icon>
                        </div>
                        ${
                          this._scheduleCollapsed
                            ? nothing
                            : html`<rs-cover-schedule
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
                                <div class="group-divider"></div>
                                <rs-toggle-row
                                  .label=${localize("covers.night_close", l)}
                                  .hint=${localize("covers.night_close_hint", l)}
                                  .checked=${this.nightClose}
                                  @toggle-changed=${(e: CustomEvent) =>
                                    this._emit("covers_night_close", e.detail)}
                                ></rs-toggle-row>
                                ${
                                  this.nightClose
                                    ? html`
                                        <rs-threshold-field
                                          .label=${localize("covers.night_position", l)}
                                          .hint=${localize("covers.night_position_hint", l)}
                                          .value=${this.nightPosition}
                                          .min=${0}
                                          .max=${100}
                                          .step=${5}
                                          suffix="%"
                                          @value-changed=${(e: CustomEvent) =>
                                            this._emit("covers_night_position", e.detail)}
                                        ></rs-threshold-field>
                                        <ha-expansion-panel
                                          .header=${localize("covers.night_close_advanced", l)}
                                          outlined
                                        >
                                          <div class="field-row" style="padding:8px 0;">
                                            <rs-threshold-field
                                              .label=${localize("covers.night_close_elevation", l)}
                                              .hint=${localize("covers.night_close_elevation_hint", l)}
                                              .value=${this.nightCloseElevation}
                                              .min=${-18}
                                              .max=${10}
                                              .step=${1}
                                              suffix="°"
                                              @value-changed=${(e: CustomEvent) =>
                                                this._emit(
                                                  "covers_night_close_elevation",
                                                  e.detail,
                                                )}
                                            ></rs-threshold-field>
                                            <rs-threshold-field
                                              .label=${localize("covers.night_close_offset", l)}
                                              .hint=${localize("covers.night_close_offset_hint", l)}
                                              .value=${this.nightCloseOffsetMinutes}
                                              .min=${-120}
                                              .max=${120}
                                              .step=${5}
                                              suffix="min"
                                              @value-changed=${(e: CustomEvent) =>
                                                this._emit(
                                                  "covers_night_close_offset_minutes",
                                                  e.detail,
                                                )}
                                            ></rs-threshold-field>
                                          </div>
                                        </ha-expansion-panel>
                                      `
                                    : nothing
                                }`
                        }
                      </div>

                      <div class="group-card ${this._solarCollapsed ? "collapsed" : ""}">
                        <div
                          class="group-header"
                          @click=${() => (this._solarCollapsed = !this._solarCollapsed)}
                        >
                          <ha-icon icon="mdi:white-balance-sunny"></ha-icon>
                          <span>${localize("covers.solar_group_title", l)}</span>
                          <ha-icon
                            class="chevron ${this._solarCollapsed ? "collapsed" : ""}"
                            icon="mdi:chevron-down"
                          ></ha-icon>
                        </div>
                        ${
                          this._solarCollapsed
                            ? nothing
                            : html`<div class="field-row">
                                  <rs-threshold-field
                                    .label=${localize("covers.deploy_threshold", l)}
                                    .hint=${localize("covers.deploy_threshold_hint", l)}
                                    .value=${this.deployThreshold}
                                    .min=${0.5}
                                    .max=${5.0}
                                    .step=${0.5}
                                    suffix="°C"
                                    @value-changed=${(e: CustomEvent) =>
                                      this._emit("covers_deploy_threshold", e.detail)}
                                  ></rs-threshold-field>
                                  <rs-threshold-field
                                    .label=${localize("covers.min_position", l)}
                                    .hint=${localize("covers.min_position_hint", l)}
                                    .value=${this.minPosition}
                                    .min=${0}
                                    .max=${80}
                                    .step=${5}
                                    suffix="%"
                                    @value-changed=${(e: CustomEvent) =>
                                      this._emit("covers_min_position", e.detail)}
                                  ></rs-threshold-field>
                                </div>
                                <div class="field-row">
                                  <rs-threshold-field
                                    .label=${localize("covers.override_minutes", l)}
                                    .hint=${localize("covers.override_minutes_hint", l)}
                                    .value=${this.overrideMinutes}
                                    .min=${0}
                                    .max=${480}
                                    .step=${15}
                                    suffix="min"
                                    @value-changed=${(e: CustomEvent) =>
                                      this._emit("covers_override_minutes", e.detail)}
                                  ></rs-threshold-field>
                                  <rs-threshold-field
                                    .label=${localize("covers.outdoor_min_temp", l)}
                                    .hint=${localize("covers.outdoor_min_temp_hint", l)}
                                    .value=${this.outdoorMinTemp ?? 10}
                                    .min=${0}
                                    .max=${35}
                                    .step=${1}
                                    suffix="°C"
                                    @value-changed=${(e: CustomEvent) =>
                                      this._emit("covers_outdoor_min_temp", e.detail)}
                                  ></rs-threshold-field>
                                </div>
                                <div class="group-divider"></div>
                                <rs-toggle-row
                                  .label=${localize("covers.snap_deploy", l)}
                                  .hint=${localize("covers.snap_deploy_hint", l)}
                                  .checked=${this.snapDeploy}
                                  @toggle-changed=${(e: CustomEvent) =>
                                    this._emit("covers_snap_deploy", e.detail)}
                                ></rs-toggle-row>`
                        }
                      </div>
                    `
                  : nothing
              }
            `
          : nothing
      }
    `;
  }

  private static readonly _DIRECTIONS: Array<{
    shortLabel: TranslationKey;
    longLabel: TranslationKey;
    deg: number;
  }> = [
    { shortLabel: "covers.orientation_N", longLabel: "covers.orientation_N_full", deg: 0 },
    { shortLabel: "covers.orientation_NE", longLabel: "covers.orientation_NE_full", deg: 45 },
    { shortLabel: "covers.orientation_E", longLabel: "covers.orientation_E_full", deg: 90 },
    { shortLabel: "covers.orientation_SE", longLabel: "covers.orientation_SE_full", deg: 135 },
    { shortLabel: "covers.orientation_S", longLabel: "covers.orientation_S_full", deg: 180 },
    { shortLabel: "covers.orientation_SW", longLabel: "covers.orientation_SW_full", deg: 225 },
    { shortLabel: "covers.orientation_W", longLabel: "covers.orientation_W_full", deg: 270 },
    { shortLabel: "covers.orientation_NW", longLabel: "covers.orientation_NW_full", deg: 315 },
  ];

  private _setMinPosition(eid: string, value: number) {
    const next = { ...this.coverMinPositions };
    next[eid] = value;
    this._emit("cover_min_positions", next);
  }

  private _setOrientation(eid: string, deg: number | undefined) {
    const next = { ...this.coverOrientations };
    if (deg === undefined) {
      delete next[eid];
    } else {
      next[eid] = deg;
    }
    this._emit("cover_orientations", next);
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
    this.dispatchEvent(
      new CustomEvent("covers-toggle", {
        detail: { entityId: eid, checked },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onResumeAuto() {
    this.dispatchEvent(new CustomEvent("cover-resume-auto", { bubbles: true, composed: true }));
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
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-covers-section": RsCoverSection;
  }
}

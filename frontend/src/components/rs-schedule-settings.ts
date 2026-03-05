import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { HomeAssistant, ScheduleEntry, ClimateMode } from "../types";
import { localize } from "../utils/localize";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { formatTemp, tempUnit, toDisplay, toCelsius, tempStep, tempRange } from "../utils/temperature";

@customElement("rs-schedule-settings")
export class RsScheduleSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public schedules: ScheduleEntry[] = [];
  @property({ type: String }) public scheduleSelectorEntity = "";
  @property({ type: Number }) public activeScheduleIndex = 0;
  @property({ type: Number }) public comfortHeat = 21.0;
  @property({ type: Number }) public comfortCool = 24.0;
  @property({ type: Number }) public ecoHeat = 17.0;
  @property({ type: Number }) public ecoCool = 27.0;
  @property({ type: String }) public climateMode: ClimateMode = "auto";

  @property({ type: Boolean }) public editing = false;

  static styles = css`
    :host {
      display: block;
    }

    .form-group {
      margin-bottom: 16px;
    }

    .form-group:last-child {
      margin-bottom: 0;
    }

    .form-label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    ha-select {
      width: 100%;
    }

    /* Selector section */
    .selector-section {
      margin-bottom: 16px;
    }

    .selector-value {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      padding-left: 4px;
    }

    .selector-warning {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      background: rgba(255, 152, 0, 0.08);
      color: var(--warning-color, #ff9800);
      font-size: 13px;
    }

    .selector-warning ha-icon {
      --mdc-icon-size: 18px;
      flex-shrink: 0;
    }

    /* Schedule list */
    .schedule-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 12px;
    }

    .schedule-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s, opacity 0.3s;
    }

    .schedule-row.active {
      background: rgba(76, 175, 80, 0.1);
    }

    .schedule-row.inactive {
      background: rgba(0, 0, 0, 0.04);
    }

    .schedule-row.unreachable {
      background: rgba(0, 0, 0, 0.02);
      opacity: 0.4;
    }

    .schedule-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 500;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--divider-color, #e0e0e0);
      color: var(--primary-text-color);
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-number {
      background: #4caf50;
      color: #fff;
    }

    .schedule-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-status-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .schedule-row.inactive .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-row.unreachable .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .schedule-link {
      cursor: pointer;
    }

    .schedule-link:hover {
      text-decoration: underline;
    }

    .schedule-row.active .schedule-name {
      color: var(--primary-text-color);
    }

    .schedule-row.inactive .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-status {
      font-size: 12px;
      white-space: nowrap;
    }

    .schedule-row.active .schedule-status {
      color: #2e7d32;
    }

    .schedule-row.inactive .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-controls {
      display: flex;
      align-items: center;
      gap: 2px;
      flex-shrink: 0;
    }

    .schedule-controls ha-icon-button {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
    }

    /* Add schedule row */
    .add-schedule-row {
      margin-top: 4px;
    }

    .add-schedule-row ha-select {
      width: 100%;
    }

    .helper-link {
      display: inline-block;
      margin-top: 4px;
      font-size: 12px;
      color: var(--primary-color);
      text-decoration: none;
    }

    .helper-link:hover {
      text-decoration: underline;
    }

    /* No schedules */
    .no-schedules {
      font-size: 13px;
      color: var(--secondary-text-color);
      padding: 12px 0;
      text-align: center;
    }

    /* Collapsible help */
    ha-expansion-panel {
      margin-top: 8px;
    }

    .help-content {
      padding: 0 12px 12px;
      font-size: 12px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }

    .help-content p {
      margin: 0 0 8px 0;
    }

    .help-content p:last-child {
      margin-bottom: 0;
    }

    .yaml-block {
      background: var(--primary-background-color, #f5f5f5);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: var(--code-font-family, monospace);
      font-size: 12px;
      line-height: 1.5;
      white-space: pre;
      overflow-x: auto;
      color: var(--primary-text-color);
    }

    .yaml-comment {
      color: var(--secondary-text-color);
    }

    .yaml-key {
      color: #0550ae;
    }

    .yaml-value {
      color: #0a3069;
    }

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

    /* View mode */
    .view-temps {
      display: flex;
      gap: 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .view-temps span {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .view-selector-info {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 8px;
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

  `;

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  private _renderViewMode() {
    const l = this.hass.language;
    const hasMultiple = this.schedules.length >= 2;

    return html`
      ${this.schedules.length > 0
        ? html`
          <div class="schedule-list">
            ${this.schedules.map((schedule, index) => {
              const state = this._getScheduleState(index);
              const entityState = this.hass?.states?.[schedule.entity_id];
              const friendlyName =
                (entityState?.attributes?.friendly_name as string) || schedule.entity_id;

              return html`
                <div class="schedule-row ${state}">
                  ${hasMultiple
                    ? html`<span class="schedule-number">${index + 1}</span>`
                    : nothing}
                  <span class="schedule-status-dot"></span>
                  <span class="schedule-name schedule-link" @click=${() => openEntityInfo(this,schedule.entity_id)}>${friendlyName}</span>
                  <span class="schedule-status">${this._getStatusText(index, state)}</span>
                </div>
              `;
            })}
          </div>
        `
        : html`<div class="no-schedules">${localize("schedule.no_schedules", l)}</div>`}

      ${this.climateMode === "auto" ? html`
        <div class="view-temps">
          ${localize("schedule.view_heat", l, {
            comfort: formatTemp(this.comfortHeat, this.hass),
            eco: formatTemp(this.ecoHeat, this.hass),
            unit: tempUnit(this.hass)
          })}
          \u00A0\u00B7\u00A0
          ${localize("schedule.view_cool", l, {
            comfort: formatTemp(this.comfortCool, this.hass),
            eco: formatTemp(this.ecoCool, this.hass),
            unit: tempUnit(this.hass)
          })}
        </div>
      ` : html`
        <div class="view-temps">
          ${localize("schedule.view_comfort", l, {
            temp: formatTemp(this.climateMode === "cool_only" ? this.comfortCool : this.comfortHeat, this.hass),
            unit: tempUnit(this.hass)
          })}
          \u00A0\u00B7\u00A0
          ${localize("schedule.view_eco", l, {
            temp: formatTemp(this.climateMode === "cool_only" ? this.ecoCool : this.ecoHeat, this.hass),
            unit: tempUnit(this.hass)
          })}
        </div>
      `}

      ${this.scheduleSelectorEntity
        ? html`<div class="view-selector-info">
            ${localize("schedule.view_selector_prefix", l)}
            <span class="schedule-link" @click=${() => openEntityInfo(this,this.scheduleSelectorEntity!)}>${(this.hass?.states?.[this.scheduleSelectorEntity]?.attributes?.friendly_name as string) || this.scheduleSelectorEntity}</span>
          </div>`
        : nothing}
    `;
  }

  private _renderEditMode() {
    const l = this.hass.language;
    const hasMultiple = this.schedules.length >= 2;

    return html`
      ${this._renderScheduleList(hasMultiple)}
      ${this._renderAddSchedule()}
      ${this._renderSelectorSection()}

      ${this.climateMode === "auto" ? html`
        <div class="temp-grid-auto">
          <div class="temp-grid-header"></div>
          <div class="temp-grid-header">${localize("schedule.column_comfort", l)}</div>
          <div class="temp-grid-header">${localize("schedule.column_eco", l)}</div>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:fire" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_heat", l)}
          </div>
          <ha-textfield type="number"
            .value=${String(toDisplay(this.comfortHeat, this.hass))}
            suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
            @change=${this._onComfortHeatChange}
          ></ha-textfield>
          <ha-textfield type="number"
            .value=${String(toDisplay(this.ecoHeat, this.hass))}
            suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
            @change=${this._onEcoHeatChange}
          ></ha-textfield>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:snowflake" style="--mdc-icon-size:16px"></ha-icon>
            ${localize("schedule.row_cool", l)}
          </div>
          <ha-textfield type="number"
            .value=${String(toDisplay(this.comfortCool, this.hass))}
            suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
            @change=${this._onComfortCoolChange}
          ></ha-textfield>
          <ha-textfield type="number"
            .value=${String(toDisplay(this.ecoCool, this.hass))}
            suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
            min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
            @change=${this._onEcoCoolChange}
          ></ha-textfield>
        </div>
      ` : html`
        <div class="temp-inputs">
          <div class="temp-input-group">
            <ha-textfield type="number"
              label=${localize("schedule.comfort_label", l)}
              suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
              .value=${String(toDisplay(this.climateMode === "cool_only" ? this.comfortCool : this.comfortHeat, this.hass))}
              min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
              @change=${this.climateMode === "cool_only" ? this._onComfortCoolChange : this._onComfortHeatChange}
            ></ha-textfield>
          </div>
          <div class="temp-input-group">
            <ha-textfield type="number"
              label=${localize("schedule.eco_label", l)}
              suffix=${tempUnit(this.hass)} step=${tempStep(this.hass)}
              .value=${String(toDisplay(this.climateMode === "cool_only" ? this.ecoCool : this.ecoHeat, this.hass))}
              min=${tempRange(5, 35, this.hass).min} max=${tempRange(5, 35, this.hass).max}
              @change=${this.climateMode === "cool_only" ? this._onEcoCoolChange : this._onEcoHeatChange}
            ></ha-textfield>
          </div>
        </div>
      `}
      <div class="fallback-hint">
        ${this.climateMode === "auto"
          ? localize("schedule.comfort_hint_auto", l)
          : localize("schedule.comfort_hint", l)}
      </div>

      <ha-expansion-panel outlined header=${localize("schedule.help_header", l)}>
        <div class="help-content">
          <p><strong>${localize("schedule.help_temps_title", l)}</strong></p>
          <p>${localize("schedule.help_temps", l)}</p>
          <ol style="margin: 4px 0 0 0; padding-left: 20px; font-size: 12px; line-height: 1.8">
            <li>${unsafeHTML(localize("schedule.help_temps_1", l))}</li>
            <li>${unsafeHTML(localize("schedule.help_temps_2", l))}</li>
            <li>${unsafeHTML(localize("schedule.help_temps_3", l))}</li>
            <li>${unsafeHTML(localize("schedule.help_temps_4", l))}</li>
          </ol>

          <p style="margin-top: 12px"><strong>${localize("schedule.help_block_title", l)}</strong></p>
          <p>${unsafeHTML(localize("schedule.help_block", l))}</p>
          <div class="yaml-block"><span class="yaml-key">schedule</span>:
  <span class="yaml-key">living_room_heating</span>:
    <span class="yaml-key">name</span>: <span class="yaml-value">Living Room Heating</span>
    <span class="yaml-key">monday</span>:
      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">23</span>
      - <span class="yaml-key">from</span>: <span class="yaml-value">"17:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"22:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">21.5</span></div>
          <p style="margin-top: 8px">${unsafeHTML(localize("schedule.help_block_note", l))}</p>

          <p style="margin-top: 12px"><strong>${localize("schedule.help_split_title", l)}</strong></p>
          <p>${unsafeHTML(localize("schedule.help_split", l))}</p>
          <div class="yaml-block">      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">heat_temperature</span>: <span class="yaml-value">21</span>
          <span class="yaml-key">cool_temperature</span>: <span class="yaml-value">24</span></div>
          <p style="margin-top: 8px">${unsafeHTML(localize("schedule.help_split_note", l))}</p>

          <p style="margin-top: 12px"><strong>${localize("schedule.help_multi_title", l)}</strong></p>
          <p>${unsafeHTML(localize("schedule.help_multi", l))}</p>
        </div>
      </ha-expansion-panel>

    `;
  }

  private _renderSelectorSection() {
    const l = this.hass.language;
    const showSelector = this.schedules.length >= 2;

    if (!showSelector) return nothing;

    const selectorState = this.scheduleSelectorEntity
      ? this.hass?.states?.[this.scheduleSelectorEntity]
      : null;

    return html`
      <div class="selector-section">
        <label class="form-label">${localize("schedule.selector_label", l)}</label>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.scheduleSelectorEntity}
          .includeDomains=${["input_boolean", "input_number"]}
          allow-custom-entity
          @value-changed=${this._onSelectorEntityChange}
        ></ha-entity-picker>
        ${!this.scheduleSelectorEntity
          ? nothing
          : selectorState
            ? html`
                <div class="selector-value">
                  ${this.scheduleSelectorEntity.startsWith("input_boolean.")
                    ? localize("schedule.selector_value_boolean", l, {
                        value: selectorState.state === "on" ? "On" : "Off",
                      })
                    : localize("schedule.selector_value_number", l, {
                        value: selectorState.state,
                      })}
                </div>
              `
            : nothing}
        ${this.schedules.length > 1 && !this.scheduleSelectorEntity
          ? html`
              <div class="selector-warning">
                <ha-icon icon="mdi:alert-outline"></ha-icon>
                ${localize("schedule.selector_warning", l)}
              </div>
            `
          : nothing}
      </div>
    `;
  }

  private _renderScheduleList(hasMultiple: boolean) {
    const l = this.hass.language;

    if (this.schedules.length === 0) {
      return html`<div class="no-schedules">${localize("schedule.no_schedules", l)}</div>`;
    }

    return html`
      <div class="schedule-list">
        ${this.schedules.map((schedule, index) => {
          const state = this._getScheduleState(index);
          const entityState = this.hass?.states?.[schedule.entity_id];
          const friendlyName =
            (entityState?.attributes?.friendly_name as string) || schedule.entity_id;

          return html`
            <div class="schedule-row ${state}">
              ${hasMultiple
                ? html`<span class="schedule-number">${index + 1}</span>`
                : nothing}
              <span class="schedule-status-dot"></span>
              <span class="schedule-name">${friendlyName}</span>
              <span class="schedule-status">${this._getStatusText(index, state)}</span>
              <span class="schedule-controls">
                ${hasMultiple && index > 0
                  ? html`
                      <ha-icon-button
                        .path=${"M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"}
                        @click=${() => this._onMoveSchedule(index, -1)}
                      ></ha-icon-button>
                    `
                  : nothing}
                ${hasMultiple && index < this.schedules.length - 1
                  ? html`
                      <ha-icon-button
                        .path=${"M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z"}
                        @click=${() => this._onMoveSchedule(index, 1)}
                      ></ha-icon-button>
                    `
                  : nothing}
                <ha-icon-button
                  .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                  @click=${() => this._onRemoveSchedule(index)}
                ></ha-icon-button>
              </span>
            </div>
          `;
        })}
      </div>
    `;
  }

  private _renderAddSchedule() {
    const l = this.hass.language;
    const availableEntities = this._getAvailableScheduleEntities();

    return html`
      <div class="add-schedule-row">
        <ha-select
          .value=${""}
          .label=${localize("schedule.select_schedule", l)}
          .options=${availableEntities.map((entityId) => ({
            value: entityId,
            label: (this.hass.states[entityId]?.attributes?.friendly_name as string) || entityId,
          }))}
          @selected=${this._onAddSchedule}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
          naturalMenuWidth
        >
          ${availableEntities.map((entityId) => {
            const entityState = this.hass.states[entityId];
            const friendlyName =
              (entityState?.attributes?.friendly_name as string) || entityId;
            return html`
              <ha-list-item value=${entityId}>
                ${friendlyName}
              </ha-list-item>
            `;
          })}
        </ha-select>
        <a href="/config/helpers" target="_top" class="helper-link">
          ${localize("schedule.create_helper_hint", l)}
        </a>
      </div>
    `;
  }

  private _getScheduleState(index: number): "active" | "inactive" | "unreachable" {
    if (this.schedules.length === 0) return "inactive";
    if (index === this.activeScheduleIndex) return "active";

    // Check if unreachable based on selector entity
    if (!this.scheduleSelectorEntity) {
      // No selector: only index 0 can be active
      return index === 0 ? "active" : "unreachable";
    }

    const selectorState = this.hass?.states?.[this.scheduleSelectorEntity];
    if (!selectorState) return "inactive"; // selector unavailable, could change

    if (this.scheduleSelectorEntity.startsWith("input_boolean.")) {
      // Boolean: only indices 0 and 1 are reachable
      return index <= 1 ? "inactive" : "unreachable";
    }

    if (this.scheduleSelectorEntity.startsWith("input_number.")) {
      const min = Number(selectorState.attributes?.min ?? 1);
      const max = Number(selectorState.attributes?.max ?? this.schedules.length);
      const scheduleNum = index + 1; // 1-based
      return scheduleNum >= min && scheduleNum <= max ? "inactive" : "unreachable";
    }

    return "inactive";
  }

  private _getStatusText(index: number, state: "active" | "inactive" | "unreachable"): string {
    const l = this.hass.language;

    if (state === "unreachable") {
      return localize("schedule.state_unreachable", l);
    }

    if (state === "inactive") {
      return localize("schedule.state_inactive", l);
    }

    // Active: show temperature info
    const schedule = this.schedules[index];
    const entityState = this.hass?.states?.[schedule.entity_id];
    if (!entityState) return localize("schedule.state_active", l);

    const isOn = entityState.state === "on";
    if (isOn) {
      const blockTemp = entityState.attributes?.temperature as number | undefined;
      if (blockTemp != null) {
        return localize("schedule.from_schedule", l, { temp: String(blockTemp), unit: tempUnit(this.hass) });
      }
      return localize("schedule.fallback", l, { temp: formatTemp(this.climateMode === "cool_only" ? this.comfortCool : this.comfortHeat, this.hass), unit: tempUnit(this.hass) });
    }

    return localize("schedule.eco_detail", l, { temp: formatTemp(this.climateMode === "cool_only" ? this.ecoCool : this.ecoHeat, this.hass), unit: tempUnit(this.hass) });
  }

  private _getScheduleEntities(): string[] {
    if (!this.hass?.states) return [];
    return Object.keys(this.hass.states).filter((id) =>
      id.startsWith("schedule.")
    );
  }

  private _getAvailableScheduleEntities(): string[] {
    const allScheduleEntities = this._getScheduleEntities();
    const usedIds = new Set(this.schedules.map((s) => s.entity_id));
    return allScheduleEntities.filter((id) => !usedIds.has(id));
  }

  private _onAddSchedule(e: Event) {
    const entityId = getSelectValue(e);
    if (!entityId) return;

    const newSchedules = [...this.schedules, { entity_id: entityId }];
    this.dispatchEvent(
      new CustomEvent("schedules-changed", {
        detail: { value: newSchedules },
        bubbles: true,
        composed: true,
      })
    );

    // Reset the select back to the placeholder
    requestAnimationFrame(() => {
      (e.target as HTMLElement & { value: string }).value = "";
    });
  }

  private _onRemoveSchedule(index: number) {
    const newSchedules = this.schedules.filter((_, i) => i !== index);
    this.dispatchEvent(
      new CustomEvent("schedules-changed", {
        detail: { value: newSchedules },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onMoveSchedule(index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= this.schedules.length) return;

    const newSchedules = [...this.schedules];
    const temp = newSchedules[index];
    newSchedules[index] = newSchedules[targetIndex];
    newSchedules[targetIndex] = temp;

    this.dispatchEvent(
      new CustomEvent("schedules-changed", {
        detail: { value: newSchedules },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onSelectorEntityChange(e: CustomEvent) {
    const value = e.detail?.value ?? "";
    this.dispatchEvent(
      new CustomEvent("schedule-selector-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onComfortHeatChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(21.0, this.hass), this.hass);
    this.dispatchEvent(new CustomEvent("comfort-heat-changed", {
      detail: { value: val }, bubbles: true, composed: true,
    }));
    if (this.comfortCool < val) {
      this.dispatchEvent(new CustomEvent("comfort-cool-changed", {
        detail: { value: val }, bubbles: true, composed: true,
      }));
    }
  }

  private _onComfortCoolChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(24.0, this.hass), this.hass);
    this.dispatchEvent(new CustomEvent("comfort-cool-changed", {
      detail: { value: val }, bubbles: true, composed: true,
    }));
    if (this.comfortHeat > val) {
      this.dispatchEvent(new CustomEvent("comfort-heat-changed", {
        detail: { value: val }, bubbles: true, composed: true,
      }));
    }
  }

  private _onEcoHeatChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(17.0, this.hass), this.hass);
    this.dispatchEvent(new CustomEvent("eco-heat-changed", {
      detail: { value: val }, bubbles: true, composed: true,
    }));
    if (this.ecoCool < val) {
      this.dispatchEvent(new CustomEvent("eco-cool-changed", {
        detail: { value: val }, bubbles: true, composed: true,
      }));
    }
  }

  private _onEcoCoolChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const val = toCelsius(parseFloat(target.value) || toDisplay(27.0, this.hass), this.hass);
    this.dispatchEvent(new CustomEvent("eco-cool-changed", {
      detail: { value: val }, bubbles: true, composed: true,
    }));
    if (this.ecoHeat > val) {
      this.dispatchEvent(new CustomEvent("eco-heat-changed", {
        detail: { value: val }, bubbles: true, composed: true,
      }));
    }
  }

}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-settings": RsScheduleSettings;
  }
}

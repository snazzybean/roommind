import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { HomeAssistant, ScheduleEntry } from "../types";
import { localize } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";

@customElement("rs-schedule-settings")
export class RsScheduleSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public schedules: ScheduleEntry[] = [];
  @property({ type: String }) public scheduleSelectorEntity = "";
  @property({ type: Number }) public activeScheduleIndex = 0;
  @property({ type: Number }) public comfortTemp = 21.0;
  @property({ type: Number }) public ecoTemp = 17.0;

  @property({ type: Boolean }) public editing = false;
  @property({ type: Boolean }) public useImperial = false;

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

      <div class="view-temps">
        ${localize("schedule.view_comfort", l, { temp: this.comfortTemp.toFixed(1), unit: tempUnit(this.useImperial) })}
        \u00A0\u00B7\u00A0
        ${localize("schedule.view_eco", l, { temp: this.ecoTemp.toFixed(1), unit: tempUnit(this.useImperial) })}
      </div>

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
      ${this._renderSelectorSection()}
      ${this._renderScheduleList(hasMultiple)}
      ${this._renderAddSchedule()}

      <div class="temp-inputs">
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${localize("schedule.comfort_label", l)}
            .suffix=${tempUnit(this.useImperial)}
            .value=${String(this.comfortTemp.toFixed(1))}
            step=${this.useImperial ? "1" : "0.5"}
            min=${this.useImperial ? "41" : "5"}
            max=${this.useImperial ? "95" : "35"}
            @change=${this._onComfortTempChange}
          ></ha-textfield>
        </div>
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${localize("schedule.eco_label", l)}
            .suffix=${tempUnit(this.useImperial)}
            .value=${String(this.ecoTemp.toFixed(1))}
            step=${this.useImperial ? "1" : "0.5"}
            min=${this.useImperial ? "41" : "5"}
            max=${this.useImperial ? "95" : "35"}
            @change=${this._onEcoTempChange}
          ></ha-textfield>
        </div>
      </div>
      <div class="fallback-hint">
        ${localize("schedule.comfort_hint", l)}
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

          <p style="margin-top: 12px"><strong>${localize("schedule.help_multi_title", l)}</strong></p>
          <p>${unsafeHTML(localize("schedule.help_multi", l))}</p>
        </div>
      </ha-expansion-panel>

    `;
  }

  private _renderSelectorSection() {
    const l = this.hass.language;
    const showSelector = this.schedules.length > 0;

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
          @selected=${this._onAddSchedule}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
          naturalMenuWidth
        >
          <ha-list-item value="">
            <ha-icon icon="mdi:plus" slot="graphic"></ha-icon>
            ${localize("schedule.add_schedule", l)}
          </ha-list-item>
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
        return localize("schedule.from_schedule", l, { temp: blockTemp.toFixed(1), unit: tempUnit(this.useImperial) });
      }
      return localize("schedule.fallback", l, { temp: this.comfortTemp.toFixed(1), unit: tempUnit(this.useImperial) });
    }

    return localize("schedule.eco_detail", l, { temp: this.ecoTemp.toFixed(1), unit: tempUnit(this.useImperial) });
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
    const target = e.target as HTMLElement & { value: string };
    const entityId = target.value;
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
      target.value = "";
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

  private _onComfortTempChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const displayVal = parseFloat(target.value) || (this.useImperial ? 70.0 : 21.0);
    this.dispatchEvent(
      new CustomEvent("comfort-temp-changed", {
        detail: {
          value: displayVal,
        },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onEcoTempChange(e: Event) {
    const target = e.target as HTMLElement & { value: string };
    const displayVal = parseFloat(target.value) || (this.useImperial ? 63.0 : 17.0);
    this.dispatchEvent(
      new CustomEvent("eco-temp-changed", {
        detail: {
          value: displayVal,
        },
        bubbles: true,
        composed: true,
      })
    );
  }

}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-settings": RsScheduleSettings;
  }
}

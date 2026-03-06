/**
 * rs-settings-general – General settings card: climate control, learning, vacation, presence, valve protection.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: Array }) public learningDisabledRooms: string[] = [];
  @property({ type: String }) public scheduleOffAction: "eco" | "off" = "eco";
  @property({ type: Boolean }) public vacationActive = false;
  @property({ type: Number }) public vacationTemp = 15;
  @property({ type: String }) public vacationUntil = "";
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ type: Array }) public presencePersons: string[] = [];
  @property({ type: String }) public presenceAwayAction: "eco" | "off" = "eco";
  @property({ type: Boolean }) public valveProtectionEnabled = false;
  @property({ type: Number }) public valveProtectionInterval = 7;

  @state() private _showLearningExceptions = false;

  private _fire(key: string, value: unknown) {
    this.dispatchEvent(new CustomEvent("setting-changed", {
      detail: { key, value },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    const l = this.hass.language;
    const configuredRooms = Object.entries(this.rooms)
      .map(([areaId]) => ({
        areaId,
        name: this.hass.areas?.[areaId]?.name ?? areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    const allRoomIds = Object.keys(this.rooms);
    const learningActive = allRoomIds.length === 0 || this.learningDisabledRooms.length < allRoomIds.length;
    const disabledCount = this.learningDisabledRooms.filter((id) => allRoomIds.includes(id)).length;

    return html`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:power"></ha-icon>
            <span>${localize("settings.general_title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          ${this.hass.floors && Object.keys(this.hass.floors).length > 0
            ? html`<div class="settings-section first">
                <div class="toggle-row">
                  <div class="toggle-text">
                    <span class="toggle-label">${localize("settings.group_by_floor", l)}</span>
                  </div>
                  <ha-switch
                    .checked=${this.groupByFloor}
                    @change=${(e: Event) => this._fire("groupByFloor", (e.target as HTMLInputElement).checked)}
                  ></ha-switch>
                </div>
              </div>`
            : nothing}
          <div class="settings-section ${this.hass.floors && Object.keys(this.hass.floors).length > 0 ? "" : "first"}">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.climate_control_active", l)}</span>
                <span class="toggle-hint">${localize("settings.climate_control_hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this.climateControlActive}
                @change=${(e: Event) => this._fire("climateControlActive", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
            <ha-select
              .label=${localize("schedule.off_action_label", l)}
              .value=${this.scheduleOffAction}
              fixedMenuPosition
              @selected=${(e: Event) => {
                const val = getSelectValue(e) as "eco" | "off";
                if (val && val !== this.scheduleOffAction) this._fire("scheduleOffAction", val);
              }}
              @closed=${(e: Event) => e.stopPropagation()}
              style="margin-top: 8px"
            >
              <ha-list-item value="eco">${localize("schedule.off_action_eco", l)}</ha-list-item>
              <ha-list-item value="off">${localize("schedule.off_action_off", l)}</ha-list-item>
            </ha-select>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.learning_title", l)}</span>
                <span class="toggle-hint">${localize("settings.learning_hint", l)}</span>
              </div>
              <ha-switch
                .checked=${learningActive}
                @change=${(e: Event) => {
                  const active = (e.target as HTMLInputElement).checked;
                  this._fire("learningDisabledRooms", active ? [] : Object.keys(this.rooms));
                  if (!active) this._showLearningExceptions = false;
                }}
              ></ha-switch>
            </div>
            ${learningActive && configuredRooms.length > 0
              ? html`
                  <button class="exceptions-link" @click=${() => { this._showLearningExceptions = !this._showLearningExceptions; }}>
                    <span>${disabledCount > 0
                      ? `${disabledCount} ${localize(disabledCount === 1 ? "settings.learning_room_paused" : "settings.learning_rooms_paused", l)}`
                      : localize("settings.learning_exceptions", l)}</span>
                    <ha-icon
                      icon=${this._showLearningExceptions ? "mdi:chevron-up" : "mdi:chevron-down"}
                      style="--mdc-icon-size: 16px"
                    ></ha-icon>
                  </button>
                  ${this._showLearningExceptions
                    ? html`
                        <div class="room-toggles">
                          ${configuredRooms.map(
                            (room) => html`
                              <div class="room-toggle-row">
                                <span class="room-toggle-name">${room.name}</span>
                                <ha-switch
                                  .checked=${!this.learningDisabledRooms.includes(room.areaId)}
                                  @change=${(e: Event) => {
                                    const disabled = !(e.target as HTMLInputElement).checked;
                                    const set = new Set(this.learningDisabledRooms);
                                    if (disabled) set.add(room.areaId); else set.delete(room.areaId);
                                    this._fire("learningDisabledRooms", [...set]);
                                  }}
                                ></ha-switch>
                              </div>
                            `
                          )}
                        </div>
                      `
                    : nothing}
              `
              : nothing}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:airplane" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("vacation.title", l)}
                </span>
                <span class="toggle-hint">${localize("vacation.hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this.vacationActive}
                @change=${(e: Event) => {
                  const active = (e.target as HTMLInputElement).checked;
                  this._fire("vacationActive", active);
                  if (!active) this._fire("vacationUntil", "");
                }}
              ></ha-switch>
            </div>
            ${this.vacationActive
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${this.vacationUntil}
                        .label=${localize("vacation.end_date", l)}
                        type="datetime-local"
                        @change=${(e: Event) => this._fire("vacationUntil", (e.target as HTMLInputElement).value)}
                      ></ha-textfield>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(toDisplay(this.vacationTemp, this.hass))}
                        .label=${localize("vacation.setback_temp", l)}
                        .suffix=${tempUnit(this.hass)}
                        type="number"
                        step=${tempStep(this.hass)}
                        min=${tempRange(5, 25, this.hass).min}
                        max=${tempRange(5, 25, this.hass).max}
                        @change=${(e: Event) => {
                          const v = parseFloat((e.target as HTMLInputElement).value);
                          if (!isNaN(v)) this._fire("vacationTemp", toCelsius(v, this.hass));
                        }}
                      ></ha-textfield>
                    </div>
                  </div>
                `
              : nothing}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:home-account" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("presence.title", l)}
                </span>
                <span class="toggle-hint">${localize("presence.hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this.presenceEnabled}
                @change=${(e: Event) => this._fire("presenceEnabled", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
            ${this.presenceEnabled
              ? html`
                  <div class="room-toggles" style="gap: 8px">
                    <span class="field-hint" style="margin-bottom: 4px">${localize("presence.hint_detail", l)}</span>
                    ${this.presencePersons.length > 0 ? html`
                      <div class="presence-person-list">
                        ${this.presencePersons.map((pid) => {
                          const name = this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join(".");
                          return html`
                            <div class="presence-person-row">
                              <ha-icon icon="mdi:account" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                              <span class="presence-person-name">${name}</span>
                              <ha-icon-button
                                .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                                @click=${() => this._fire("presencePersons", this.presencePersons.filter((p) => p !== pid))}
                              ></ha-icon-button>
                            </div>
                          `;
                        })}
                      </div>
                    ` : nothing}
                    <ha-entity-picker
                      .hass=${this.hass}
                      .includeDomains=${["person", "device_tracker", "binary_sensor", "input_boolean"]}
                      .entityFilter=${(entity: { entity_id: string }) => !this.presencePersons.includes(entity.entity_id)}
                      .label=${localize("presence.add_entity", l)}
                      @value-changed=${(e: CustomEvent) => {
                        const val = e.detail?.value;
                        if (val && !this.presencePersons.includes(val)) {
                          this._fire("presencePersons", [...this.presencePersons, val]);
                        }
                        const picker = e.target as HTMLElement & { value: string };
                        picker.value = "";
                      }}
                    ></ha-entity-picker>
                    <ha-select
                      .label=${localize("presence.away_action_label", l)}
                      .value=${this.presenceAwayAction}
                      fixedMenuPosition
                      @selected=${(e: Event) => {
                        const val = getSelectValue(e) as "eco" | "off";
                        if (val && val !== this.presenceAwayAction) this._fire("presenceAwayAction", val);
                      }}
                      @closed=${(e: Event) => e.stopPropagation()}
                      style="margin-top: 8px"
                    >
                      <ha-list-item value="eco">${localize("presence.away_action_eco", l)}</ha-list-item>
                      <ha-list-item value="off">${localize("presence.away_action_off", l)}</ha-list-item>
                    </ha-select>
                  </div>
                `
              : nothing}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-refresh" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("valve_protection.title", l)}
                </span>
                <span class="toggle-hint">${localize("valve_protection.hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this.valveProtectionEnabled}
                @change=${(e: Event) => this._fire("valveProtectionEnabled", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
            ${this.valveProtectionEnabled
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.valveProtectionInterval)}
                        .label=${localize("valve_protection.interval_label", l)}
                        .suffix=${localize("valve_protection.interval_suffix", l)}
                        type="number"
                        step="1"
                        min="1"
                        max="90"
                        @change=${(e: Event) => {
                          const v = parseInt((e.target as HTMLInputElement).value, 10);
                          if (!isNaN(v) && v >= 1 && v <= 90) this._fire("valveProtectionInterval", v);
                        }}
                      ></ha-textfield>
                      <span class="field-hint">${localize("valve_protection.interval_hint", l)}</span>
                    </div>
                  </div>
                `
              : nothing}
          </div>
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .exceptions-link {
      display: inline-flex; align-items: center; gap: 4px;
      background: none; border: none; padding: 8px 0 0; margin: 0;
      cursor: pointer; font-size: 13px; color: var(--primary-color); font-family: inherit;
    }
    .exceptions-link:hover { text-decoration: underline; }

    .room-toggles { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; }
    .room-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; }
    .room-toggle-name { font-size: 14px; color: var(--primary-text-color); }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    .presence-person-list { display: flex; flex-direction: column; gap: 2px; }
    .presence-person-row {
      display: flex; align-items: center; gap: 10px;
      padding: 4px 8px 4px 12px; border-radius: 8px; background: rgba(0, 0, 0, 0.04);
    }
    .presence-person-name { flex: 1; font-size: 14px; font-weight: 500; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-general": RsSettingsGeneral;
  }
}

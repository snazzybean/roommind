/**
 * rs-settings – Global RoomMind settings page.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, GlobalSettings, HassEntity, RoomConfig, NotificationTarget } from "../types";
import { localize } from "../utils/localize";
import { fireSaveStatus, getSelectValue } from "../utils/events";
import { formatTemp, tempUnit, toDisplay, toCelsius, tempStep, tempRange, toDisplayDelta } from "../utils/temperature";

@customElement("rs-settings")
export class RsSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _groupByFloor = false;
  @state() private _climateControlActive = true;
  @state() private _learningDisabledRooms: string[] = [];
  @state() private _showLearningExceptions = false;
  @state() private _outdoorTempSensor = "";
  @state() private _outdoorHumiditySensor = "";
  @state() private _outdoorCoolingMin = 16;
  @state() private _outdoorHeatingMax = 22;
  @state() private _controlMode: "mpc" | "bangbang" = "mpc";
  @state() private _comfortWeight = 70;
  @state() private _weatherEntity = "";
  @state() private _predictionEnabled = true;
  @state() private _vacationActive = false;
  @state() private _vacationTemp = 15;
  @state() private _vacationUntil = "";
  @state() private _presenceEnabled = false;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _scheduleOffAction: "eco" | "off" = "eco";
  @state() private _valveProtectionEnabled = false;
  @state() private _valveProtectionInterval = 7;
  @state() private _moldDetectionEnabled = false;
  @state() private _moldHumidityThreshold = 70;
  @state() private _moldSustainedMinutes = 30;
  @state() private _moldNotificationCooldown = 60;
  @state() private _moldNotificationsEnabled = true;
  @state() private _moldNotificationTargets: NotificationTarget[] = [];
  @state() private _moldPreventionEnabled = false;
  @state() private _moldPreventionIntensity: "light" | "medium" | "strong" = "medium";
  @state() private _moldPreventionNotify = false;
  @state() private _resetSelectedRoom = "";
  @state() private _loaded = false;

  private _saveDebounce?: ReturnType<typeof setTimeout>;

  static styles = css`
    :host {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .left-column,
    .right-column {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 0;
      font-size: 16px;
      font-weight: 500;
    }

    .header-title {
      display: flex;
      align-items: center;
      gap: 8px;
      --mdc-icon-size: 20px;
    }

    .card-content {
      padding: 8px 16px 16px;
    }

    .settings-section {
      padding: 16px 0;
      border-top: 1px solid var(--divider-color);
    }

    .settings-section:first-child,
    .settings-section.first {
      border-top: none;
    }

    .toggle-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }

    .toggle-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .toggle-label {
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .toggle-hint {
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.4;
    }

    .exceptions-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px 0 0;
      margin: 0;
      cursor: pointer;
      font-size: 13px;
      color: var(--primary-color);
      font-family: inherit;
    }

    .exceptions-link:hover {
      text-decoration: underline;
    }

    .presence-person-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-person-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 8px 4px 12px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-person-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }

    .room-toggles {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 12px;
    }

    .room-toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 0;
    }

    .room-toggle-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .sensor-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .current-value {
      margin-top: 8px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .current-value.muted {
      color: var(--secondary-text-color);
    }

    .loading {
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .hint {
      color: var(--secondary-text-color);
      font-size: 13px;
      margin: 0 0 12px;
    }

    .section-label {
      display: block;
      margin-bottom: 8px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .threshold-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .threshold-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .threshold-field ha-textfield {
      width: 100%;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .radio-group {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .radio-option {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
    }

    .slider-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .slider-row input[type="range"] {
      flex: 1;
      accent-color: var(--primary-color);
    }

    .slider-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .reset-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }

    .reset-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .reset-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border: 1px solid var(--error-color, #d32f2f);
      border-radius: 8px;
      background: transparent;
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      font-family: inherit;
      cursor: pointer;
      transition: background 0.15s;
      --mdc-icon-size: 16px;
      white-space: nowrap;
    }

    .reset-btn:hover {
      background: rgba(211, 47, 47, 0.08);
    }

    .reset-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .reset-btn:disabled:hover {
      background: transparent;
    }

    .reset-room-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .reset-room-row ha-select {
      flex: 1;
    }

    .mold-target-card {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 8px 8px 8px 12px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.04);
    }

    .mold-target-header {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .mold-target-header span {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }

    .mold-target-detail {
      display: flex;
      gap: 8px;
      align-items: center;
      padding-left: 26px;
    }

    .mold-target-detail ha-entity-picker {
      flex: 1;
    }

    .mold-target-detail ha-select {
      min-width: 120px;
    }

    @media (max-width: 600px) {
      :host {
        grid-template-columns: 1fr;
      }

      .sensor-grid,
      .threshold-grid {
        grid-template-columns: 1fr;
      }

      .mold-target-detail {
        flex-direction: column;
        padding-left: 0;
      }

      .reset-row {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
      }
    }
  `;

  connectedCallback() {
    super.connectedCallback();
    this._loadSettings();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
  }

  private async _loadSettings() {
    try {
      const result = await this.hass.callWS<{ settings: GlobalSettings }>({
        type: "roommind/settings/get",
      });
      this._groupByFloor = result.settings.group_by_floor ?? false;
      this._climateControlActive = result.settings.climate_control_active ?? true;
      this._learningDisabledRooms = result.settings.learning_disabled_rooms ?? [];
      this._outdoorTempSensor = result.settings.outdoor_temp_sensor ?? "";
      this._outdoorHumiditySensor = result.settings.outdoor_humidity_sensor ?? "";
      this._outdoorCoolingMin = result.settings.outdoor_cooling_min ?? 16;
      this._outdoorHeatingMax = result.settings.outdoor_heating_max ?? 22;
      this._controlMode = result.settings.control_mode ?? "mpc";
      this._comfortWeight = result.settings.comfort_weight ?? 70;
      this._weatherEntity = result.settings.weather_entity ?? "";
      this._predictionEnabled = result.settings.prediction_enabled ?? true;
      const vUntil = result.settings.vacation_until;
      this._vacationActive = !!(vUntil && vUntil > Date.now() / 1000);
      this._vacationTemp = result.settings.vacation_temp ?? 15;
      if (vUntil && vUntil > Date.now() / 1000) {
        this._vacationUntil = this._tsToDatetimeLocal(vUntil);
      }
      this._presenceEnabled = result.settings.presence_enabled ?? false;
      this._presencePersons = result.settings.presence_persons ?? [];
      this._presenceAwayAction = result.settings.presence_away_action ?? "eco";
      this._scheduleOffAction = result.settings.schedule_off_action ?? "eco";
      this._valveProtectionEnabled = result.settings.valve_protection_enabled ?? false;
      this._valveProtectionInterval = result.settings.valve_protection_interval_days ?? 7;
      this._moldDetectionEnabled = result.settings.mold_detection_enabled ?? false;
      this._moldHumidityThreshold = result.settings.mold_humidity_threshold ?? 70;
      this._moldSustainedMinutes = result.settings.mold_sustained_minutes ?? 30;
      this._moldNotificationCooldown = result.settings.mold_notification_cooldown ?? 60;
      this._moldNotificationsEnabled = result.settings.mold_notifications_enabled ?? true;
      this._moldNotificationTargets = result.settings.mold_notification_targets ?? [];
      this._moldPreventionEnabled = result.settings.mold_prevention_enabled ?? false;
      this._moldPreventionIntensity = result.settings.mold_prevention_intensity ?? "medium";
      this._moldPreventionNotify = result.settings.mold_prevention_notify_enabled ?? false;
    } catch (err) {
      console.debug("[RoomMind] loadSettings:", err);
    } finally {
      this._loaded = true;
    }
  }

  protected render() {
    if (!this._loaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }
    const l = this.hass.language;

    const outdoorTemp = this._outdoorTempSensor
      ? this._getSensorValue(this._outdoorTempSensor)
      : null;

    const outdoorHumidity = this._outdoorHumiditySensor
      ? this._getSensorValue(this._outdoorHumiditySensor)
      : null;

    const configuredRooms = Object.entries(this.rooms)
      .map(([areaId]) => ({
        areaId,
        name: this.hass.areas?.[areaId]?.name ?? areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    const allRoomIds = Object.keys(this.rooms);
    const learningActive = allRoomIds.length === 0 || this._learningDisabledRooms.length < allRoomIds.length;
    const disabledCount = this._learningDisabledRooms.filter((id) => allRoomIds.includes(id)).length;

    return html`
      <div class="left-column">
      <!-- Card: General -->
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
                    .checked=${this._groupByFloor}
                    @change=${this._onGroupByFloorChanged}
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
                .checked=${this._climateControlActive}
                @change=${this._onClimateControlChanged}
              ></ha-switch>
            </div>
            <ha-select
              .label=${localize("schedule.off_action_label", l)}
              .value=${this._scheduleOffAction}
              .options=${[
                { value: "eco", label: localize("schedule.off_action_eco", l) },
                { value: "off", label: localize("schedule.off_action_off", l) },
              ]}
              fixedMenuPosition
              @selected=${this._onScheduleOffActionChanged}
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
                @change=${this._onLearningToggled}
              ></ha-switch>
            </div>
            ${learningActive && configuredRooms.length > 0
              ? html`
                  <button class="exceptions-link" @click=${this._toggleLearningExceptions}>
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
                                  .checked=${!this._learningDisabledRooms.includes(room.areaId)}
                                  @change=${(e: Event) => this._onLearningRoomToggled(room.areaId, !(e.target as HTMLInputElement).checked)}
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
                .checked=${this._vacationActive}
                @change=${this._onVacationToggled}
              ></ha-switch>
            </div>
            ${this._vacationActive
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${this._vacationUntil}
                        .label=${localize("vacation.end_date", l)}
                        type="datetime-local"
                        @change=${this._onVacationUntilChanged}
                      ></ha-textfield>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(toDisplay(this._vacationTemp, this.hass))}
                        .label=${localize("vacation.setback_temp", l)}
                        .suffix=${tempUnit(this.hass)}
                        type="number"
                        step=${tempStep(this.hass)}
                        min=${tempRange(5, 25, this.hass).min}
                        max=${tempRange(5, 25, this.hass).max}
                        @change=${this._onVacationTempChanged}
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
                .checked=${this._presenceEnabled}
                @change=${this._onPresenceToggled}
              ></ha-switch>
            </div>
            ${this._presenceEnabled
              ? html`
                  <div class="room-toggles" style="gap: 8px">
                    <span class="field-hint" style="margin-bottom: 4px">${localize("presence.hint_detail", l)}</span>
                    ${this._presencePersons.length > 0 ? html`
                      <div class="presence-person-list">
                        ${this._presencePersons.map((pid) => {
                          const name = this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join(".");
                          return html`
                            <div class="presence-person-row">
                              <ha-icon icon="mdi:account" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                              <span class="presence-person-name">${name}</span>
                              <ha-icon-button
                                .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                                @click=${() => {
                                  this._presencePersons = this._presencePersons.filter((p) => p !== pid);
                                  this._autoSave();
                                }}
                              ></ha-icon-button>
                            </div>
                          `;
                        })}
                      </div>
                    ` : nothing}
                    <ha-entity-picker
                      .hass=${this.hass}
                      .includeDomains=${["person", "device_tracker", "binary_sensor", "input_boolean"]}
                      .entityFilter=${(entity: { entity_id: string }) => !this._presencePersons.includes(entity.entity_id)}
                      .label=${localize("presence.add_entity", l)}
                      @value-changed=${(e: CustomEvent) => {
                        const val = e.detail?.value;
                        if (val && !this._presencePersons.includes(val)) {
                          this._presencePersons = [...this._presencePersons, val];
                          this._autoSave();
                        }
                        const picker = e.target as HTMLElement & { value: string };
                        picker.value = "";
                      }}
                    ></ha-entity-picker>
                    <ha-select
                      .label=${localize("presence.away_action_label", l)}
                      .value=${this._presenceAwayAction}
                      .options=${[
                        { value: "eco", label: localize("presence.away_action_eco", l) },
                        { value: "off", label: localize("presence.away_action_off", l) },
                      ]}
                      fixedMenuPosition
                      @selected=${this._onPresenceAwayActionChanged}
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
                .checked=${this._valveProtectionEnabled}
                @change=${this._onValveProtectionToggled}
              ></ha-switch>
            </div>
            ${this._valveProtectionEnabled
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._valveProtectionInterval)}
                        .label=${localize("valve_protection.interval_label", l)}
                        .suffix=${localize("valve_protection.interval_suffix", l)}
                        type="number"
                        step="1"
                        min="1"
                        max="90"
                        @change=${this._onValveProtectionIntervalChanged}
                      ></ha-textfield>
                      <span class="field-hint">${localize("valve_protection.interval_hint", l)}</span>
                    </div>
                  </div>
                `
              : nothing}
          </div>
        </div>
      </ha-card>

      <!-- Card 2: Control -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:tune-variant"></ha-icon>
            <span>${localize("settings.control_title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <p class="hint">${localize("settings.control_mode_hint", l)}</p>
            <div class="radio-group">
              <label class="radio-option" @click=${() => this._setControlMode("mpc")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this._controlMode === "mpc"}
                ></ha-radio>
                <span>${localize("settings.control_mode_mpc", l)}</span>
              </label>
              <label class="radio-option" @click=${() => this._setControlMode("bangbang")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this._controlMode === "bangbang"}
                ></ha-radio>
                <span>${localize("settings.control_mode_simple", l)}</span>
              </label>
            </div>
          </div>

          <div class="settings-section">
            <label class="section-label">${localize("settings.comfort_weight", l)}</label>
            <div class="slider-row">
              <span class="slider-label">${localize("settings.comfort_weight_efficiency", l)}</span>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                .value=${String(this._comfortWeight)}
                @change=${this._onComfortWeightChanged}
              />
              <span class="slider-label">${localize("settings.comfort_weight_comfort", l)}</span>
            </div>
          </div>

          <div class="settings-section">
            <p class="hint">${localize("settings.smart_control_hint", l)}</p>
            <div class="threshold-grid">
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this._outdoorCoolingMin, this.hass))}
                  .label=${localize("settings.outdoor_cooling_min", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(-10, 40, this.hass).min}
                  max=${tempRange(-10, 40, this.hass).max}
                  @change=${this._onOutdoorCoolingMinChanged}
                ></ha-textfield>
                <span class="field-hint">${localize("settings.outdoor_cooling_min_hint", l)}</span>
              </div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this._outdoorHeatingMax, this.hass))}
                  .label=${localize("settings.outdoor_heating_max", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(0, 40, this.hass).min}
                  max=${tempRange(0, 40, this.hass).max}
                  @change=${this._onOutdoorHeatingMaxChanged}
                ></ha-textfield>
                <span class="field-hint">${localize("settings.outdoor_heating_max_hint", l)}</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.prediction_enabled", l)}</span>
                <span class="toggle-hint">${localize("settings.prediction_enabled_hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this._predictionEnabled}
                @change=${this._onPredictionEnabledChanged}
              ></ha-switch>
            </div>
          </div>
        </div>
      </ha-card>
      </div>

      <div class="right-column">
      <!-- Card 1: Sensors & Data Sources -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:thermometer"></ha-icon>
            <span>${localize("settings.sensors_title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <div class="sensor-grid">
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this._outdoorTempSensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterTemperature}
                  .label=${localize("settings.outdoor_sensor_label", l)}
                  allow-custom-entity
                  @value-changed=${this._onOutdoorTempChanged}
                ></ha-entity-picker>
                ${outdoorTemp !== null
                  ? html`<div class="current-value">
                      ${localize("settings.outdoor_current", l, { temp: outdoorTemp.toFixed(1), unit: tempUnit(this.hass) })}
                    </div>`
                  : this._outdoorTempSensor
                    ? html`<div class="current-value muted">
                        ${localize("settings.outdoor_waiting", l)}
                      </div>`
                    : nothing}
              </div>
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this._outdoorHumiditySensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterHumidity}
                  .label=${localize("settings.outdoor_humidity_label", l)}
                  allow-custom-entity
                  @value-changed=${this._onOutdoorHumidityChanged}
                ></ha-entity-picker>
                ${outdoorHumidity !== null
                  ? html`<div class="current-value">
                      ${localize("settings.outdoor_humidity_current", l, { value: String(outdoorHumidity) })}
                    </div>`
                  : this._outdoorHumiditySensor
                    ? html`<div class="current-value muted">
                        ${localize("settings.outdoor_waiting", l)}
                      </div>`
                    : nothing}
              </div>
            </div>
          </div>

          <div class="settings-section">
            <ha-entity-picker
              .hass=${this.hass}
              .value=${this._weatherEntity}
              .includeDomains=${["weather"]}
              .label=${localize("settings.weather_entity", l)}
              allow-custom-entity
              @value-changed=${this._onWeatherEntityChanged}
            ></ha-entity-picker>
            <span class="field-hint">${localize("settings.weather_entity_hint", l)}</span>
          </div>
        </div>
      </ha-card>

      <!-- Card: Mold Risk -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:water-alert"></ha-icon>
            <span>${localize("mold.title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <!-- Detection section -->
          <div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:bell-alert" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("mold.detection", l)}
                </span>
                <span class="toggle-hint">${localize("mold.detection_desc", l)}</span>
              </div>
              <ha-switch
                .checked=${this._moldDetectionEnabled}
                @change=${this._onMoldDetectionToggled}
              ></ha-switch>
            </div>
            ${this._moldDetectionEnabled
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldHumidityThreshold)}
                        .label=${localize("mold.threshold", l)}
                        .suffix=${"%"}
                        type="number"
                        step="1"
                        min="50"
                        max="90"
                        @change=${this._onMoldThresholdChanged}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.threshold_hint", l)}</span>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldSustainedMinutes)}
                        .label=${localize("mold.sustained", l)}
                        .suffix=${"min"}
                        type="number"
                        step="5"
                        min="5"
                        max="120"
                        @change=${this._onMoldSustainedChanged}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.sustained_hint", l)}</span>
                    </div>
                  </div>
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldNotificationCooldown)}
                        .label=${localize("mold.cooldown", l)}
                        .suffix=${"min"}
                        type="number"
                        step="5"
                        min="10"
                        max="1440"
                        @change=${this._onMoldCooldownChanged}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.cooldown_hint", l)}</span>
                    </div>
                  </div>
                `
              : nothing}
          </div>

          <!-- Prevention section -->
          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-check" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("mold.prevention", l)}
                </span>
                <span class="toggle-hint">${localize("mold.prevention_desc", l)}</span>
              </div>
              <ha-switch
                .checked=${this._moldPreventionEnabled}
                @change=${this._onMoldPreventionToggled}
              ></ha-switch>
            </div>
            ${this._moldPreventionEnabled
              ? html`
                  <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 4px;">
                    <ha-select
                      style="width: 100%;"
                      .value=${this._moldPreventionIntensity}
                      .label=${localize("mold.intensity", l)}
                      .options=${[
                        { value: "light", label: localize("mold.intensity_light", l, { delta: String(toDisplayDelta(1, this.hass)), unit: tempUnit(this.hass) }) },
                        { value: "medium", label: localize("mold.intensity_medium", l, { delta: String(toDisplayDelta(2, this.hass)), unit: tempUnit(this.hass) }) },
                        { value: "strong", label: localize("mold.intensity_strong", l, { delta: String(toDisplayDelta(3, this.hass)), unit: tempUnit(this.hass) }) },
                      ]}
                      @selected=${this._onMoldIntensityChanged}
                      @closed=${(e: Event) => e.stopPropagation()}
                    >
                      <ha-list-item value="light">${localize("mold.intensity_light", l, { delta: String(toDisplayDelta(1, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                      <ha-list-item value="medium">${localize("mold.intensity_medium", l, { delta: String(toDisplayDelta(2, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                      <ha-list-item value="strong">${localize("mold.intensity_strong", l, { delta: String(toDisplayDelta(3, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                    </ha-select>
                    <span class="field-hint">${localize("mold.intensity_hint", l)}</span>
                  </div>
                `
              : nothing}
          </div>

          <!-- Notifications section (visible when detection OR prevention active) -->
          ${this._moldDetectionEnabled || this._moldPreventionEnabled
            ? html`
                <div class="settings-section">
                  <div class="toggle-row">
                    <div class="toggle-text">
                      <span class="toggle-label">
                        <ha-icon icon="mdi:bell-outline" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                        ${localize("mold.notifications_enabled", l)}
                        <ha-icon
                          icon="mdi:alert-circle-outline"
                          style="--mdc-icon-size: 14px; vertical-align: middle; margin-left: 4px; color: var(--warning-color, #ffa600)"
                          title="${localize("mold.notifications_beta_hint", l)}"
                        ></ha-icon>
                      </span>
                      <span class="toggle-hint">${localize("mold.notifications_enabled_hint", l)}</span>
                    </div>
                    <ha-switch
                      .checked=${this._moldNotificationsEnabled}
                      @change=${this._onMoldNotificationsEnabledToggled}
                    ></ha-switch>
                  </div>
                  ${this._moldNotificationsEnabled
                    ? html`
                  <p class="hint" style="margin-top: 12px">${localize("mold.notifications_desc", l)}</p>

                  <!-- Target list -->
                  <div class="presence-person-list">
                    ${this._moldNotificationTargets.map((t, idx) => {
                      const name = t.entity_id
                        ? (this.hass.states[t.entity_id]?.attributes?.friendly_name
                          ?? t.entity_id.replace("notify.", ""))
                        : localize("mold.target_unnamed", l);
                      return html`
                        <div class="mold-target-card">
                          <div class="mold-target-header">
                            <ha-icon icon="mdi:bell" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                            <span>${name}</span>
                            <ha-icon-button
                              .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                              @click=${() => this._removeMoldTarget(idx)}
                            ></ha-icon-button>
                          </div>
                          <div class="mold-target-detail">
                            <ha-entity-picker
                              .hass=${this.hass}
                              .value=${t.person_entity}
                              .includeDomains=${["person"]}
                              .label=${localize("mold.target_person", l)}
                              allow-custom-entity
                              @value-changed=${(e: CustomEvent) => this._onMoldTargetPersonChanged(idx, e)}
                            ></ha-entity-picker>
                            <ha-select
                              .value=${t.notify_when}
                              .options=${[
                                { value: "always", label: localize("mold.target_when_always", l) },
                                { value: "home_only", label: localize("mold.target_when_home", l) },
                              ]}
                              @selected=${(e: Event) => this._onMoldTargetWhenChanged(idx, e)}
                              @closed=${(e: Event) => e.stopPropagation()}
                            >
                              <ha-list-item value="always">${localize("mold.target_when_always", l)}</ha-list-item>
                              <ha-list-item value="home_only">${localize("mold.target_when_home", l)}</ha-list-item>
                            </ha-select>
                          </div>
                        </div>
                      `;
                    })}
                  </div>

                  <!-- Add target picker -->
                  <div style="margin-top: 8px">
                    <ha-entity-picker
                      .hass=${this.hass}
                      .value=${""}
                      .includeDomains=${["notify"]}
                      .label=${localize("mold.add_target_label", l)}
                      allow-custom-entity
                      @value-changed=${this._onMoldTargetAdded}
                    ></ha-entity-picker>
                    <span class="field-hint">${localize("mold.add_target_hint", l)}</span>
                  </div>

                  <!-- Prevention notify toggle -->
                  ${this._moldPreventionEnabled
                    ? html`
                        <div class="toggle-row" style="margin-top: 12px">
                          <div class="toggle-text">
                            <span class="toggle-label">${localize("mold.prevention_notify", l)}</span>
                            <span class="toggle-hint">${localize("mold.prevention_notify_hint", l)}</span>
                          </div>
                          <ha-switch
                            .checked=${this._moldPreventionNotify}
                            @change=${this._onMoldPreventionNotifyToggled}
                          ></ha-switch>
                        </div>
                      `
                    : nothing}
                    `
                    : nothing}
                </div>
              `
            : nothing}
        </div>
      </ha-card>

      <!-- Card: Reset Thermal Data -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:restart"></ha-icon>
            <span>${localize("settings.reset_title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <p class="hint">${localize("settings.reset_hint", l)}</p>

          <div class="settings-section first">
            <div class="reset-row">
              <div class="reset-text">
                <span class="toggle-label">${localize("settings.reset_all_label", l)}</span>
                <span class="toggle-hint">${localize("settings.reset_all_hint", l)}</span>
              </div>
              <button class="reset-btn" @click=${this._resetAllModels}>
                <ha-icon icon="mdi:restart-alert"></ha-icon>
                ${localize("settings.reset_all_btn", l)}
              </button>
            </div>
          </div>

          <div class="settings-section">
            <div class="reset-text" style="margin-bottom: 12px">
              <span class="toggle-label">${localize("settings.reset_room_label", l)}</span>
              <span class="toggle-hint">${localize("settings.reset_room_hint", l)}</span>
            </div>
            ${configuredRooms.length > 0
              ? html`
                  <div class="reset-room-row">
                    <ha-select
                      .value=${this._resetSelectedRoom}
                      .label=${localize("settings.reset_room_select", l)}
                      .options=${configuredRooms.map((room) => ({ value: room.areaId, label: room.name }))}
                      @selected=${this._onResetRoomSelected}
                      @closed=${(e: Event) => e.stopPropagation()}
                    >
                      ${configuredRooms.map(
                        (room) => html`<ha-list-item .value=${room.areaId}>${room.name}</ha-list-item>`
                      )}
                    </ha-select>
                    ${this._resetSelectedRoom
                      ? html`<ha-icon-button
                          .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                          @click=${this._clearResetSelection}
                        ></ha-icon-button>`
                      : nothing}
                    <button
                      class="reset-btn"
                      ?disabled=${!this._resetSelectedRoom}
                      @click=${() => this._resetSelectedRoom && this._resetRoomModel(this._resetSelectedRoom)}
                    >
                      <ha-icon icon="mdi:restart"></ha-icon>
                      ${localize("settings.reset_btn", l)}
                    </button>
                  </div>
                `
              : html`<p class="hint">${localize("settings.reset_no_rooms", l)}</p>`}
          </div>
        </div>
      </ha-card>
      </div>
    `;
  }

  private _filterTemperature = (entity: HassEntity): boolean => {
    return entity.attributes?.device_class === "temperature";
  };

  private _filterHumidity = (entity: HassEntity): boolean => {
    return entity.attributes?.device_class === "humidity";
  };

  private _getSensorValue(entityId: string): number | null {
    const state = this.hass.states[entityId];
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      return null;
    }
    const val = parseFloat(state.state);
    return isNaN(val) ? null : Math.round(val * 10) / 10;
  }


  private _tsToDatetimeLocal(ts: number): string {
    const d = new Date(ts * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  private _onVacationToggled(e: Event) {
    this._vacationActive = (e.target as HTMLInputElement).checked;
    if (!this._vacationActive) {
      this._vacationUntil = "";
    }
    this._autoSave();
  }

  private _onVacationUntilChanged(e: Event) {
    this._vacationUntil = (e.target as HTMLInputElement).value;
    this._autoSave();
  }

  private _onVacationTempChanged(e: Event) {
    const value = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(value)) {
      this._vacationTemp = toCelsius(value, this.hass);
      this._autoSave();
    }
  }

  private _onPresenceToggled(e: Event) {
    this._presenceEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onPresenceAwayActionChanged(e: Event) {
    const val = getSelectValue(e) as "eco" | "off";
    if (val && val !== this._presenceAwayAction) {
      this._presenceAwayAction = val;
      this._autoSave();
    }
  }

  private _onScheduleOffActionChanged(e: Event) {
    const val = getSelectValue(e) as "eco" | "off";
    if (val && val !== this._scheduleOffAction) {
      this._scheduleOffAction = val;
      this._autoSave();
    }
  }

  private _onValveProtectionToggled(e: Event) {
    this._valveProtectionEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onValveProtectionIntervalChanged(e: Event) {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (!isNaN(value) && value >= 1 && value <= 90 && value !== this._valveProtectionInterval) {
      this._valveProtectionInterval = value;
      this._autoSave();
    }
  }

  private _onLearningToggled(e: Event) {
    const active = (e.target as HTMLInputElement).checked;
    if (active) {
      this._learningDisabledRooms = [];
    } else {
      this._learningDisabledRooms = Object.keys(this.rooms);
      this._showLearningExceptions = false;
    }
    this._autoSave();
  }

  private _toggleLearningExceptions() {
    this._showLearningExceptions = !this._showLearningExceptions;
  }

  private _setControlMode(mode: "mpc" | "bangbang") {
    if (this._controlMode === mode) return;
    this._controlMode = mode;
    this._autoSave();
  }

  private _onGroupByFloorChanged(e: Event) {
    this._groupByFloor = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onClimateControlChanged(e: Event) {
    this._climateControlActive = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onLearningRoomToggled(areaId: string, checked: boolean) {
    const set = new Set(this._learningDisabledRooms);
    if (checked) {
      set.add(areaId);
    } else {
      set.delete(areaId);
    }
    this._learningDisabledRooms = [...set];
    this._autoSave();
  }

  private _onOutdoorTempChanged(e: CustomEvent) {
    const value = (e.detail?.value as string) ?? "";
    if (value === this._outdoorTempSensor) return;
    this._outdoorTempSensor = value;
    this._autoSave();
  }

  private _onOutdoorHumidityChanged(e: CustomEvent) {
    const value = (e.detail?.value as string) ?? "";
    if (value === this._outdoorHumiditySensor) return;
    this._outdoorHumiditySensor = value;
    this._autoSave();
  }

  private _onOutdoorCoolingMinChanged(e: Event) {
    const value = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(value)) {
      const celsius = toCelsius(value, this.hass);
      if (celsius !== this._outdoorCoolingMin) {
        this._outdoorCoolingMin = celsius;
        this._autoSave();
      }
    }
  }

  private _onOutdoorHeatingMaxChanged(e: Event) {
    const value = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(value)) {
      const celsius = toCelsius(value, this.hass);
      if (celsius !== this._outdoorHeatingMax) {
        this._outdoorHeatingMax = celsius;
        this._autoSave();
      }
    }
  }

  private _onComfortWeightChanged(e: Event) {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (!isNaN(value) && value !== this._comfortWeight) {
      this._comfortWeight = value;
      this._autoSave();
    }
  }

  private _onWeatherEntityChanged(e: CustomEvent) {
    const value = (e.detail?.value as string) ?? "";
    if (value === this._weatherEntity) return;
    this._weatherEntity = value;
    this._autoSave();
  }

  private _onPredictionEnabledChanged(e: Event) {
    this._predictionEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onResetRoomSelected(e: Event) {
    this._resetSelectedRoom = getSelectValue(e);
  }

  private _clearResetSelection() {
    this._resetSelectedRoom = "";
  }

  private async _resetRoomModel(areaId: string) {
    const l = this.hass.language;
    if (!confirm(localize("settings.reset_room_confirm", l))) return;
    try {
      fireSaveStatus(this,"saving");
      await this.hass.callWS({
        type: "roommind/thermal/reset",
        area_id: areaId,
      });
      fireSaveStatus(this,"saved");
    } catch {
      fireSaveStatus(this,"error");
    }
  }

  private async _resetAllModels() {
    const l = this.hass.language;
    if (!confirm(localize("settings.reset_all_confirm", l))) return;
    try {
      fireSaveStatus(this,"saving");
      await this.hass.callWS({ type: "roommind/thermal/reset_all" });
      fireSaveStatus(this,"saved");
    } catch {
      fireSaveStatus(this,"error");
    }
  }

  private _removeMoldTarget(idx: number) {
    this._moldNotificationTargets = this._moldNotificationTargets.filter((_, i) => i !== idx);
    this._autoSave();
  }

  private _onMoldTargetAdded(e: CustomEvent) {
    const value = (e.detail?.value as string) ?? "";
    if (!value) return;
    this._moldNotificationTargets = [
      ...this._moldNotificationTargets,
      { entity_id: value, person_entity: "", notify_when: "always" as const },
    ];
    // Reset picker by forcing re-render
    const picker = e.target as HTMLElement & { value?: string };
    if (picker) picker.value = "";
    this._autoSave();
  }

  private _onMoldTargetPersonChanged(idx: number, e: CustomEvent) {
    const value = (e.detail?.value as string) ?? "";
    const targets = [...this._moldNotificationTargets];
    targets[idx] = { ...targets[idx], person_entity: value };
    this._moldNotificationTargets = targets;
    this._autoSave();
  }

  private _onMoldTargetWhenChanged(idx: number, e: Event) {
    const value = getSelectValue(e) as "always" | "home_only";
    if (!value) return;
    const targets = [...this._moldNotificationTargets];
    targets[idx] = { ...targets[idx], notify_when: value };
    this._moldNotificationTargets = targets;
    this._autoSave();
  }

  private _onMoldNotificationsEnabledToggled(e: Event) {
    this._moldNotificationsEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onMoldDetectionToggled(e: Event) {
    this._moldDetectionEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onMoldThresholdChanged(e: Event) {
    const value = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(value) && value >= 50 && value <= 90 && value !== this._moldHumidityThreshold) {
      this._moldHumidityThreshold = value;
      this._autoSave();
    }
  }

  private _onMoldSustainedChanged(e: Event) {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (!isNaN(value) && value >= 5 && value <= 120 && value !== this._moldSustainedMinutes) {
      this._moldSustainedMinutes = value;
      this._autoSave();
    }
  }

  private _onMoldCooldownChanged(e: Event) {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (!isNaN(value) && value >= 10 && value <= 1440 && value !== this._moldNotificationCooldown) {
      this._moldNotificationCooldown = value;
      this._autoSave();
    }
  }

  private _onMoldPreventionToggled(e: Event) {
    this._moldPreventionEnabled = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _onMoldIntensityChanged(e: Event) {
    const value = getSelectValue(e) as "light" | "medium" | "strong";
    if (value && value !== this._moldPreventionIntensity) {
      this._moldPreventionIntensity = value;
      this._autoSave();
    }
  }

  private _onMoldPreventionNotifyToggled(e: Event) {
    this._moldPreventionNotify = (e.target as HTMLInputElement).checked;
    this._autoSave();
  }

  private _autoSave() {
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this,"saving");

    try {
      await this.hass.callWS({
        type: "roommind/settings/save",
        group_by_floor: this._groupByFloor,
        climate_control_active: this._climateControlActive,
        learning_disabled_rooms: this._learningDisabledRooms,
        outdoor_temp_sensor: this._outdoorTempSensor,
        outdoor_humidity_sensor: this._outdoorHumiditySensor,
        outdoor_cooling_min: this._outdoorCoolingMin,
        outdoor_heating_max: this._outdoorHeatingMax,
        control_mode: this._controlMode,
        comfort_weight: this._comfortWeight,
        weather_entity: this._weatherEntity,
        prediction_enabled: this._predictionEnabled,
        vacation_temp: this._vacationTemp,
        vacation_until: this._vacationActive && this._vacationUntil
          ? new Date(this._vacationUntil).getTime() / 1000
          : null,
        presence_enabled: this._presenceEnabled,
        presence_persons: this._presencePersons.filter(p => p),
        presence_away_action: this._presenceAwayAction,
        schedule_off_action: this._scheduleOffAction,
        valve_protection_enabled: this._valveProtectionEnabled,
        valve_protection_interval_days: this._valveProtectionInterval,
        mold_detection_enabled: this._moldDetectionEnabled,
        mold_humidity_threshold: this._moldHumidityThreshold,
        mold_sustained_minutes: this._moldSustainedMinutes,
        mold_notification_cooldown: this._moldNotificationCooldown,
        mold_notifications_enabled: this._moldNotificationsEnabled,
        mold_notification_targets: this._moldNotificationTargets.filter(t => t.entity_id),
        mold_prevention_enabled: this._moldPreventionEnabled,
        mold_prevention_intensity: this._moldPreventionIntensity,
        mold_prevention_notify_enabled: this._moldPreventionNotify,
        mold_prevention_notify_targets: this._moldPreventionNotify
          ? this._moldNotificationTargets.filter(t => t.entity_id)
          : [],
      });
      fireSaveStatus(this,"saved");
    } catch {
      fireSaveStatus(this,"error");
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings": RsSettings;
  }
}

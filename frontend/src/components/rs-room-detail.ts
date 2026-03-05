import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  HassArea,
  RoomConfig,
  ClimateMode,
  OverrideType,
  ScheduleEntry,
} from "../types";
import "./rs-hero-status";
import "./rs-climate-mode-selector";
import "./rs-schedule-settings";
import "./rs-device-section";
import "./rs-section-card";
import { localize } from "../utils/localize";
import { fireSaveStatus } from "../utils/events";
import { formatTemp, tempUnit, toDisplay, toCelsius, tempStep, tempRange } from "../utils/temperature";

@customElement("rs-room-detail")
export class RsRoomDetail extends LitElement {
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ type: Boolean }) public climateControlActive = true;

  @state() private _selectedThermostats: Set<string> = new Set();
  @state() private _selectedAcs: Set<string> = new Set();
  @state() private _selectedTempSensor = "";
  @state() private _selectedHumiditySensor = "";
  @state() private _selectedWindowSensors: Set<string> = new Set();
  @state() private _windowOpenDelay = 0;
  @state() private _windowCloseDelay = 0;
  @state() private _climateMode: ClimateMode = "auto";
  @state() private _schedules: ScheduleEntry[] = [];
  @state() private _scheduleSelectorEntity = "";
  @state() private _comfortHeat = 21.0;
  @state() private _comfortCool = 24.0;
  @state() private _ecoHeat = 17.0;
  @state() private _ecoCool = 27.0;
  @state() private _error = "";
  @state() private _dirty = false;
  @state() private _overridePending: OverrideType | null = null;
  @state() private _overrideCustomTemp = 21;
  @state() private _overrideError = "";
  @state() private _optimisticOverride: {
    type: OverrideType;
    temp: number;
    until: number;
  } | null = null;
  @state() private _optimisticClear = false;
  @state() private _editingSchedule = false;
  @state() private _editingDevices = false;
  @state() private _editingPresence = false;
  @state() private _selectedPresencePersons: string[] = [];
  @state() private _displayName = "";
  @state() private _heatingSystemType = "";


  private _prevAreaId: string | null = null;
  private _saveDebounce?: ReturnType<typeof setTimeout>;

  static styles = css`
    :host {
      display: block;
      max-width: 1100px;
      margin: 0 auto;
    }

    .detail-layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .col-left,
    .col-right {
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
    }

    @media (max-width: 860px) {
      .detail-layout {
        grid-template-columns: 1fr;
      }
    }

    /* Section cards handled by rs-section-card */

    /* Actions */
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 8px;
      margin-bottom: 24px;
    }

    .error {
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      margin-top: 8px;
    }

    /* Override section */
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
      transition: background 0.15s, border-color 0.15s;
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

    .override-duration {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      align-items: center;
    }

    .override-duration-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-dur-chip {
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 12px;
      background: transparent;
      color: var(--primary-text-color);
      transition: background 0.15s;
    }

    .override-dur-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .override-dur-chip:disabled {
      opacity: 0.5;
      pointer-events: none;
    }

    .override-custom-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }

    .override-custom-row input {
      width: 56px;
      padding: 4px 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
      font-size: 13px;
      text-align: center;
      background: transparent;
      color: var(--primary-text-color);
    }

    .override-custom-row span {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-error {
      color: var(--error-color, #d32f2f);
      font-size: 12px;
      margin-top: 6px;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
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

    .presence-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .presence-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 13px;
      font-family: inherit;
      background: transparent;
      color: var(--secondary-text-color);
      transition: background 0.15s, border-color 0.15s, color 0.15s;
    }

    .presence-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-chip.active {
      border-color: var(--primary-color);
      color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .presence-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s;
    }

    .presence-row.home {
      background: rgba(76, 175, 80, 0.1);
    }

    .presence-row.away {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .presence-row.home .presence-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .presence-row.away .presence-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .presence-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .presence-row.home .presence-name {
      color: var(--primary-text-color);
    }

    .presence-row.away .presence-name {
      color: var(--secondary-text-color);
    }

    .presence-state {
      font-size: 12px;
      white-space: nowrap;
    }

    .presence-row.home .presence-state {
      color: #2e7d32;
    }

    .presence-row.away .presence-state {
      color: var(--secondary-text-color);
    }

    .help-content {
      padding: 0 16px 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }
  `;

  connectedCallback() {
    super.connectedCallback();
    this._initFromConfig();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
  }

  updated(changedProps: Map<string, unknown>) {
    const currentAreaId = this.config?.area_id ?? this.area?.area_id ?? null;
    const areaChanged = currentAreaId !== this._prevAreaId;

    if (areaChanged) {
      this._initFromConfig();
      this._prevAreaId = currentAreaId;
    } else if (changedProps.has("config") && !this._dirty) {
      const prevConfig = changedProps.get("config") as
        | RoomConfig
        | null
        | undefined;
      if (prevConfig === null || prevConfig === undefined) {
        this._initFromConfig();
      }
    }

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

  private _initFromConfig() {
    if (this.config) {
      this._selectedThermostats = new Set(this.config.thermostats);
      this._selectedAcs = new Set(this.config.acs);
      this._selectedTempSensor = this.config.temperature_sensor;
      this._selectedHumiditySensor = this.config.humidity_sensor ?? "";
      this._selectedWindowSensors = new Set(this.config.window_sensors ?? []);
      this._windowOpenDelay = this.config.window_open_delay ?? 0;
      this._windowCloseDelay = this.config.window_close_delay ?? 0;
      this._climateMode = this.config.climate_mode;
      this._schedules = this.config.schedules ?? [];
      this._scheduleSelectorEntity = this.config.schedule_selector_entity ?? "";
      this._comfortHeat = this.config.comfort_heat ?? this.config.comfort_temp ?? 21.0;
      this._comfortCool = this.config.comfort_cool ?? 24.0;
      this._ecoHeat = this.config.eco_heat ?? this.config.eco_temp ?? 17.0;
      this._ecoCool = this.config.eco_cool ?? 27.0;
      this._selectedPresencePersons = this.config.presence_persons ?? [];
      this._displayName = this.config.display_name ?? "";
      this._heatingSystemType = this.config.heating_system_type ?? "";
    } else {
      this._selectedThermostats = new Set();
      this._selectedAcs = new Set();
      this._selectedTempSensor = "";
      this._selectedHumiditySensor = "";
      this._selectedWindowSensors = new Set();
      this._windowOpenDelay = 0;
      this._windowCloseDelay = 0;
      this._climateMode = "auto";
      this._schedules = [];
      this._scheduleSelectorEntity = "";
      this._comfortHeat = 21.0;
      this._comfortCool = 24.0;
      this._ecoHeat = 17.0;
      this._ecoCool = 27.0;
      this._selectedPresencePersons = [];
      this._displayName = "";
      this._heatingSystemType = "";
    }
    this._dirty = false;

    // Auto-detect editing mode
    const hasDevices = this._selectedThermostats.size > 0 || this._selectedAcs.size > 0 || !!this._selectedTempSensor;
    this._editingSchedule = this._schedules.length === 0;
    this._editingDevices = !hasDevices;
  }

  render() {
    if (!this.area) return nothing;

    return html`
      <div class="detail-layout">
        <div class="col-left">
          <rs-hero-status
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .overrideInfo=${this._getEffectiveOverride()}
            .climateControlActive=${this.climateControlActive}
            @display-name-changed=${this._onDisplayNameChanged}
          ></rs-hero-status>

          <rs-section-card
            icon="mdi:cog"
            .heading=${localize("room.section.climate_mode", this.hass.language)}
            hasInfo
          >
            <div slot="info">
              <b>${localize("mode.auto", this.hass.language)}</b> — ${localize("mode.auto_desc", this.hass.language)}<br>
              <b>${localize("mode.heat_only", this.hass.language)}</b> — ${localize("mode.heat_only_desc", this.hass.language)}<br>
              <b>${localize("mode.cool_only", this.hass.language)}</b> — ${localize("mode.cool_only_desc", this.hass.language)}
            </div>
            <rs-climate-mode-selector
              .climateMode=${this._climateMode}
              .language=${this.hass.language}
              @mode-changed=${this._onModeChanged}
            ></rs-climate-mode-selector>
          </rs-section-card>

          <rs-section-card
            icon="mdi:calendar"
            .heading=${localize("room.section.schedule", this.hass.language)}
            editable
            .editing=${this._editingSchedule}
            .doneLabel=${localize("schedule.done", this.hass.language)}
            @edit-click=${() => { this._editingSchedule = true; }}
            @done-click=${() => { this._editingSchedule = false; }}
          >
            <rs-schedule-settings
              .hass=${this.hass}
              .schedules=${this._schedules}
              .scheduleSelectorEntity=${this._scheduleSelectorEntity}
              .activeScheduleIndex=${this.config?.live?.active_schedule_index ?? -1}
              .comfortHeat=${this._comfortHeat}
              .comfortCool=${this._comfortCool}
              .ecoHeat=${this._ecoHeat}
              .ecoCool=${this._ecoCool}
              .climateMode=${this._climateMode}
              .editing=${this._editingSchedule}
              @schedules-changed=${this._onSchedulesChanged}
              @schedule-selector-changed=${this._onScheduleSelectorChanged}
              @comfort-heat-changed=${this._onComfortHeatChanged}
              @comfort-cool-changed=${this._onComfortCoolChanged}
              @eco-heat-changed=${this._onEcoHeatChanged}
              @eco-cool-changed=${this._onEcoCoolChanged}
            ></rs-schedule-settings>
            ${this.config ? this._renderOverrideSection() : nothing}
          </rs-section-card>

          ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        </div>

        <div class="col-right">
          <rs-section-card
            icon="mdi:power-plug"
            .heading=${localize("room.section.devices", this.hass.language)}
            editable
            .editing=${this._editingDevices}
            .doneLabel=${localize("devices.done", this.hass.language)}
            @edit-click=${() => { this._editingDevices = true; }}
            @done-click=${() => { this._editingDevices = false; }}
          >
            <rs-device-section
              .hass=${this.hass}
              .area=${this.area}
              .editing=${this._editingDevices}
              .selectedThermostats=${this._selectedThermostats}
              .selectedAcs=${this._selectedAcs}
              .selectedTempSensor=${this._selectedTempSensor}
              .selectedHumiditySensor=${this._selectedHumiditySensor}
              .selectedWindowSensors=${this._selectedWindowSensors}
              .windowOpenDelay=${this._windowOpenDelay}
              .windowCloseDelay=${this._windowCloseDelay}
              .heatingSystemType=${this._heatingSystemType}
              @climate-toggle=${this._onClimateToggle}
              @device-type-change=${this._onDeviceTypeChange}
              @sensor-selected=${this._onSensorSelected}
              @window-sensor-toggle=${this._onWindowSensorToggle}
              @window-open-delay-changed=${this._onWindowOpenDelayChanged}
              @window-close-delay-changed=${this._onWindowCloseDelayChanged}
              @external-entity-added=${this._onExternalEntityAdded}
              @heating-system-type-changed=${this._onHeatingSystemTypeChanged}
            ></rs-device-section>
          </rs-section-card>

          ${this._renderPresenceSection()}
        </div>
      </div>
    `;
  }

  // ---- Child event handlers ----

  private _onModeChanged(e: CustomEvent<{ mode: ClimateMode }>) {
    this._climateMode = e.detail.mode;
    this._autoSave();
  }

  private _onSchedulesChanged(e: CustomEvent<{ value: ScheduleEntry[] }>) {
    this._schedules = e.detail.value;
    this._autoSave();
  }

  private _onScheduleSelectorChanged(e: CustomEvent<{ value: string }>) {
    this._scheduleSelectorEntity = e.detail.value;
    this._autoSave();
  }

  private _onComfortHeatChanged(e: CustomEvent<{ value: number }>) {
    this._comfortHeat = e.detail.value;
    if (this._comfortCool < this._comfortHeat) this._comfortCool = this._comfortHeat;
    this._autoSave();
  }

  private _onComfortCoolChanged(e: CustomEvent<{ value: number }>) {
    this._comfortCool = e.detail.value;
    if (this._comfortHeat > this._comfortCool) this._comfortHeat = this._comfortCool;
    this._autoSave();
  }

  private _onEcoHeatChanged(e: CustomEvent<{ value: number }>) {
    this._ecoHeat = e.detail.value;
    if (this._ecoCool < this._ecoHeat) this._ecoCool = this._ecoHeat;
    this._autoSave();
  }

  private _onEcoCoolChanged(e: CustomEvent<{ value: number }>) {
    this._ecoCool = e.detail.value;
    if (this._ecoHeat > this._ecoCool) this._ecoHeat = this._ecoCool;
    this._autoSave();
  }

  private _onClimateToggle(
    e: CustomEvent<{ entityId: string; checked: boolean; detectedType: "thermostat" | "ac" }>
  ) {
    const { entityId, checked, detectedType } = e.detail;
    if (checked) {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      if (detectedType === "ac") {
        newAcs.add(entityId);
      } else {
        newThermostats.add(entityId);
      }
      this._selectedThermostats = newThermostats;
      this._selectedAcs = newAcs;
    } else {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      newThermostats.delete(entityId);
      newAcs.delete(entityId);
      this._selectedThermostats = newThermostats;
      this._selectedAcs = newAcs;
    }
    this._autoSave();
  }

  private _onDeviceTypeChange(
    e: CustomEvent<{ entityId: string; type: "thermostat" | "ac" }>
  ) {
    const { entityId, type } = e.detail;
    const newThermostats = new Set(this._selectedThermostats);
    const newAcs = new Set(this._selectedAcs);

    if (type === "thermostat") {
      newAcs.delete(entityId);
      newThermostats.add(entityId);
    } else {
      newThermostats.delete(entityId);
      newAcs.add(entityId);
    }

    this._selectedThermostats = newThermostats;
    this._selectedAcs = newAcs;
    this._autoSave();
  }

  private _onSensorSelected(
    e: CustomEvent<{ entityId: string; type: "temp" | "humidity" }>
  ) {
    if (e.detail.type === "temp") {
      this._selectedTempSensor = e.detail.entityId;
    } else {
      this._selectedHumiditySensor = e.detail.entityId;
    }
    this._autoSave();
  }

  private _onWindowSensorToggle(
    e: CustomEvent<{ entityId: string; checked: boolean }>
  ) {
    const { entityId, checked } = e.detail;
    const next = new Set(this._selectedWindowSensors);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this._selectedWindowSensors = next;
    this._autoSave();
  }

  private _onWindowOpenDelayChanged(e: CustomEvent<{ value: number }>) {
    this._windowOpenDelay = e.detail.value;
    this._autoSave();
  }

  private _onWindowCloseDelayChanged(e: CustomEvent<{ value: number }>) {
    this._windowCloseDelay = e.detail.value;
    this._autoSave();
  }

  private _onHeatingSystemTypeChanged(e: CustomEvent<{ value: string }>) {
    this._heatingSystemType = e.detail.value;
    this._autoSave();
  }

  private _onExternalEntityAdded(
    e: CustomEvent<{ entityId: string; category: "climate" | "temp" | "humidity" | "window"; detectedType?: "thermostat" | "ac" }>
  ) {
    const { entityId, category, detectedType } = e.detail;
    if (category === "climate") {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      if (detectedType === "ac") {
        newAcs.add(entityId);
      } else {
        newThermostats.add(entityId);
      }
      this._selectedThermostats = newThermostats;
      this._selectedAcs = newAcs;
    } else if (category === "temp") {
      this._selectedTempSensor = entityId;
    } else if (category === "window") {
      const next = new Set(this._selectedWindowSensors);
      next.add(entityId);
      this._selectedWindowSensors = next;
    } else {
      this._selectedHumiditySensor = entityId;
    }
    this._autoSave();
  }

  // ---- Auto-save ----

  private _onDisplayNameChanged(e: CustomEvent<{ value: string }>) {
    this._displayName = e.detail.value;
    this._autoSave();
  }

  private _autoSave() {
    this._dirty = true;
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this,"saving");
    this._error = "";

    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: this.area.area_id,
        thermostats: [...this._selectedThermostats],
        acs: [...this._selectedAcs],
        temperature_sensor: this._selectedTempSensor,
        humidity_sensor: this._selectedHumiditySensor,
        window_sensors: [...this._selectedWindowSensors],
        window_open_delay: this._windowOpenDelay,
        window_close_delay: this._windowCloseDelay,
        climate_mode: this._climateMode,
        schedules: this._schedules,
        schedule_selector_entity: this._scheduleSelectorEntity,
        comfort_heat: this._comfortHeat,
        comfort_cool: this._comfortCool,
        eco_heat: this._ecoHeat,
        eco_cool: this._ecoCool,
        presence_persons: this._selectedPresencePersons.filter(p => p),
        display_name: this._displayName,
        heating_system_type: this._heatingSystemType,
      });

      this._dirty = false;
      fireSaveStatus(this,"saved");

      this.dispatchEvent(
        new CustomEvent("room-updated", {
          bubbles: true,
          composed: true,
        })
      );
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : localize("room.error_save_fallback", this.hass.language);
      this._error = message;
      fireSaveStatus(this,"error");
    }
  }

  // ---- Override handlers ----

  private _getEffectiveOverride(): {
    active: boolean;
    type: OverrideType | null;
    temp: number | null;
    until: number | null;
  } {
    // Optimistic clear takes priority
    if (this._optimisticClear) {
      return { active: false, type: null, temp: null, until: null };
    }
    // Optimistic set takes priority over server data
    if (this._optimisticOverride) {
      return {
        active: true,
        type: this._optimisticOverride.type,
        temp: this._optimisticOverride.temp,
        until: this._optimisticOverride.until,
      };
    }
    // Fall back to server data
    const live = this.config?.live;
    if (live?.override_active && live.override_type) {
      return {
        active: true,
        type: live.override_type,
        temp: live.override_temp,
        until: live.override_until,
      };
    }
    return { active: false, type: null, temp: null, until: null };
  }

  private _renderPresenceSection() {
    if (!this.presenceEnabled || this.presencePersons.length === 0) return nothing;

    return html`
      <rs-section-card
        icon="mdi:home-account"
        .heading=${localize("room.section.presence", this.hass.language)}
        editable
        .editing=${this._editingPresence}
        .doneLabel=${localize("schedule.done", this.hass.language)}
        @edit-click=${() => { this._editingPresence = true; }}
        @done-click=${() => { this._editingPresence = false; }}
      >
        ${this._editingPresence ? html`
          <div style="padding: 0 16px 16px">
            <div class="presence-chips">
              ${this.presencePersons.map((pid) => {
                const active = this._selectedPresencePersons.includes(pid);
                const name = this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join(".");
                return html`
                  <button
                    class="presence-chip ${active ? "active" : ""}"
                    @click=${() => {
                      if (active) {
                        this._selectedPresencePersons = this._selectedPresencePersons.filter(p => p !== pid);
                      } else {
                        this._selectedPresencePersons = [...this._selectedPresencePersons, pid];
                      }
                      this._autoSave();
                    }}
                  >
                    <ha-icon icon=${active ? "mdi:account-check" : "mdi:account-outline"} style="--mdc-icon-size: 16px"></ha-icon>
                    ${name}
                  </button>
                `;
              })}
            </div>
            <ha-expansion-panel outlined .header=${localize("presence.room_help_header", this.hass.language)} style="margin-top: 12px">
              <div class="help-content">
                <p>${localize("presence.room_help_body", this.hass.language)}</p>
              </div>
            </ha-expansion-panel>
          </div>
        ` : html`
          <div style="padding: 0 16px 16px">
            ${this._selectedPresencePersons.length > 0 ? html`
              <div class="presence-list">
                ${this._selectedPresencePersons.map((pid) => {
                  const name = this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join(".");
                  const st = this.hass.states[pid]?.state;
                  const isHome = pid.startsWith("person.") || pid.startsWith("device_tracker.") ? st === "home" : st === "on";
                  return html`
                    <div class="presence-row ${isHome ? "home" : "away"}">
                      <span class="presence-dot"></span>
                      <span class="presence-name">${name}</span>
                      <span class="presence-state">${isHome
                        ? localize("presence.state_home", this.hass.language)
                        : localize("presence.state_away", this.hass.language)}</span>
                    </div>
                  `;
                })}
              </div>
            ` : html`
              <span class="field-hint">${localize("presence.room_none_assigned", this.hass.language)}</span>
            `}
          </div>
        `}
      </rs-section-card>
    `;
  }

  private _renderOverrideSection() {
    const ov = this._getEffectiveOverride();

    return html`
      <hr class="override-divider" />
      <div class="override-label">${localize("override.label", this.hass.language)}</div>
      ${this._renderOverrideButtons(ov)}
      ${this._overrideError
        ? html`<div class="override-error">${this._overrideError}</div>`
        : nothing}
    `;
  }

  private _renderOverrideButtons(ov: ReturnType<typeof this._getEffectiveOverride>) {
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
              @click=${() => isActive ? this._onClearOverride() : this._onOverridePreset(t)}
            >
              <ha-icon icon=${t === "boost" ? "mdi:fire" : t === "eco" ? "mdi:leaf" : "mdi:thermometer"}></ha-icon>
              ${t === "boost" ? `${localize("override.comfort", this.hass.language)} ${formatTemp(this._climateMode === "cool_only" ? this._comfortCool : this._comfortHeat, this.hass)}${tempUnit(this.hass)}`
                : t === "eco" ? `${localize("override.eco", this.hass.language)} ${formatTemp(this._climateMode === "cool_only" ? this._ecoCool : this._ecoHeat, this.hass)}${tempUnit(this.hass)}`
                : localize("override.custom", this.hass.language)}
            </button>
          `;
        })}
      </div>
      ${showDuration
        ? html`
            ${this._overridePending === "custom"
              ? html`
                  <div class="override-custom-row">
                    <span>${localize("override.target", this.hass.language)}</span>
                    <input
                      type="number"
                      min=${tempRange(5, 35, this.hass).min}
                      max=${tempRange(5, 35, this.hass).max}
                      step=${tempStep(this.hass)}
                      .value=${String(toDisplay(this._overrideCustomTemp, this.hass))}
                      @input=${this._onOverrideCustomTempInput}
                    />
                    <span>${tempUnit(this.hass)}</span>
                  </div>
                `
              : nothing}
            <div class="override-duration">
              <span class="override-duration-label">${localize("override.activate_for", this.hass.language)}</span>
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
                `
              )}
            </div>
          `
        : nothing}
    `;
  }

  private _onOverridePreset(type: OverrideType): void {
    if (this._overridePending === type) {
      this._overridePending = null;
    } else {
      this._overridePending = type;
      if (type === "custom") {
        this._overrideCustomTemp = this._climateMode === "cool_only" ? this._comfortCool : this._comfortHeat;
      }
    }
    this._overrideError = "";
  }

  private _onOverrideCustomTempInput(e: Event): void {
    this._overrideCustomTemp = toCelsius(Number((e.target as HTMLInputElement).value) || toDisplay(21, this.hass), this.hass);
  }

  private async _onOverrideActivate(hours: number): Promise<void> {
    if (!this._overridePending || !this.config) return;

    const pendingType = this._overridePending;
    let temp: number;
    if (pendingType === "boost") {
      temp = this._climateMode === "cool_only" ? this._comfortCool : this._comfortHeat;
    } else if (pendingType === "eco") {
      temp = this._climateMode === "cool_only" ? this._ecoCool : this._ecoHeat;
    } else {
      temp = this._overrideCustomTemp;
    }

    // Optimistic: show override immediately
    this._optimisticOverride = {
      type: pendingType,
      temp,
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
      msg.temperature = temp;
    }

    try {
      await this.hass.callWS(msg);
      // Refresh real data in background; optimistic state stays until
      // server data arrives and confirms the override.
      this._fireRoomUpdated();
    } catch (err) {
      // Rollback optimistic state on error
      this._optimisticOverride = null;
      this._overrideError =
        err instanceof Error ? err.message : localize("override.error_set", this.hass.language);
      console.error("Override set failed:", err);
    }
  }

  private async _onClearOverride(): Promise<void> {
    if (!this.config) return;

    // Optimistic: hide override immediately
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
      // Rollback optimistic state on error
      this._optimisticClear = false;
      this._overrideError =
        err instanceof Error ? err.message : localize("override.error_clear", this.hass.language);
      console.error("Override clear failed:", err);
    }
  }

  private _fireRoomUpdated(): void {
    this.dispatchEvent(
      new CustomEvent("room-updated", { bubbles: true, composed: true })
    );
  }

}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-detail": RsRoomDetail;
  }
}

import { LitElement, html, css, nothing } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  HassArea,
  RoomConfig,
  ClimateMode,
  ScheduleEntry,
  CoverScheduleEntry,
  DeviceConfig,
  DeviceType,
  DeviceRole,
} from "../types";
import "./rs-hero-status";
import "./rs-climate-mode-selector";
import "./rs-schedule-settings";
import "./rs-device-section";
import "./rs-sensor-section";
import "./rs-window-section";
import "./rs-section-card";
import "./rs-override-section";
import "./rs-presence-section";
import "./rs-covers-section";
import "./rs-heat-source-section";
import "../components/shared/rs-toggle-row";
import { localize } from "../utils/localize";
import { fireSaveStatus } from "../utils/events";
import { resolveHeatingSystemType } from "../utils/device-utils";
import type { RsOverrideSection } from "./rs-override-section";

@customElement("rs-room-detail")
export class RsRoomDetail extends LitElement {
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ type: Boolean }) public climateControlActive = true;

  @property({ type: Boolean }) public valveProtectionEnabled = false;

  @state() private _devices: DeviceConfig[] = [];
  @state() private _selectedTempSensor = "";
  @state() private _selectedHumiditySensor = "";
  @state() private _selectedOccupancySensors: Set<string> = new Set();
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
  @state() private _editingSchedule = false;
  @state() private _editingDevices = false;
  @state() private _editingSensors = false;
  @state() private _editingWindows = false;
  @state() private _editingPresence = false;
  @state() private _selectedPresencePersons: string[] = [];
  @state() private _displayName = "";
  @state() private _selectedCovers: Set<string> = new Set();
  @state() private _coversAutoEnabled = false;
  @state() private _coversDeployThreshold = 1.5;
  @state() private _coversMinPosition = 0;
  @state() private _coversOverrideMinutes = 60;
  @state() private _coverSchedules: CoverScheduleEntry[] = [];
  @state() private _coverScheduleSelectorEntity = "";
  @state() private _coversNightClose = false;
  @state() private _coversNightPosition = 0;
  @state() private _coversSnapDeploy = false;
  @state() private _coverOrientations: Record<string, number> = {};
  @state() private _coversNightCloseElevation = 0;
  @state() private _coversNightCloseOffsetMinutes = 0;
  @state() private _coversOutdoorMinTemp: number | null = 10;
  @state() private _coverMinPositions: Record<string, number> = {};
  @state() private _editingCovers = false;
  @state() private _ignorePresence = false;
  @state() private _isOutdoor = false;
  @state() private _valveProtectionExclude: Set<string> = new Set();
  @state() private _climateControlEnabled = true;
  @state() private _heatSourceOrchestration = false;
  @state() private _heatSourcePrimaryDelta = 1.5;
  @state() private _heatSourceOutdoorThreshold = 5.0;
  @state() private _heatSourceAcMinOutdoor = -15.0;

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

    .outdoor-toggle-card,
    .climate-control-toggle-card {
      padding: 12px 16px;
    }

    /* Section cards handled by rs-section-card */

    /* YAML code block for info panels (slotted into rs-section-card) */
    .yaml-block {
      background: var(--primary-background-color, #f5f5f5);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      padding: 10px 14px;
      margin: 8px 0;
      font-family: var(--code-font-family, monospace);
      font-size: 12px;
      line-height: 1.6;
      white-space: pre;
      overflow-x: auto;
      color: var(--primary-text-color);
    }
    .yaml-key {
      color: #0550ae;
    }
    .yaml-value {
      color: #0a3069;
    }

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
      const prevConfig = changedProps.get("config") as RoomConfig | null | undefined;
      if (prevConfig === null || prevConfig === undefined) {
        this._initFromConfig();
      }
    }
  }

  private _initFromConfig() {
    if (this.config) {
      if (this.config.devices?.length) {
        this._devices = [...this.config.devices];
      } else {
        this._devices = [
          ...(this.config.thermostats ?? []).map((eid) => ({
            entity_id: eid,
            type: "trv" as DeviceType,
            role: "auto" as DeviceRole,
            heating_system_type: this.config!.heating_system_type ?? "",
          })),
          ...(this.config.acs ?? []).map((eid) => ({
            entity_id: eid,
            type: "ac" as DeviceType,
            role: "auto" as DeviceRole,
          })),
        ];
      }
      this._selectedTempSensor = this.config.temperature_sensor;
      this._selectedHumiditySensor = this.config.humidity_sensor ?? "";
      this._selectedOccupancySensors = new Set(this.config.occupancy_sensors ?? []);
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
      this._selectedCovers = new Set(this.config.covers ?? []);
      this._coversAutoEnabled = this.config.covers_auto_enabled ?? false;
      this._coversDeployThreshold = this.config.covers_deploy_threshold ?? 1.5;
      this._coversMinPosition = this.config.covers_min_position ?? 0;
      this._coversOverrideMinutes = this.config.covers_override_minutes ?? 60;
      this._coverSchedules = this.config.cover_schedules ?? [];
      this._coverScheduleSelectorEntity = this.config.cover_schedule_selector_entity ?? "";
      this._coversNightClose = this.config.covers_night_close ?? false;
      this._coversNightPosition = this.config.covers_night_position ?? 0;
      this._coversSnapDeploy = this.config.covers_snap_deploy ?? false;
      this._coverOrientations = this.config.cover_orientations ?? {};
      this._coversNightCloseElevation = this.config.covers_night_close_elevation ?? 0;
      this._coversNightCloseOffsetMinutes = this.config.covers_night_close_offset_minutes ?? 0;
      this._coversOutdoorMinTemp = this.config.covers_outdoor_min_temp ?? 10;
      this._coverMinPositions = this.config.cover_min_positions ?? {};
      this._ignorePresence = this.config.ignore_presence ?? false;
      this._isOutdoor = this.config.is_outdoor ?? false;
      this._valveProtectionExclude = new Set(this.config.valve_protection_exclude ?? []);
      this._climateControlEnabled = this.config.climate_control_enabled ?? true;
      this._heatSourceOrchestration = this.config.heat_source_orchestration ?? false;
      this._heatSourcePrimaryDelta = this.config.heat_source_primary_delta ?? 1.5;
      this._heatSourceOutdoorThreshold = this.config.heat_source_outdoor_threshold ?? 5.0;
      this._heatSourceAcMinOutdoor = this.config.heat_source_ac_min_outdoor ?? -15.0;
    } else {
      this._devices = [];
      this._selectedTempSensor = "";
      this._selectedHumiditySensor = "";
      this._selectedOccupancySensors = new Set();
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
      this._selectedCovers = new Set();
      this._coversAutoEnabled = false;
      this._coversDeployThreshold = 1.5;
      this._coversMinPosition = 0;
      this._coversOverrideMinutes = 60;
      this._coverSchedules = [];
      this._coverScheduleSelectorEntity = "";
      this._coversNightClose = false;
      this._coversNightPosition = 0;
      this._coversSnapDeploy = false;
      this._coverOrientations = {};
      this._coversNightCloseElevation = 0;
      this._coversNightCloseOffsetMinutes = 0;
      this._coversOutdoorMinTemp = 10;
      this._coverMinPositions = {};
      this._ignorePresence = false;
      this._isOutdoor = false;
      this._valveProtectionExclude = new Set();
      this._climateControlEnabled = true;
      this._heatSourceOrchestration = false;
      this._heatSourcePrimaryDelta = 1.5;
      this._heatSourceOutdoorThreshold = 5.0;
      this._heatSourceAcMinOutdoor = -15.0;
    }
    this._dirty = false;

    // A room is "configured" once it has at least one device.
    // Unconfigured rooms open all panels in edit mode (setup flow).
    // Configured rooms open all panels in display mode (user clicks pen to edit).
    const isConfigured = this._devices.length > 0;
    this._editingSchedule = !isConfigured;
    this._editingDevices = !isConfigured;
    this._editingSensors = !isConfigured;
    this._editingWindows = !isConfigured;
    this._editingCovers = !isConfigured;
  }

  /** Expose effective override for hero-status via the override sub-component. */
  private _getEffectiveOverride(): {
    active: boolean;
    type: import("../types").OverrideType | null;
    temp: number | null;
    until: number | null;
  } {
    const overrideEl = this.shadowRoot?.querySelector(
      "rs-override-section",
    ) as RsOverrideSection | null;
    if (overrideEl) {
      return overrideEl.getEffectiveOverride();
    }
    // Fallback before sub-component mounts
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

  render() {
    if (!this.area) return nothing;

    return html`
      <div class="detail-layout">
        <div class="col-left">
          <rs-hero-status
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .isOutdoor=${this._isOutdoor}
            .overrideInfo=${this._getEffectiveOverride()}
            .climateControlActive=${this.climateControlActive && this._climateControlEnabled}
            @display-name-changed=${this._onDisplayNameChanged}
          ></rs-hero-status>

          ${!this._isOutdoor
            ? html`
                <ha-card class="climate-control-toggle-card">
                  <rs-toggle-row
                    .label=${localize("room.climate_control_toggle", this.hass.language)}
                    .hint=${localize("room.climate_control_hint", this.hass.language)}
                    .checked=${this._climateControlEnabled}
                    @toggle-changed=${this._onClimateControlToggle}
                  ></rs-toggle-row>
                </ha-card>

                <rs-section-card
                  icon="mdi:cog"
                  .heading=${localize("room.section.climate_mode", this.hass.language)}
                  hasInfo
                >
                  <div slot="info">
                    <b>${localize("mode.auto", this.hass.language)}</b> —
                    ${localize("mode.auto_desc", this.hass.language)}<br />
                    <b>${localize("mode.heat_only", this.hass.language)}</b> —
                    ${localize("mode.heat_only_desc", this.hass.language)}<br />
                    <b>${localize("mode.cool_only", this.hass.language)}</b> —
                    ${localize("mode.cool_only_desc", this.hass.language)}
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
                  @edit-click=${() => {
                    this._editingSchedule = true;
                  }}
                  @done-click=${() => {
                    this._editingSchedule = false;
                  }}
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
                  ${this.config
                    ? html`
                        <rs-override-section
                          .hass=${this.hass}
                          .config=${this.config}
                          .climateMode=${this._climateMode}
                          .comfortHeat=${this._comfortHeat}
                          .comfortCool=${this._comfortCool}
                          .ecoHeat=${this._ecoHeat}
                          .ecoCool=${this._ecoCool}
                          .language=${this.hass.language}
                        ></rs-override-section>
                      `
                    : nothing}
                </rs-section-card>
              `
            : nothing}
          ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        </div>

        <div class="col-right">
          ${!this._isOutdoor
            ? html`
                <rs-section-card
                  icon="mdi:power-plug"
                  .heading=${localize("room.section.devices", this.hass.language)}
                  editable
                  .editing=${this._editingDevices}
                  .doneLabel=${localize("devices.done", this.hass.language)}
                  @edit-click=${() => {
                    this._editingDevices = true;
                  }}
                  @done-click=${() => {
                    this._editingDevices = false;
                  }}
                >
                  <rs-device-section
                    .hass=${this.hass}
                    .area=${this.area}
                    .editing=${this._editingDevices}
                    .devices=${this._devices}
                    .selectedTempSensor=${this._selectedTempSensor}
                    .selectedHumiditySensor=${this._selectedHumiditySensor}
                    .selectedOccupancySensors=${this._selectedOccupancySensors}
                    .selectedWindowSensors=${this._selectedWindowSensors}
                    .valveProtectionExclude=${this._valveProtectionExclude}
                    .valveProtectionEnabled=${this.valveProtectionEnabled}
                    @device-changed=${this._onDeviceChanged}
                    @external-entity-added=${this._onExternalEntityAdded}
                    @valve-protection-exclude-toggle=${this._onValveProtectionExcludeToggle}
                  ></rs-device-section>
                </rs-section-card>

                <rs-section-card
                  icon="mdi:thermometer"
                  .heading=${localize("room.section.sensors", this.hass.language)}
                  editable
                  .editing=${this._editingSensors}
                  .doneLabel=${localize("devices.done", this.hass.language)}
                  @edit-click=${() => {
                    this._editingSensors = true;
                  }}
                  @done-click=${() => {
                    this._editingSensors = false;
                  }}
                >
                  <rs-sensor-section
                    .hass=${this.hass}
                    .area=${this.area}
                    .editing=${this._editingSensors}
                    .temperatureSensor=${this._selectedTempSensor}
                    .humiditySensor=${this._selectedHumiditySensor}
                    .occupancySensors=${this._selectedOccupancySensors}
                    .language=${this.hass.language}
                    @sensor-changed=${this._onSensorChanged}
                  ></rs-sensor-section>
                </rs-section-card>

                <rs-section-card
                  icon="mdi:window-open-variant"
                  .heading=${localize("room.section.windows", this.hass.language)}
                  editable
                  .editing=${this._editingWindows}
                  .doneLabel=${localize("devices.done", this.hass.language)}
                  @edit-click=${() => {
                    this._editingWindows = true;
                  }}
                  @done-click=${() => {
                    this._editingWindows = false;
                  }}
                >
                  <rs-window-section
                    .hass=${this.hass}
                    .area=${this.area}
                    .editing=${this._editingWindows}
                    .windowSensors=${this._selectedWindowSensors}
                    .windowOpenDelay=${this._windowOpenDelay}
                    .windowCloseDelay=${this._windowCloseDelay}
                    .heatingSystemType=${resolveHeatingSystemType(this._devices)}
                    .language=${this.hass.language}
                    @window-config-changed=${this._onWindowConfigChanged}
                  ></rs-window-section>
                </rs-section-card>

                <rs-presence-section
                  .hass=${this.hass}
                  .presenceEnabled=${this.presenceEnabled}
                  .presencePersons=${this.presencePersons}
                  .selectedPresencePersons=${this._selectedPresencePersons}
                  .ignorePresence=${this._ignorePresence}
                  .editing=${this._editingPresence}
                  .language=${this.hass.language}
                  @presence-persons-changed=${this._onPresencePersonsChanged}
                  @ignore-presence-changed=${this._onIgnorePresenceChanged}
                  @editing-changed=${this._onPresenceEditingChanged}
                ></rs-presence-section>
              `
            : nothing}
          ${!this._isOutdoor
            ? html`<rs-section-card
                icon="mdi:blinds-horizontal"
                .heading=${localize("room.section.covers", this.hass.language)}
                .badge=${localize("badge.beta", this.hass.language)}
                .badgeHint=${localize("badge.beta_hint", this.hass.language)}
                hasInfo
                editable
                .editing=${this._editingCovers}
                .doneLabel=${localize("covers.done", this.hass.language)}
                @edit-click=${() => {
                  this._editingCovers = true;
                }}
                @done-click=${() => {
                  this._editingCovers = false;
                }}
              >
                <div slot="info">
                  <b>${localize("covers.info.selection_title", this.hass.language)}</b><br />
                  ${localize("covers.info.selection_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.schedule_title", this.hass.language)}</b><br />
                  ${localize("covers.info.schedule_body", this.hass.language)}
                  <div class="yaml-block">
                    ${unsafeHTML(
                      '<span class="yaml-key">schedule</span>:\n' +
                        '  <span class="yaml-key">cover_evening</span>:\n' +
                        '    <span class="yaml-key">name</span>: <span class="yaml-value">Cover Evening</span>\n' +
                        '    <span class="yaml-key">monday</span>:\n' +
                        '      - <span class="yaml-key">from</span>: <span class="yaml-value">"20:00:00"</span>\n' +
                        '        <span class="yaml-key">to</span>: <span class="yaml-value">"06:00:00"</span>\n' +
                        '        <span class="yaml-key">data</span>:\n' +
                        '          <span class="yaml-key">position</span>: <span class="yaml-value">10</span>',
                    )}
                  </div>
                  <b>${localize("covers.info.solar_title", this.hass.language)}</b><br />
                  ${localize("covers.info.solar_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.night_title", this.hass.language)}</b><br />
                  ${localize("covers.info.night_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.override_title", this.hass.language)}</b><br />
                  ${localize("covers.info.override_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.priority_title", this.hass.language)}</b><br />
                  ${localize("covers.info.priority_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.entities_title", this.hass.language)}</b><br />
                  ${localize("covers.info.entities_body", this.hass.language)}
                </div>
                <rs-covers-section
                  .hass=${this.hass}
                  .area=${this.area}
                  .editing=${this._editingCovers}
                  .selectedCovers=${this._selectedCovers}
                  .autoEnabled=${this._coversAutoEnabled}
                  .deployThreshold=${this._coversDeployThreshold}
                  .minPosition=${this._coversMinPosition}
                  .overrideMinutes=${this._coversOverrideMinutes}
                  .coverSchedules=${this._coverSchedules}
                  .coverScheduleSelectorEntity=${this._coverScheduleSelectorEntity}
                  .activeCoverScheduleIndex=${this.config?.live?.active_cover_schedule_index ?? -1}
                  .nightClose=${this._coversNightClose}
                  .nightPosition=${this._coversNightPosition}
                  .snapDeploy=${this._coversSnapDeploy}
                  .forcedReason=${this.config?.live?.cover_forced_reason ?? ""}
                  .autoPaused=${this.config?.live?.cover_auto_paused ?? false}
                  .coverOrientations=${this._coverOrientations}
                  .nightCloseElevation=${this._coversNightCloseElevation}
                  .nightCloseOffsetMinutes=${this._coversNightCloseOffsetMinutes}
                  .outdoorMinTemp=${this._coversOutdoorMinTemp}
                  .coverMinPositions=${this._coverMinPositions}
                  @covers-toggle=${this._onCoversToggle}
                  @setting-changed=${this._onCoverSettingChanged}
                ></rs-covers-section>
              </rs-section-card>`
            : nothing}
          ${!this._isOutdoor &&
          this._selectedTempSensor &&
          this._devices.some((d) => d.type === "trv") &&
          this._devices.some((d) => d.type === "ac")
            ? html`<rs-section-card
                icon="mdi:swap-horizontal"
                .heading=${localize("room.section.heat_source", this.hass.language)}
              >
                <rs-heat-source-section
                  .hass=${this.hass}
                  .enabled=${this._heatSourceOrchestration}
                  .primaryDelta=${this._heatSourcePrimaryDelta}
                  .outdoorThreshold=${this._heatSourceOutdoorThreshold}
                  .acMinOutdoor=${this._heatSourceAcMinOutdoor}
                  @setting-changed=${this._onHeatSourceSettingChanged}
                ></rs-heat-source-section>
              </rs-section-card>`
            : nothing}

          <ha-card class="outdoor-toggle-card">
            <rs-toggle-row
              .label=${localize("room.outdoor_toggle", this.hass.language)}
              .hint=${localize("room.outdoor_hint", this.hass.language)}
              .checked=${this._isOutdoor}
              @toggle-changed=${this._onOutdoorToggle}
            ></rs-toggle-row>
          </ha-card>
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

  private _onDeviceChanged(e: CustomEvent<{ devices: DeviceConfig[] }>) {
    const oldDeviceIds = new Set(this._devices.map((d) => d.entity_id));
    this._devices = e.detail.devices;
    const newDeviceIds = new Set(this._devices.map((d) => d.entity_id));

    // Clean up valve protection exclude list for removed devices
    for (const eid of oldDeviceIds) {
      if (!newDeviceIds.has(eid) && this._valveProtectionExclude.has(eid)) {
        const nextExclude = new Set(this._valveProtectionExclude);
        nextExclude.delete(eid);
        this._valveProtectionExclude = nextExclude;
      }
    }

    // Moving to non-TRV: remove from valve protection exclude list
    for (const d of this._devices) {
      if (d.type !== "trv" && this._valveProtectionExclude.has(d.entity_id)) {
        const nextExclude = new Set(this._valveProtectionExclude);
        nextExclude.delete(d.entity_id);
        this._valveProtectionExclude = nextExclude;
      }
    }

    this._autoSave();
  }

  private _onSensorChanged(e: CustomEvent<{ key: string; value: string | string[] }>) {
    const { key, value } = e.detail;
    if (key === "temperature_sensor") {
      this._selectedTempSensor = value as string;
    } else if (key === "humidity_sensor") {
      this._selectedHumiditySensor = value as string;
    } else if (key === "occupancy_sensors") {
      this._selectedOccupancySensors = new Set(value as string[]);
    }
    this._autoSave();
  }

  private _onWindowConfigChanged(e: CustomEvent<{ key: string; value: string[] | number }>) {
    const { key, value } = e.detail;
    if (key === "window_sensors") {
      this._selectedWindowSensors = new Set(value as string[]);
    } else if (key === "window_open_delay") {
      this._windowOpenDelay = value as number;
    } else if (key === "window_close_delay") {
      this._windowCloseDelay = value as number;
    }
    this._autoSave();
  }

  private _onValveProtectionExcludeToggle(e: CustomEvent<{ entityId: string; excluded: boolean }>) {
    const { entityId, excluded } = e.detail;
    const next = new Set(this._valveProtectionExclude);
    if (excluded) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this._valveProtectionExclude = next;
    this._autoSave();
  }

  private _onExternalEntityAdded(
    e: CustomEvent<{
      entityId: string;
      category: "temp" | "humidity" | "window" | "occupancy";
    }>,
  ) {
    const { entityId, category } = e.detail;
    if (category === "temp") {
      this._selectedTempSensor = entityId;
    } else if (category === "window") {
      const next = new Set(this._selectedWindowSensors);
      next.add(entityId);
      this._selectedWindowSensors = next;
    } else if (category === "occupancy") {
      const next = new Set(this._selectedOccupancySensors);
      next.add(entityId);
      this._selectedOccupancySensors = next;
    } else {
      this._selectedHumiditySensor = entityId;
    }
    this._autoSave();
  }

  private _onPresencePersonsChanged(e: CustomEvent<string[]>) {
    this._selectedPresencePersons = e.detail;
    this._autoSave();
  }

  private _onIgnorePresenceChanged(e: CustomEvent<boolean>) {
    this._ignorePresence = e.detail;
    this._autoSave();
  }

  private _onPresenceEditingChanged(e: CustomEvent<{ editing: boolean }>) {
    this._editingPresence = e.detail.editing;
  }

  // ---- Cover event handlers ----

  private _onCoversToggle(e: CustomEvent<{ entityId: string; checked: boolean }>) {
    const { entityId, checked } = e.detail;
    const next = new Set(this._selectedCovers);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
      if (entityId in this._coverOrientations) {
        const nextOrientations = { ...this._coverOrientations };
        delete nextOrientations[entityId];
        this._coverOrientations = nextOrientations;
      }
      if (entityId in this._coverMinPositions) {
        const nextMinPositions = { ...this._coverMinPositions };
        delete nextMinPositions[entityId];
        this._coverMinPositions = nextMinPositions;
      }
    }
    this._selectedCovers = next;
    this._autoSave();
  }

  private _onCoverSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    e.stopPropagation();
    if (key === "covers_auto_enabled") this._coversAutoEnabled = value as boolean;
    else if (key === "covers_deploy_threshold") this._coversDeployThreshold = value as number;
    else if (key === "covers_min_position") this._coversMinPosition = value as number;
    else if (key === "covers_override_minutes") this._coversOverrideMinutes = value as number;
    else if (key === "cover_schedules") this._coverSchedules = value as CoverScheduleEntry[];
    else if (key === "cover_schedule_selector_entity")
      this._coverScheduleSelectorEntity = value as string;
    else if (key === "covers_night_close") this._coversNightClose = value as boolean;
    else if (key === "covers_night_position") this._coversNightPosition = value as number;
    else if (key === "covers_snap_deploy") this._coversSnapDeploy = value as boolean;
    else if (key === "cover_orientations")
      this._coverOrientations = value as Record<string, number>;
    else if (key === "covers_night_close_elevation")
      this._coversNightCloseElevation = value as number;
    else if (key === "covers_night_close_offset_minutes")
      this._coversNightCloseOffsetMinutes = value as number;
    else if (key === "covers_outdoor_min_temp") this._coversOutdoorMinTemp = value as number | null;
    else if (key === "cover_min_positions")
      this._coverMinPositions = value as Record<string, number>;
    this._autoSave();
  }

  // ---- Heat source orchestration ----

  private _onHeatSourceSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    e.stopPropagation();
    if (key === "heat_source_orchestration") this._heatSourceOrchestration = value as boolean;
    else if (key === "heat_source_primary_delta") this._heatSourcePrimaryDelta = value as number;
    else if (key === "heat_source_outdoor_threshold")
      this._heatSourceOutdoorThreshold = value as number;
    else if (key === "heat_source_ac_min_outdoor") this._heatSourceAcMinOutdoor = value as number;
    this._autoSave();
  }

  // ---- Outdoor toggle ----

  private _onClimateControlToggle(e: CustomEvent) {
    this._climateControlEnabled = e.detail;
    this._autoSave();
  }

  private _onOutdoorToggle(e: CustomEvent<boolean>) {
    this._isOutdoor = e.detail;
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
    fireSaveStatus(this, "saving");
    this._error = "";

    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: this.area.area_id,
        devices: this._devices,
        temperature_sensor: this._selectedTempSensor,
        humidity_sensor: this._selectedHumiditySensor,
        occupancy_sensors: [...this._selectedOccupancySensors],
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
        presence_persons: this._selectedPresencePersons.filter((p) => p),
        display_name: this._displayName,
        covers: [...this._selectedCovers],
        climate_control_enabled: this._climateControlEnabled,
        covers_auto_enabled: this._coversAutoEnabled,
        covers_deploy_threshold: this._coversDeployThreshold,
        covers_min_position: this._coversMinPosition,
        covers_override_minutes: this._coversOverrideMinutes,
        cover_schedules: this._coverSchedules,
        cover_schedule_selector_entity: this._coverScheduleSelectorEntity,
        covers_night_close: this._coversNightClose,
        covers_night_position: this._coversNightPosition,
        covers_snap_deploy: this._coversSnapDeploy,
        cover_orientations: this._coverOrientations,
        covers_night_close_elevation: this._coversNightCloseElevation,
        covers_night_close_offset_minutes: this._coversNightCloseOffsetMinutes,
        covers_outdoor_min_temp: this._coversOutdoorMinTemp,
        cover_min_positions: this._coverMinPositions,
        ignore_presence: this._ignorePresence,
        is_outdoor: this._isOutdoor,
        valve_protection_exclude: [...this._valveProtectionExclude],
        heat_source_orchestration: this._heatSourceOrchestration,
        heat_source_primary_delta: this._heatSourcePrimaryDelta,
        heat_source_outdoor_threshold: this._heatSourceOutdoorThreshold,
        heat_source_ac_min_outdoor: this._heatSourceAcMinOutdoor,
      });

      this._dirty = false;
      fireSaveStatus(this, "saved");

      this.dispatchEvent(
        new CustomEvent("room-updated", {
          bubbles: true,
          composed: true,
        }),
      );
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : localize("room.error_save_fallback", this.hass.language);
      this._error = message;
      fireSaveStatus(this, "error");
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-detail": RsRoomDetail;
  }
}

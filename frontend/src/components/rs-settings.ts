/**
 * rs-settings – Global RoomMind settings page (orchestrator).
 * Owns all state, loads/saves settings, delegates rendering to sub-components.
 */
import { LitElement, html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, GlobalSettings, RoomConfig, NotificationTarget } from "../types";
import { localize } from "../utils/localize";
import { fireSaveStatus } from "../utils/events";
import "./settings/rs-settings-general";
import "./settings/rs-settings-control";
import "./settings/rs-settings-sensors";
import "./settings/rs-settings-mold";
import "./settings/rs-settings-reset";

@customElement("rs-settings")
export class RsSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _groupByFloor = false;
  @state() private _climateControlActive = true;
  @state() private _learningDisabledRooms: string[] = [];
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
  @state() private _loaded = false;

  private _saveDebounce?: ReturnType<typeof setTimeout>;

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
      const s = result.settings;
      this._groupByFloor = s.group_by_floor ?? false;
      this._climateControlActive = s.climate_control_active ?? true;
      this._learningDisabledRooms = s.learning_disabled_rooms ?? [];
      this._outdoorTempSensor = s.outdoor_temp_sensor ?? "";
      this._outdoorHumiditySensor = s.outdoor_humidity_sensor ?? "";
      this._outdoorCoolingMin = s.outdoor_cooling_min ?? 16;
      this._outdoorHeatingMax = s.outdoor_heating_max ?? 22;
      this._controlMode = s.control_mode ?? "mpc";
      this._comfortWeight = s.comfort_weight ?? 70;
      this._weatherEntity = s.weather_entity ?? "";
      this._predictionEnabled = s.prediction_enabled ?? true;
      const vUntil = s.vacation_until;
      this._vacationActive = !!(vUntil && vUntil > Date.now() / 1000);
      this._vacationTemp = s.vacation_temp ?? 15;
      if (vUntil && vUntil > Date.now() / 1000) {
        this._vacationUntil = this._tsToDatetimeLocal(vUntil);
      }
      this._presenceEnabled = s.presence_enabled ?? false;
      this._presencePersons = s.presence_persons ?? [];
      this._presenceAwayAction = s.presence_away_action ?? "eco";
      this._scheduleOffAction = s.schedule_off_action ?? "eco";
      this._valveProtectionEnabled = s.valve_protection_enabled ?? false;
      this._valveProtectionInterval = s.valve_protection_interval_days ?? 7;
      this._moldDetectionEnabled = s.mold_detection_enabled ?? false;
      this._moldHumidityThreshold = s.mold_humidity_threshold ?? 70;
      this._moldSustainedMinutes = s.mold_sustained_minutes ?? 30;
      this._moldNotificationCooldown = s.mold_notification_cooldown ?? 60;
      this._moldNotificationsEnabled = s.mold_notifications_enabled ?? true;
      this._moldNotificationTargets = s.mold_notification_targets ?? [];
      this._moldPreventionEnabled = s.mold_prevention_enabled ?? false;
      this._moldPreventionIntensity = s.mold_prevention_intensity ?? "medium";
      this._moldPreventionNotify = s.mold_prevention_notify_enabled ?? false;
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

    return html`
      <div class="left-column">
        <rs-settings-general
          .hass=${this.hass}
          .rooms=${this.rooms}
          .groupByFloor=${this._groupByFloor}
          .climateControlActive=${this._climateControlActive}
          .learningDisabledRooms=${this._learningDisabledRooms}
          .scheduleOffAction=${this._scheduleOffAction}
          .vacationActive=${this._vacationActive}
          .vacationTemp=${this._vacationTemp}
          .vacationUntil=${this._vacationUntil}
          .presenceEnabled=${this._presenceEnabled}
          .presencePersons=${this._presencePersons}
          .presenceAwayAction=${this._presenceAwayAction}
          .valveProtectionEnabled=${this._valveProtectionEnabled}
          .valveProtectionInterval=${this._valveProtectionInterval}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-general>
        <rs-settings-control
          .hass=${this.hass}
          .controlMode=${this._controlMode}
          .comfortWeight=${this._comfortWeight}
          .outdoorCoolingMin=${this._outdoorCoolingMin}
          .outdoorHeatingMax=${this._outdoorHeatingMax}
          .predictionEnabled=${this._predictionEnabled}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-control>
      </div>
      <div class="right-column">
        <rs-settings-sensors
          .hass=${this.hass}
          .outdoorTempSensor=${this._outdoorTempSensor}
          .outdoorHumiditySensor=${this._outdoorHumiditySensor}
          .weatherEntity=${this._weatherEntity}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-sensors>
        <rs-settings-mold
          .hass=${this.hass}
          .moldDetectionEnabled=${this._moldDetectionEnabled}
          .moldHumidityThreshold=${this._moldHumidityThreshold}
          .moldSustainedMinutes=${this._moldSustainedMinutes}
          .moldNotificationCooldown=${this._moldNotificationCooldown}
          .moldNotificationsEnabled=${this._moldNotificationsEnabled}
          .moldNotificationTargets=${this._moldNotificationTargets}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionIntensity=${this._moldPreventionIntensity}
          .moldPreventionNotify=${this._moldPreventionNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-mold>
        <rs-settings-reset
          .hass=${this.hass}
          .rooms=${this.rooms}
        ></rs-settings-reset>
      </div>
    `;
  }

  private _onSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    (this as Record<string, unknown>)[`_${key}`] = value;
    this._autoSave();
  }

  private _tsToDatetimeLocal(ts: number): string {
    const d = new Date(ts * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  private _autoSave() {
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this, "saving");

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
      fireSaveStatus(this, "saved");
    } catch {
      fireSaveStatus(this, "error");
    }
  }

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

    .loading {
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    @media (max-width: 600px) {
      :host {
        grid-template-columns: 1fr;
      }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings": RsSettings;
  }
}

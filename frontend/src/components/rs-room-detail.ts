import { LitElement, html, css, nothing } from "lit";
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
import "./room-detail/rs-room-hero";
import "./rs-schedule-settings";
import type { ScheduleCardPart } from "./rs-schedule-settings";
import "./room-detail/rs-target-temps";
import "./room-detail/rs-price-shift";
import "./rs-device-section";
import "./rs-sensor-section";
import "./rs-override-section";
import "./rs-presence-section";
import "./rs-covers-section";
import "./rs-heat-source-section";
import "./shared/rs-edit-dialog";
import "./shared/rs-confirm-dialog";
import "./shared/rs-list-card";
import "./shared/rs-list-row";
import "./shared/rs-segmented";
import {
  coversHelp,
  devicesHelp,
  editDialogHelpStyles,
  presenceHelp,
  heatSourceHelp,
  priceHelp,
  scheduleHelp,
  temperaturesHelp,
} from "./room-detail/edit-dialog-help";
import { localize, type TranslationKey } from "../utils/localize";
import { errorText } from "../utils/errors";
import { showToast } from "../utils/toast";
import { fireSaveStatus } from "../utils/events";
import { resolveHeatingSystemType } from "../utils/device-utils";
import { DEFAULT_OCCUPANCY_ECO_DELAY } from "../utils/constants";
import { NO_OVERRIDE, type EffectiveOverride } from "../utils/override";
import { tokens } from "../styles/tokens";

type EditableSection =
  ScheduleCardPart | "devices" | "sensors" | "presence" | "covers" | "heatSource";

@customElement("rs-room-detail")
export class RsRoomDetail extends LitElement {
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  /** A price source is set in the settings: shows the per-room price options. */
  @property({ type: Boolean }) public priceConfigured = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ type: Boolean }) public climateControlActive = true;
  /** Global: what rooms do while their schedule is off / everybody is away. */
  @property({ type: String }) public scheduleOffAction: "eco" | "off" = "eco";
  @property({ type: String }) public presenceAwayAction: "eco" | "off" = "eco";

  @property({ type: Boolean }) public valveProtectionEnabled = false;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Boolean }) public coilDryEnabled = false;
  @property({ type: Number }) public coilDryMinutes = 20;
  @property({ type: String }) public coilDryMode = "fan_only";
  @property({ type: String }) public coilDryFanMode = "low";
  @property({ attribute: false }) public outdoorTemp: number | null = null;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ attribute: false }) public vacationUntil: number | null = null;

  @state() private _devices: DeviceConfig[] = [];
  @state() private _selectedTempSensor = "";
  @state() private _selectedHumiditySensor = "";
  @state() private _selectedOccupancySensors: Set<string> = new Set();
  @state() private _occupancyEcoEnabled = false;
  @state() private _preheatEnabled = true;
  @state() private _followDeviceSetpoint = false;
  @state() private _priceShift = 0;
  @state() private _heatSourcePriceAware = false;
  @state() private _occupancyEcoDelay = DEFAULT_OCCUPANCY_ECO_DELAY;
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
  @state() private _editing: EditableSection | null = null;
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
  @state() private _coversWindowHold = false;
  @state() private _coverOrientations: Record<string, number> = {};
  @state() private _coversNightCloseElevation = 0;
  @state() private _coversNightCloseOffsetMinutes = 0;
  @state() private _coversOutdoorMinTemp: number | null = 10;
  @state() private _coverMinPositions: Record<string, number> = {};
  @state() private _ignorePresence = false;
  @state() private _isOutdoor = false;
  @state() private _valveProtectionExclude: Set<string> = new Set();
  @state() private _climateControlEnabled = true;
  @state() private _heatSourceOrchestration = false;
  @state() private _heatSourcePrimaryDelta = 1.5;
  @state() private _heatSourceOutdoorThreshold = 5.0;
  @state() private _heatSourceAcMinOutdoor = -15.0;
  @state() private _optimisticCoverResume = false;
  /** Override as the override control shows it (optimistic until the poll confirms). */
  @state() private _override: EffectiveOverride = NO_OVERRIDE;
  /** Device the device dialog opens with. */
  @state() private _focusDevice = "";
  @state() private _confirmDelete = false;
  @state() private _deleting = false;
  @state() private _deleteError = "";

  private _prevAreaId: string | null = null;
  private _saveDebounce?: ReturnType<typeof setTimeout>;

  static styles = [
    tokens,
    editDialogHelpStyles,
    css`
      :host {
        display: block;
        max-width: 1240px;
        margin: 0 auto;
      }

      .layout {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: var(--rs-space-4);
        align-items: start;
      }

      .col {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
        min-width: 0;
      }

      @media (min-width: 960px) {
        .layout {
          grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
        }

        /* sticky only while it fits; a taller column scrolls with the page */
        .col.left {
          position: sticky;
          top: var(--rs-sticky-top, 72px);
          max-height: calc(100vh - var(--rs-sticky-top, 72px) - 16px);
          overflow-y: auto;
          overscroll-behavior: contain;
          scrollbar-width: thin;
        }
      }

      .mode {
        padding: var(--rs-space-1) var(--rs-space-4) var(--rs-space-4);
      }

      .mode-label {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        margin: var(--rs-space-2) 0 6px;
      }

      .mode-desc {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        margin-top: var(--rs-space-2);
        line-height: 1.4;
      }

      .error {
        color: var(--rs-err);
        font-size: 13px;
      }
    `,
  ];

  connectedCallback() {
    super.connectedCallback();
    this._initFromConfig();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    // Leaving the room within the debounce: send the change instead of dropping it
    this._flushSave();
  }

  willUpdate() {
    const currentAreaId = this.config?.area_id ?? this.area?.area_id ?? null;
    // The same element shows another room: the old room's pending edits go to the old room
    if (this._prevAreaId && currentAreaId !== this._prevAreaId) this._flushSave(this._prevAreaId);
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

    if (
      changedProps.has("config") &&
      this._optimisticCoverResume &&
      !this.config?.live?.cover_auto_paused
    ) {
      this._optimisticCoverResume = false;
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
      this._occupancyEcoEnabled = this.config.occupancy_eco_enabled ?? false;
      this._preheatEnabled = this.config.preheat_enabled ?? true;
      this._followDeviceSetpoint = this.config.follow_device_setpoint ?? false;
      this._priceShift = this.config.price_shift ?? 0;
      this._heatSourcePriceAware = this.config.heat_source_price_aware ?? false;
      this._occupancyEcoDelay = this.config.occupancy_eco_delay ?? DEFAULT_OCCUPANCY_ECO_DELAY;
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
      this._coversWindowHold = this.config.covers_window_hold ?? false;
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
      this._occupancyEcoEnabled = false;
      this._preheatEnabled = true;
      this._followDeviceSetpoint = false;
      this._priceShift = 0;
      this._heatSourcePriceAware = false;
      this._occupancyEcoDelay = DEFAULT_OCCUPANCY_ECO_DELAY;
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
      this._coversWindowHold = false;
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

    // Unconfigured rooms open the device-edit dialog automatically; outdoor areas need none.
    if (this._devices.length === 0 && !this._isOutdoor && this._editing === null) {
      this._editing = "devices";
    }
  }

  private _openEdit = (section: EditableSection) => (e?: Event) => {
    e?.stopPropagation();
    this._focusDevice = "";
    this._editing = section;
  };

  private _onScheduleEditClick(e: CustomEvent<{ part?: ScheduleCardPart } | undefined>) {
    e.stopPropagation();
    this._focusDevice = "";
    this._editing = e.detail?.part ?? "schedule";
  }

  private _onDevicesEditClick(e: CustomEvent<{ entityId?: string } | undefined>) {
    e.stopPropagation();
    this._focusDevice = e.detail?.entityId ?? "";
    this._editing = "devices";
  }

  private _closeEdit = () => {
    this._editing = null;
    this._focusDevice = "";
  };

  private _onOverrideState(e: CustomEvent<EffectiveOverride>) {
    e.stopPropagation();
    this._override = e.detail;
  }

  private _onOpenAnalytics() {
    this.dispatchEvent(new CustomEvent("open-analytics", { bubbles: true, composed: true }));
  }

  private _onDeleteClick() {
    this._deleteError = "";
    this._confirmDelete = true;
  }

  private _onDeleteCancel = () => {
    if (this._deleting) return;
    this._confirmDelete = false;
  };

  private async _onDeleteConfirm() {
    this._deleting = true;
    this._deleteError = "";
    try {
      await this.hass.callWS({ type: "roommind/rooms/delete", area_id: this.area.area_id });
      this._confirmDelete = false;
      this.dispatchEvent(new CustomEvent("room-deleted", { bubbles: true, composed: true }));
    } catch (err) {
      const l = this.hass.language;
      this._deleteError = errorText(err, localize("detail.delete_error", l), l);
    } finally {
      this._deleting = false;
    }
  }

  render() {
    if (!this.area) return nothing;
    const l = this.hass.language;
    const outdoor = this._isOutdoor;

    return html`
      <div class="layout">
        <div class="col left">
          <rs-room-hero
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .isOutdoor=${outdoor}
            .overrideInfo=${this._override}
            .climateControlActive=${this.climateControlActive && this._climateControlEnabled}
            .controlMode=${this.controlMode}
            .outdoorTemp=${this.outdoorTemp}
            .vacationActive=${this.vacationActive}
            .vacationUntil=${this.vacationUntil}
            @display-name-changed=${this._onDisplayNameChanged}
          >
            ${
              this.config && !outdoor
                ? html`<rs-override-section
                    slot="control"
                    .hass=${this.hass}
                    .config=${this.config}
                    .climateMode=${this._climateMode}
                    .comfortHeat=${this._comfortHeat}
                    .comfortCool=${this._comfortCool}
                    .ecoHeat=${this._ecoHeat}
                    .ecoCool=${this._ecoCool}
                    .language=${l}
                    .disabled=${!(this.climateControlActive && this._climateControlEnabled)}
                    @override-state=${this._onOverrideState}
                  ></rs-override-section>`
                : nothing
            }
          </rs-room-hero>
          ${outdoor ? nothing : this._renderControlCard()}
        </div>
        <div class="col right">
          ${outdoor ? this._renderSensorsCard() : this._renderSectionCards()}
          ${this._renderRoomCard()}
          ${
            this._error && this._editing === null
              ? html`<div class="error" role="alert">${this._error}</div>`
              : nothing
          }
        </div>
      </div>
      ${this._renderEditDialog()} ${this._renderDeleteDialog()}
    `;
  }

  /** What the room's devices can do; unknown device states count as able. */
  private _deviceAbilities(): { heat: boolean; cool: boolean; mixed: boolean } {
    const modes = (eid: string): string[] | null => {
      const m = this.hass.states[eid]?.attributes?.hvac_modes;
      return Array.isArray(m) ? (m as string[]) : null;
    };
    const can = (eid: string, wanted: string[]) => {
      const m = modes(eid);
      return m === null || m.some((x) => wanted.includes(x));
    };
    const trvs = this._devices.filter((d) => d.type === "trv");
    const acs = this._devices.filter((d) => d.type === "ac");
    return {
      heat: trvs.length > 0 || acs.some((d) => can(d.entity_id, ["heat", "heat_cool", "auto"])),
      cool: acs.some((d) => can(d.entity_id, ["cool", "heat_cool", "auto"])),
      mixed: trvs.length > 0 && acs.length > 0,
    };
  }

  private _renderControlCard() {
    const l = this.hass.language;
    const ability = this._deviceAbilities();
    const judged = this._devices.length > 0;
    const autoDesc: TranslationKey =
      !judged || (ability.heat && ability.cool)
        ? "mode.auto_desc"
        : ability.heat
          ? "mode.auto_desc_heat"
          : "mode.auto_desc_cool";
    const modes: {
      value: ClimateMode;
      key: TranslationKey;
      icon: string;
      desc: TranslationKey;
      fits: boolean;
    }[] = [
      { value: "auto", key: "mode.auto", icon: "mdi:autorenew", desc: autoDesc, fits: true },
      {
        value: "heat_only",
        key: "mode.heat_only",
        icon: "mdi:fire",
        desc: ability.mixed ? "mode.heat_only_desc" : "mode.heat_only_desc_plain",
        fits: !judged || ability.heat,
      },
      {
        value: "cool_only",
        key: "mode.cool_only",
        icon: "mdi:snowflake",
        desc: "mode.cool_only_desc",
        fits: !judged || ability.cool,
      },
    ];
    const current = modes.find((m) => m.value === this._climateMode) ?? modes[0];
    // A stored mode the devices cannot do stays selected and says so; it is not rewritten
    const offered = modes.filter((m) => m.fits || m.value === current.value);
    const secondary = !this.climateControlActive
      ? localize("card.control_off_global", l)
      : localize(this._climateControlEnabled ? "detail.control.on" : "detail.control.off", l);
    return html`<rs-list-card>
      <rs-list-row
        switch
        icon="mdi:power"
        .iconColor=${this._climateControlEnabled && this.climateControlActive ? "var(--primary-color)" : ""}
        .heading=${localize("room.climate_control_toggle", l)}
        .secondary=${secondary}
        .checked=${this._climateControlEnabled}
        @toggle-changed=${this._onClimateControlToggle}
      ></rs-list-row>
      <div class="mode">
        <div class="mode-label">${localize("room.section.climate_mode", l)}</div>
        <rs-segmented
          .label=${localize("room.section.climate_mode", l)}
          .options=${offered.map((m) => ({ value: m.value, label: localize(m.key, l), icon: m.icon }))}
          .value=${this._climateMode}
          @value-changed=${this._onModeChanged}
        ></rs-segmented>
        <div class="mode-desc">
          ${localize(current.fits ? current.desc : "mode.unsupported", l)}
        </div>
      </div>
    </rs-list-card>`;
  }

  private _renderSectionCards() {
    const l = this.hass.language;
    const live = this.config?.live;
    const deviceCount = this._devices.length;
    return html`
      <rs-list-card
        .heading=${localize("room.section.schedule", l)}
        @edit-click=${this._onScheduleEditClick}
      >
        <rs-schedule-settings
          .hass=${this.hass}
          .schedules=${this._schedules}
          .scheduleSelectorEntity=${this._scheduleSelectorEntity}
          .activeScheduleIndex=${live?.active_schedule_index ?? -1}
          .comfortHeat=${this._comfortHeat}
          .comfortCool=${this._comfortCool}
          .ecoHeat=${this._ecoHeat}
          .ecoCool=${this._ecoCool}
          .climateMode=${this._climateMode}
          .scheduleTempWarnings=${live?.schedule_temp_warnings ?? []}
          .preheatEnabled=${this._preheatEnabled}
          .followDeviceSetpoint=${this._followDeviceSetpoint}
          .priceShift=${this._priceShift}
          .priceConfigured=${this.priceConfigured}
          .showPreheat=${this._showPreheat()}
          .scheduleOffAction=${this.scheduleOffAction}
          .presenceAwayAction=${this.presenceAwayAction}
          .presenceActive=${this._presenceActive()}
          .occupancyEco=${this._occupancyEcoEnabled && this._selectedOccupancySensors.size > 0}
          .editing=${false}
          @preheat-changed=${this._onPreheatChanged}
          @follow-device-setpoint-changed=${this._onFollowDeviceSetpointChanged}
        ></rs-schedule-settings>
      </rs-list-card>

      <rs-list-card
        .heading=${localize("room.section.devices", l)}
        .aside=${deviceCount ? localize(deviceCount === 1 ? "detail.devices.count_one" : "detail.devices.count", l, { count: deviceCount }) : ""}
        @edit-click=${this._onDevicesEditClick}
      >
        <rs-device-section
          .hass=${this.hass}
          .area=${this.area}
          .editing=${false}
          .devices=${this._devices}
          .selectedTempSensor=${this._selectedTempSensor}
          .valveProtectionExclude=${this._valveProtectionExclude}
          .valveProtectionEnabled=${this.valveProtectionEnabled}
          .coilDryEnabledGlobal=${this.coilDryEnabled}
          .coilDryMinutesGlobal=${this.coilDryMinutes}
          .coilDryModeGlobal=${this.coilDryMode}
          .coilDryFanModeGlobal=${this.coilDryFanMode}
        ></rs-device-section>
      </rs-list-card>

      ${this._renderSensorsCard()}
      ${
        this.presenceEnabled || this._selectedPresencePersons.length > 0 || this._ignorePresence
          ? html`<rs-list-card
              .heading=${localize("room.section.presence", l)}
              .info=${localize("presence.persons_info", l)}
              @edit-click=${this._openEdit("presence")}
            >
              <rs-presence-section
                .hass=${this.hass}
                .presenceEnabled=${this.presenceEnabled}
                .presencePersons=${this.presencePersons}
                .selectedPresencePersons=${this._selectedPresencePersons}
                .ignorePresence=${this._ignorePresence}
                .awayAction=${this.presenceAwayAction}
                .editing=${false}
                .language=${l}
              ></rs-presence-section>
            </rs-list-card>`
          : nothing
      }

      <rs-list-card
        .heading=${localize("room.section.covers", l)}
        @edit-click=${this._openEdit("covers")}
      >
        <rs-covers-section
          .hass=${this.hass}
          .area=${this.area}
          .editing=${false}
          .selectedCovers=${this._selectedCovers}
          .autoEnabled=${this._coversAutoEnabled}
          .forcedReason=${live?.cover_forced_reason ?? ""}
          .coverReason=${live?.cover_reason ?? ""}
          .autoPaused=${this._optimisticCoverResume ? false : (live?.cover_auto_paused ?? false)}
          .overrideUntil=${live?.cover_override_until ?? null}
          .coverOrientations=${this._coverOrientations}
          .coverMinPositions=${this._coverMinPositions}
          @cover-resume-auto=${this._onCoverResumeAuto}
        ></rs-covers-section>
      </rs-list-card>

      ${
        this._selectedTempSensor &&
        this._climateMode !== "cool_only" &&
        this._devices.some((d) => d.type === "trv") &&
        this._devices.some((d) => d.type === "ac")
          ? html`<rs-list-card
              .heading=${localize("room.section.heat_source", l)}
              @edit-click=${this._openEdit("heatSource")}
            >
              <rs-heat-source-section
                .hass=${this.hass}
                .editing=${false}
                .enabled=${this._heatSourceOrchestration}
                .primaryDelta=${this._heatSourcePrimaryDelta}
                .outdoorThreshold=${this._heatSourceOutdoorThreshold}
                .acMinOutdoor=${this._heatSourceAcMinOutdoor}
                .priceAware=${this._heatSourcePriceAware}
                .priceConfigured=${this.priceConfigured}
                .outdoorTemp=${this.outdoorTemp}
                .climateMode=${this._climateMode}
              ></rs-heat-source-section>
            </rs-list-card>`
          : nothing
      }
    `;
  }

  private _renderSensorsCard() {
    const l = this.hass.language;
    return html`<rs-list-card
      .heading=${localize("room.section.sensors", l)}
      @edit-click=${this._openEdit("sensors")}
    >
      <rs-sensor-section
        .hass=${this.hass}
        .area=${this.area}
        .editing=${false}
        .outdoor=${this._isOutdoor}
        .temperatureSensor=${this._selectedTempSensor}
        .humiditySensor=${this._selectedHumiditySensor}
        .occupancySensors=${this._selectedOccupancySensors}
        .occupancyEcoEnabled=${this._occupancyEcoEnabled}
        .occupancyEcoDelay=${this._occupancyEcoDelay}
        .windowSensors=${this._selectedWindowSensors}
        .windowOpenDelay=${this._windowOpenDelay}
        .windowCloseDelay=${this._windowCloseDelay}
        .heatingSystemType=${resolveHeatingSystemType(this._devices)}
        .language=${l}
      ></rs-sensor-section>
    </rs-list-card>`;
  }

  /** Outdoor flag, analytics and removal: there for every room, outdoor ones included. */
  private _renderRoomCard() {
    const l = this.hass.language;
    return html`<rs-list-card>
      <rs-list-row
        switch
        icon="mdi:tree"
        .heading=${localize("room.outdoor_toggle", l)}
        .secondary=${localize("room.outdoor_hint", l)}
        .checked=${this._isOutdoor}
        @toggle-changed=${this._onOutdoorToggle}
      ></rs-list-row>
      ${
        this.config
          ? html`<rs-list-row
                clickable
                chevron
                icon="mdi:chart-line"
                .heading=${localize("detail.analytics", l)}
                .secondary=${localize(
                  this._isOutdoor ? "detail.analytics_sub_outdoor" : "detail.analytics_sub",
                  l,
                )}
                @row-click=${this._onOpenAnalytics}
              ></rs-list-row>
              <rs-list-row
                clickable
                variant="danger"
                icon="mdi:delete-outline"
                .heading=${localize("detail.delete", l)}
                .secondary=${localize("detail.delete_sub", l)}
                @row-click=${this._onDeleteClick}
              ></rs-list-row>`
          : nothing
      }
    </rs-list-card>`;
  }

  private _renderDeleteDialog() {
    if (!this._confirmDelete) return nothing;
    const l = this.hass.language;
    const name = this.config?.display_name || this.area.name;
    return html`<rs-confirm-dialog
      open
      icon="mdi:delete-outline"
      .heading=${localize("detail.delete_title", l)}
      .message=${localize("detail.delete_body", l, { name })}
      .confirmLabel=${localize("detail.delete_confirm", l)}
      .busy=${this._deleting}
      .error=${this._deleteError}
      @cancel=${this._onDeleteCancel}
      @confirm=${this._onDeleteConfirm}
    ></rs-confirm-dialog>`;
  }

  private _renderEditDialog() {
    if (this._editing === null) return nothing;
    const lang = this.hass.language;

    switch (this._editing) {
      case "schedule":
        return html`<rs-edit-dialog
          open
          icon="mdi:calendar-clock"
          .heading=${localize("detail.schedule.dialog_schedule", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${scheduleHelp(lang)}
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
            .scheduleTempWarnings=${this.config?.live?.schedule_temp_warnings ?? []}
            .editing=${true}
            .roomName=${this._displayName || this.area.name}
            @schedules-changed=${this._onSchedulesChanged}
            @schedule-selector-changed=${this._onScheduleSelectorChanged}
            @open-schedule-editor=${this._onOpenScheduleEditor}
          ></rs-schedule-settings>
        </rs-edit-dialog>`;
      case "temperatures":
        return html`<rs-edit-dialog
          open
          icon="mdi:thermometer"
          .heading=${localize("detail.schedule.dialog_temps", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${temperaturesHelp(lang)}
          <rs-target-temps
            .hass=${this.hass}
            .comfortHeat=${this._comfortHeat}
            .comfortCool=${this._comfortCool}
            .ecoHeat=${this._ecoHeat}
            .ecoCool=${this._ecoCool}
            .climateMode=${this._climateMode}
            @comfort-heat-changed=${this._onComfortHeatChanged}
            @comfort-cool-changed=${this._onComfortCoolChanged}
            @eco-heat-changed=${this._onEcoHeatChanged}
            @eco-cool-changed=${this._onEcoCoolChanged}
          ></rs-target-temps>
        </rs-edit-dialog>`;
      case "price":
        return html`<rs-edit-dialog
          open
          icon="mdi:cash-clock"
          .heading=${localize("schedule.price_shift_label", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${priceHelp(lang)}
          <rs-price-shift
            .hass=${this.hass}
            .priceShift=${this._priceShift}
            .climateMode=${this._climateMode}
            .priceLevel=${this.config?.live?.price_level ?? null}
            .shiftHeat=${this.config?.live?.price_shift_heat ?? 0}
            .shiftCool=${this.config?.live?.price_shift_cool ?? 0}
            @price-shift-changed=${this._onPriceShiftChanged}
          ></rs-price-shift>
        </rs-edit-dialog>`;
      case "devices":
        return html`<rs-edit-dialog
          open
          icon="mdi:power-plug"
          .heading=${localize("room.section.devices", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${devicesHelp(lang)}
          <rs-device-section
            .hass=${this.hass}
            .area=${this.area}
            .editing=${true}
            .focusEntity=${this._focusDevice}
            .devices=${this._devices}
            .selectedTempSensor=${this._selectedTempSensor}
            .valveProtectionExclude=${this._valveProtectionExclude}
            .valveProtectionEnabled=${this.valveProtectionEnabled}
            .coilDryEnabledGlobal=${this.coilDryEnabled}
            .coilDryMinutesGlobal=${this.coilDryMinutes}
            .coilDryModeGlobal=${this.coilDryMode}
            .coilDryFanModeGlobal=${this.coilDryFanMode}
            @device-changed=${this._onDeviceChanged}
            @valve-protection-exclude-toggle=${this._onValveProtectionExcludeToggle}
          ></rs-device-section>
        </rs-edit-dialog>`;
      case "sensors":
        return html`<rs-edit-dialog
          open
          icon="mdi:thermometer"
          .heading=${localize("room.section.sensors", lang)}
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          <rs-sensor-section
            .hass=${this.hass}
            .area=${this.area}
            .editing=${true}
            .outdoor=${this._isOutdoor}
            .temperatureSensor=${this._selectedTempSensor}
            .humiditySensor=${this._selectedHumiditySensor}
            .occupancySensors=${this._selectedOccupancySensors}
            .occupancyEcoEnabled=${this._occupancyEcoEnabled}
            .occupancyEcoDelay=${this._occupancyEcoDelay}
            .windowSensors=${this._selectedWindowSensors}
            .windowOpenDelay=${this._windowOpenDelay}
            .windowCloseDelay=${this._windowCloseDelay}
            .heatingSystemType=${resolveHeatingSystemType(this._devices)}
            .language=${this.hass.language}
            @sensor-changed=${this._onSensorChanged}
          ></rs-sensor-section>
        </rs-edit-dialog>`;
      case "presence":
        return html`<rs-edit-dialog
          open
          icon="mdi:home-account"
          .heading=${localize("room.section.presence", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${presenceHelp(lang)}
          <rs-presence-section
            .hass=${this.hass}
            .presenceEnabled=${this.presenceEnabled}
            .presencePersons=${this.presencePersons}
            .selectedPresencePersons=${this._selectedPresencePersons}
            .ignorePresence=${this._ignorePresence}
            .awayAction=${this.presenceAwayAction}
            .editing=${true}
            .language=${this.hass.language}
            @presence-persons-changed=${this._onPresencePersonsChanged}
            @ignore-presence-changed=${this._onIgnorePresenceChanged}
          ></rs-presence-section>
        </rs-edit-dialog>`;
      case "covers":
        return html`<rs-edit-dialog
          open
          icon="mdi:blinds-horizontal"
          .heading=${localize("room.section.covers", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${coversHelp(lang)}
          <rs-covers-section
            .hass=${this.hass}
            .area=${this.area}
            .editing=${true}
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
            .coverReason=${this.config?.live?.cover_reason ?? ""}
            .windowHold=${this._coversWindowHold}
            .hasWindowSensors=${this._selectedWindowSensors.size > 0}
            .autoPaused=${
              this._optimisticCoverResume ? false : (this.config?.live?.cover_auto_paused ?? false)
            }
            .overrideUntil=${this.config?.live?.cover_override_until ?? null}
            .coverOrientations=${this._coverOrientations}
            .nightCloseElevation=${this._coversNightCloseElevation}
            .nightCloseOffsetMinutes=${this._coversNightCloseOffsetMinutes}
            .outdoorMinTemp=${this._coversOutdoorMinTemp}
            .coverMinPositions=${this._coverMinPositions}
            @covers-toggle=${this._onCoversToggle}
            @setting-changed=${this._onCoverSettingChanged}
            @cover-resume-auto=${this._onCoverResumeAuto}
          ></rs-covers-section>
        </rs-edit-dialog>`;
      case "heatSource":
        return html`<rs-edit-dialog
          open
          icon="mdi:swap-horizontal"
          .heading=${localize("room.section.heat_source", lang)}
          hasInfo
          .error=${this._error}
          @rs-dialog-closed=${this._closeEdit}
        >
          ${heatSourceHelp(lang)}
          <rs-heat-source-section
            .hass=${this.hass}
            .editing=${true}
            .enabled=${this._heatSourceOrchestration}
            .primaryDelta=${this._heatSourcePrimaryDelta}
            .outdoorThreshold=${this._heatSourceOutdoorThreshold}
            .acMinOutdoor=${this._heatSourceAcMinOutdoor}
            .priceAware=${this._heatSourcePriceAware}
            .priceConfigured=${this.priceConfigured}
            .outdoorTemp=${this.outdoorTemp}
            .climateMode=${this._climateMode}
            @setting-changed=${this._onHeatSourceSettingChanged}
          ></rs-heat-source-section>
        </rs-edit-dialog>`;
    }
  }

  // ---- Child event handlers ----

  private _onModeChanged(e: CustomEvent<{ value: ClimateMode }>) {
    e.stopPropagation();
    this._climateMode = e.detail.value;
    this._autoSave();
  }

  /**
   * The schedule dialog opens the editor page: a pending room save (e.g. the just created
   * helper's assignment) goes out first, the page switch unmounts this element.
   */
  private async _onOpenScheduleEditor(e: CustomEvent<{ entityId: string }>) {
    e.stopPropagation();
    if (this._saveDebounce) {
      clearTimeout(this._saveDebounce);
      this._saveDebounce = undefined;
      await this._doSave();
    }
    this._editing = null;
    this.dispatchEvent(
      new CustomEvent("open-schedule-editor", {
        detail: { entityId: e.detail.entityId, areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onSchedulesChanged(e: CustomEvent<{ value: ScheduleEntry[] }>) {
    const before = this._schedules;
    const next = e.detail.value;
    this._schedules = next;
    this._autoSave();
    // Removing is easily undone, so it asks nothing and offers Undo instead
    const removed = before.find((s) => !next.some((n) => n.entity_id === s.entity_id));
    if (removed && next.length < before.length) {
      const l = this.hass.language;
      const name =
        (this.hass.states[removed.entity_id]?.attributes?.friendly_name as string) ||
        removed.entity_id;
      showToast(this, localize("schedule.removed", l, { name }), l, () => {
        this._schedules = before;
        this._autoSave();
      });
    }
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

  /** Presence detection switches this room: on globally, someone to watch, not ignored. */
  private _presenceActive(): boolean {
    if (!this.presenceEnabled || this._ignorePresence) return false;
    return (this._selectedPresencePersons.length || this.presencePersons.length) > 0;
  }

  /**
   * Only where the pre-heat lead applies: MPC with a room sensor, not cool_only. Underfloor
   * heating pre-heats through its own control, unless an orchestrated AC heats the room.
   */
  private _showPreheat(): boolean {
    if (
      // Without a schedule or price shift there is no warmer block to start early for
      (!this._schedules.length && !(this._priceShift > 0)) ||
      this.controlMode !== "mpc" ||
      !this._selectedTempSensor ||
      this._climateMode === "cool_only"
    ) {
      return false;
    }
    const acHeats = this._heatSourceOrchestration && this._devices.some((d) => d.type === "ac");
    return resolveHeatingSystemType(this._devices) !== "underfloor" || acHeats;
  }

  private _onPreheatChanged(e: CustomEvent<{ value: boolean }>) {
    this._preheatEnabled = e.detail.value;
    this._autoSave();
  }

  private _onPriceShiftChanged(e: CustomEvent<{ value: number }>) {
    this._priceShift = e.detail.value;
    this._autoSave();
  }

  private _onFollowDeviceSetpointChanged(e: CustomEvent<{ value: boolean }>) {
    this._followDeviceSetpoint = e.detail.value;
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

  private _onSensorChanged(
    e: CustomEvent<{ key: string; value: string | string[] | number | boolean }>,
  ) {
    const { key, value } = e.detail;
    if (key === "temperature_sensor") {
      this._selectedTempSensor = value as string;
    } else if (key === "humidity_sensor") {
      this._selectedHumiditySensor = value as string;
    } else if (key === "occupancy_sensors") {
      this._selectedOccupancySensors = new Set(value as string[]);
    } else if (key === "occupancy_eco_enabled") {
      this._occupancyEcoEnabled = value as boolean;
    } else if (key === "occupancy_eco_delay") {
      this._occupancyEcoDelay = value as number;
    } else if (key === "window_sensors") {
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

  private _onPresencePersonsChanged(e: CustomEvent<string[]>) {
    this._selectedPresencePersons = e.detail;
    this._autoSave();
  }

  private _onIgnorePresenceChanged(e: CustomEvent<boolean>) {
    this._ignorePresence = e.detail;
    this._autoSave();
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

  /** Lives here, not in the dialog: Undo still works after the dialog was closed. */
  private _onCoverSchedules(next: CoverScheduleEntry[]) {
    const before = this._coverSchedules;
    this._coverSchedules = next;
    const removed = before.find((s) => !next.some((n) => n.entity_id === s.entity_id));
    if (!removed || next.length >= before.length) return;
    const l = this.hass.language;
    const name =
      (this.hass.states[removed.entity_id]?.attributes?.friendly_name as string) ||
      removed.entity_id;
    showToast(this, localize("covers.schedule_removed", l, { name }), l, () => {
      this._coverSchedules = before;
      this._autoSave();
    });
  }

  private _onCoverSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    e.stopPropagation();
    if (key === "covers_auto_enabled") this._coversAutoEnabled = value as boolean;
    else if (key === "covers_deploy_threshold") this._coversDeployThreshold = value as number;
    else if (key === "covers_min_position") this._coversMinPosition = value as number;
    else if (key === "covers_override_minutes") this._coversOverrideMinutes = value as number;
    else if (key === "cover_schedules") this._onCoverSchedules(value as CoverScheduleEntry[]);
    else if (key === "cover_schedule_selector_entity")
      this._coverScheduleSelectorEntity = value as string;
    else if (key === "covers_night_close") this._coversNightClose = value as boolean;
    else if (key === "covers_night_position") this._coversNightPosition = value as number;
    else if (key === "covers_snap_deploy") this._coversSnapDeploy = value as boolean;
    else if (key === "covers_window_hold") this._coversWindowHold = value as boolean;
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

  private async _onCoverResumeAuto() {
    this._optimisticCoverResume = true;
    try {
      await this.hass.callWS({
        type: "roommind/covers/clear_override",
        area_id: this.area.area_id,
      });
    } catch (err) {
      this._optimisticCoverResume = false;
      const l = this.hass.language;
      this._error = errorText(err, localize("room.error_save_fallback", l), l);
    }
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
    else if (key === "heat_source_price_aware") this._heatSourcePriceAware = value as boolean;
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
    this._saveDebounce = setTimeout(() => {
      this._saveDebounce = undefined;
      void this._doSave();
    }, 500);
  }

  private _flushSave(areaId?: string) {
    if (!this._saveDebounce) return;
    clearTimeout(this._saveDebounce);
    this._saveDebounce = undefined;
    void this._doSave(areaId);
  }

  private async _doSave(areaId: string = this.area.area_id) {
    fireSaveStatus(this, "saving");
    this._error = "";

    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: areaId,
        devices: this._devices,
        temperature_sensor: this._selectedTempSensor,
        humidity_sensor: this._selectedHumiditySensor,
        occupancy_sensors: [...this._selectedOccupancySensors],
        occupancy_eco_enabled: this._occupancyEcoEnabled,
        occupancy_eco_delay: this._occupancyEcoDelay,
        preheat_enabled: this._preheatEnabled,
        follow_device_setpoint: this._followDeviceSetpoint,
        price_shift: this._priceShift,
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
        covers_window_hold: this._coversWindowHold,
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
        heat_source_price_aware: this._heatSourcePriceAware,
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
      const l = this.hass.language;
      this._error = errorText(err, localize("room.error_save_fallback", l), l);
      fireSaveStatus(this, "error");
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-detail": RsRoomDetail;
  }
}

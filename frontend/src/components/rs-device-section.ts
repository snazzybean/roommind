import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, DeviceConfig, DeviceType } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";
import { resolveHeatingSystemType } from "../utils/device-utils";
import { masterDetailStyles } from "../styles/master-detail-styles";
import { inputStyles } from "../styles/input-styles";
import "./shared/rs-master-detail";
import "./shared/rs-info-icon";

/**
 * UI-only sentinel for "inherit the global setting".  ha-select cannot render an
 * option whose value is the empty string, so the stored "" would show up as a
 * blank field.  Mapped back to "" on save; "__keep__" keeps its own meaning
 * (send no fan mode at all) and must not be folded into this.
 */
const INHERIT = "__inherit__";

const fromInherit = (value: string | undefined): string => (value === INHERIT ? "" : (value ?? ""));

@customElement("rs-device-section")
export class RsDeviceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public devices: DeviceConfig[] = [];
  @property({ type: String }) public selectedTempSensor = "";
  @property({ attribute: false }) public valveProtectionExclude: Set<string> = new Set();
  @property({ type: Boolean }) public valveProtectionEnabled = false;
  @property({ type: Boolean }) public coilDryEnabledGlobal = false;
  @property({ type: Number }) public coilDryMinutesGlobal = 20;
  @property({ type: String }) public coilDryModeGlobal = "fan_only";
  @property({ type: String }) public coilDryFanModeGlobal = "low";

  @property({ type: Boolean }) public editing = false;
  @state() private _systemTypeInfoExpanded = false;
  @state() private _showBoostHint = false;
  @state() private _selectedThermostats: Set<string> = new Set();
  @state() private _selectedCoolingDevices: Set<string> = new Set();
  @state() private _heatingSystemType = "";
  @state() private _selectedForEdit = "";

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has("devices")) {
      this._selectedThermostats = new Set(
        this.devices.filter((d) => d.type === "trv").map((d) => d.entity_id),
      );
      this._selectedCoolingDevices = new Set(
        this.devices.filter((d) => d.type === "ac").map((d) => d.entity_id),
      );
      this._heatingSystemType = resolveHeatingSystemType(this.devices);

      // Keep _selectedForEdit valid: clear if device was removed,
      // auto-select first device when nothing is selected.
      const inRoom = new Set(this.devices.map((d) => d.entity_id));
      if (this._selectedForEdit && !inRoom.has(this._selectedForEdit)) {
        this._selectedForEdit = "";
      }
      if (!this._selectedForEdit && this.devices.length > 0) {
        this._selectedForEdit = this.devices[0].entity_id;
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

      .section-subtitle {
        font-size: 12px;
        font-weight: 500;
        color: var(--secondary-text-color);
        margin: 12px 0 8px 0;
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }

      .section-subtitle:first-child {
        margin-top: 0;
      }

      .device-group {
        padding: 4px 0;
      }

      .device-group + .device-group {
        margin-top: 8px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, #eee);
      }

      .device-list-scroll {
        max-height: 168px;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-width: thin;
      }

      /* Device rows */
      .device-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 14px;
        font-size: 14px;
        color: var(--primary-text-color);
        border-radius: 10px;
        margin-bottom: 2px;
        transition: background 0.15s;
      }

      .device-row:last-child {
        margin-bottom: 0;
      }

      .device-row:hover {
        background: rgba(0, 0, 0, 0.02);
      }

      .device-row.selected {
        background: rgba(3, 169, 244, 0.035);
      }

      .device-row ha-checkbox,
      .device-row ha-radio {
        flex-shrink: 0;
      }

      .device-info {
        flex: 1;
        min-width: 0;
      }

      .device-name-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .device-name {
        font-size: 14px;
        font-weight: 450;
        color: var(--primary-text-color);
      }

      .device-value {
        margin-left: auto;
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color);
        flex-shrink: 0;
      }

      .device-entity {
        font-family: var(--code-font-family, monospace);
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 2px;
        opacity: 0.7;
      }

      .external-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 10px;
        font-weight: 500;
        color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.1);
        padding: 2px 8px;
        border-radius: 10px;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        flex-shrink: 0;
      }

      .device-type-select {
        flex-shrink: 0;
        --ha-select-min-width: 90px;
      }

      .no-devices {
        color: var(--secondary-text-color);
        font-size: 13px;
        font-style: italic;
        padding: 12px 14px;
      }

      .entity-picker-wrap {
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, #eee);
      }

      .subtitle-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .info-icon {
        --mdc-icon-size: 16px;
        color: var(--secondary-text-color);
        cursor: pointer;
        opacity: 0.6;
      }
      .info-icon:hover,
      .info-icon.info-active {
        opacity: 1;
        color: var(--primary-color);
      }

      .system-type-info {
        font-size: 12px;
        line-height: 1.5;
        color: var(--secondary-text-color);
        padding: 8px 14px 4px;
      }

      .boost-hint {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-top: 8px;
        padding: 8px 12px;
        background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
        border-radius: 8px;
        font-size: 13px;
        color: var(--primary-text-color);
        line-height: 1.4;
        --mdc-icon-size: 18px;
      }
      .boost-hint ha-icon {
        color: var(--primary-color);
        flex-shrink: 0;
        margin-top: 1px;
      }

      .idle-action-row {
        display: flex;
        gap: 12px;
        padding: 4px 14px 4px 42px;
      }

      .idle-action-row ha-select {
        flex: 1;
        min-width: 0;
      }

      .setpoint-mode-row {
        display: flex;
        gap: 12px;
        padding: 4px 14px 4px 42px;
      }

      .setpoint-mode-row ha-select {
        flex: 1;
        min-width: 0;
      }

      .setpoint-mode-hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        padding: 2px 14px 4px 42px;
      }

      .valve-exclude-row {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 2px 14px 2px 42px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .valve-exclude-row ha-icon {
        --mdc-icon-size: 14px;
        color: var(--secondary-text-color);
      }

      .valve-exclude-row ha-checkbox {
        --mdc-checkbox-unchecked-color: var(--secondary-text-color);
        margin: -8px -4px -8px -8px;
      }

      .valve-exclude-badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        font-size: 10px;
        font-weight: 500;
        color: var(--secondary-text-color);
        background: var(--secondary-background-color);
        padding: 2px 6px;
        border-radius: 8px;
        --mdc-icon-size: 12px;
      }

      /* View mode styles */
      .view-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 14px;
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

      .entity-link {
        cursor: pointer;
      }

      .entity-link:hover {
        text-decoration: underline;
      }

      .view-value {
        font-weight: 500;
        flex-shrink: 0;
      }
    `,
  ];

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  private _renderViewMode() {
    const hasClimate = this._selectedThermostats.size > 0 || this._selectedCoolingDevices.size > 0;

    return html`
      ${hasClimate
        ? html`
            <div class="device-group">
              <div class="section-subtitle">
                ${localize("devices.climate_entities", this.hass.language)}
              </div>
              ${[...this._selectedThermostats].map((id) => this._renderViewRow(id, "climate"))}
              ${[...this._selectedCoolingDevices].map((id) => this._renderViewRow(id, "climate"))}
            </div>
          `
        : nothing}
      ${this._heatingSystemType
        ? html`
            <div class="device-group">
              <div class="section-subtitle">
                ${localize("devices.heating_system_type", this.hass.language)}
              </div>
              <div class="view-row">
                <span class="view-name"
                  >${this._heatingSystemType === "radiator"
                    ? localize("devices.system_type_radiator", this.hass.language)
                    : this._heatingSystemType === "underfloor"
                      ? localize("devices.system_type_underfloor", this.hass.language)
                      : this._heatingSystemType}</span
                >
              </div>
            </div>
          `
        : nothing}
    `;
  }

  private _renderViewRow(entityId: string, type: "climate" | "temp" | "humidity") {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const state = entityState?.state;
    const attrs = entityState?.attributes ?? {};

    let displayValue = "";
    if (type === "climate") {
      const ct = attrs.current_temperature as number | undefined;
      if (ct != null) displayValue = `${ct.toFixed(1)}${tempUnit(this.hass)}`;
    } else if (type === "temp") {
      const tempVal = entityId.startsWith("climate.") ? attrs.current_temperature : state;
      if (tempVal != null && tempVal !== "" && tempVal !== "unknown" && tempVal !== "unavailable")
        displayValue = `${Number(tempVal).toFixed(1)}${tempUnit(this.hass)}`;
    } else {
      if (state && state !== "unknown" && state !== "unavailable")
        displayValue = `${Math.round(Number(state))}%`;
    }

    const showExcludeBadge =
      type === "climate" &&
      this.valveProtectionEnabled &&
      this.valveProtectionExclude.has(entityId);

    const device =
      type === "climate" ? this.devices.find((d) => d.entity_id === entityId) : undefined;
    const showIdleBadge =
      device?.idle_action === "fan_only" ||
      device?.idle_action === "setback" ||
      device?.idle_action === "low";
    const showDirectBadge = device?.setpoint_mode === "direct" && !!this.selectedTempSensor;

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this, entityId)}
          >${friendlyName}</span
        >
        ${showIdleBadge
          ? html`<span class="valve-exclude-badge">
              ${device!.idle_action === "fan_only"
                ? html`${localize("devices.idle_action_fan_only", this.hass.language)}${device!
                    .idle_fan_mode
                    ? ` (${device!.idle_fan_mode})`
                    : nothing}`
                : device!.idle_action === "low"
                  ? localize("devices.idle_action_low", this.hass.language)
                  : localize("devices.idle_action_setback", this.hass.language)}
            </span>`
          : nothing}
        ${showDirectBadge
          ? html`<span class="valve-exclude-badge">
              ${localize("devices.setpoint_mode_direct", this.hass.language)}
            </span>`
          : nothing}
        ${showExcludeBadge
          ? html`<span class="valve-exclude-badge">
              <ha-icon icon="mdi:shield-off-outline"></ha-icon>
              ${localize("devices.valve_protection_excluded", this.hass.language)}
            </span>`
          : nothing}
        ${displayValue ? html`<span class="view-value">${displayValue}</span>` : nothing}
      </div>
    `;
  }

  private _renderEditMode() {
    const allAreaEntities = getEntitiesForArea(
      this.area.area_id,
      this.hass?.entities,
      this.hass?.devices,
    ).filter((e) => {
      const idAfterDot = e.entity_id.substring(e.entity_id.indexOf(".") + 1);
      return !idAfterDot.startsWith("roommind_");
    });

    const areaClimateEntities = allAreaEntities.filter((e) => e.entity_id.startsWith("climate."));
    const areaClimateIds = new Set(areaClimateEntities.map((e) => e.entity_id));
    const allSelectedClimate = new Set(this.devices.map((d) => d.entity_id));
    const externalClimateIds = [...allSelectedClimate].filter((id) => !areaClimateIds.has(id));

    const inRoom = (id: string) => allSelectedClimate.has(id);
    const detailId = this._selectedForEdit;

    return html`
      <rs-master-detail>
        <div slot="master" class="master">
          <div class="section-subtitle">
            ${localize("devices.climate_entities", this.hass.language)}
          </div>
          <div class="master-list">
            ${areaClimateEntities.length > 0
              ? areaClimateEntities.map((e) => this._renderMasterRow(e.entity_id, false))
              : html`<div class="no-devices">
                  ${localize("devices.no_climate", this.hass.language)}
                </div>`}
            ${externalClimateIds.map((id) => this._renderMasterRow(id, true))}
          </div>
          <div class="entity-picker-wrap">
            <ha-entity-picker
              .hass=${this.hass}
              .includeDomains=${["climate"]}
              .entityFilter=${this._entityFilter}
              .value=${""}
              label=${localize("devices.add_entity", this.hass.language)}
              @value-changed=${this._onEntityPicked}
            ></ha-entity-picker>
          </div>
        </div>

        <div slot="detail" class="detail-panel">
          ${detailId && inRoom(detailId)
            ? this._renderDeviceDetail(detailId)
            : html`<div class="empty-detail">
                <ha-icon icon="mdi:gesture-tap"></ha-icon>
                <span>${localize("devices.select_to_configure", this.hass.language)}</span>
              </div>`}
        </div>
      </rs-master-detail>

      ${this._selectedThermostats.size > 0
        ? html`
            <div class="block-divider"></div>
            <div class="block">
              <div class="subtitle-row">
                <div class="section-subtitle">
                  ${localize("devices.heating_system_type", this.hass.language)}
                </div>
                <ha-icon
                  class="info-icon ${this._systemTypeInfoExpanded ? "info-active" : ""}"
                  icon="mdi:information-outline"
                  @click=${() => {
                    this._systemTypeInfoExpanded = !this._systemTypeInfoExpanded;
                  }}
                ></ha-icon>
              </div>
              ${this._systemTypeInfoExpanded
                ? html`
                    <div class="system-type-info">
                      ${localize("devices.heating_system_type_info", this.hass.language)}
                    </div>
                  `
                : nothing}
              <ha-select
                .value=${this._heatingSystemType || "standard"}
                .options=${[
                  {
                    value: "standard",
                    label: localize("devices.system_type_none", this.hass.language),
                  },
                  {
                    value: "radiator",
                    label: localize("devices.system_type_radiator", this.hass.language),
                  },
                  {
                    value: "underfloor",
                    label: localize("devices.system_type_underfloor", this.hass.language),
                  },
                ]}
                @selected=${this._onHeatingSystemTypeChange}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
                style="width: 100%;"
              >
                <ha-list-item value="standard"
                  >${localize("devices.system_type_none", this.hass.language)}</ha-list-item
                >
                <ha-list-item value="radiator"
                  >${localize("devices.system_type_radiator", this.hass.language)}</ha-list-item
                >
                <ha-list-item value="underfloor"
                  >${localize("devices.system_type_underfloor", this.hass.language)}</ha-list-item
                >
              </ha-select>
              ${this._showBoostHint
                ? html`
                    <div class="boost-hint">
                      <ha-icon icon="mdi:information-outline"></ha-icon>
                      <span
                        >${localize(
                          "devices.heating_system_type_boost_hint",
                          this.hass.language,
                        )}</span
                      >
                    </div>
                  `
                : nothing}
            </div>
          `
        : nothing}
    `;
  }

  private _renderMasterRow(entityId: string, external: boolean) {
    const isThermostat = this._selectedThermostats.has(entityId);
    const isAc = this._selectedCoolingDevices.has(entityId);
    const isInRoom = isThermostat || isAc;
    const isFocused = this._selectedForEdit === entityId;
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const device = this.devices.find((d) => d.entity_id === entityId);
    const typeLabel = isThermostat
      ? localize("devices.type_thermostat", this.hass.language)
      : isAc
        ? localize("devices.type_ac", this.hass.language)
        : "";

    return html`
      <div
        class="master-row ${isFocused ? "focused" : ""} ${isInRoom ? "in-room" : ""}"
        @click=${() => this._onSelectForEdit(entityId)}
      >
        <ha-checkbox
          .checked=${isInRoom}
          @click=${(e: Event) => e.stopPropagation()}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onClimateToggle(entityId, target.checked);
            if (target.checked) this._selectedForEdit = entityId;
          }}
        ></ha-checkbox>
        <div class="master-info">
          <div class="master-name-row">
            <span class="master-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge"
                  >${localize("devices.other_area", this.hass.language)}</span
                >`
              : nothing}
          </div>
          <div class="master-meta">
            ${typeLabel ? html`<span class="type-pill">${typeLabel}</span>` : nothing}
            ${device?.idle_action && device.idle_action !== "off"
              ? html`<span class="meta-pill"
                  >${localize(
                    `devices.idle_action_${device.idle_action}`,
                    this.hass.language,
                  )}</span
                >`
              : nothing}
            ${isAc &&
            (device?.coil_dry === "on" || (device?.coil_dry !== "off" && this.coilDryEnabledGlobal))
              ? html`<span class="meta-pill"
                  >${localize("devices.coil_dry_summary", this.hass.language)}</span
                >`
              : nothing}
            ${device?.setpoint_mode === "direct" && this.selectedTempSensor
              ? html`<span class="meta-pill"
                  >${localize("devices.setpoint_mode_direct", this.hass.language)}</span
                >`
              : nothing}
          </div>
        </div>
      </div>
    `;
  }

  private _onSelectForEdit(entityId: string) {
    this._selectedForEdit = entityId;
  }

  private _renderDeviceDetail(entityId: string) {
    const device = this.devices.find((d) => d.entity_id === entityId);
    if (!device) return nothing;

    const isThermostat = device.type === "trv";
    const isAc = device.type === "ac";
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const hvacModes = (entityState?.attributes?.hvac_modes ?? []) as string[];
    const supportsFanOnly = hvacModes.includes("fan_only");
    const isExcluded = this.valveProtectionExclude.has(entityId);
    const lang = this.hass.language;

    return html`
      <div class="detail-head">
        <div class="detail-title">${friendlyName}</div>
        <div class="detail-entity-id">${entityId}</div>
      </div>

      <div class="detail-field">
        <ha-select
          .label=${localize("devices.type_label", lang) || "Type"}
          .value=${this._getDeviceDisplayType(entityId)}
          .options=${[
            { value: "thermostat", label: localize("devices.type_thermostat", lang) },
            { value: "ac", label: localize("devices.type_ac", lang) },
          ]}
          @selected=${(e: Event) =>
            this._onDeviceTypeChange(entityId, getSelectValue(e) as "thermostat" | "ac")}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
        >
          <ha-list-item value="thermostat"
            >${localize("devices.type_thermostat", lang)}</ha-list-item
          >
          <ha-list-item value="ac">${localize("devices.type_ac", lang)}</ha-list-item>
        </ha-select>
      </div>

      ${isAc
        ? html`
            <div class="detail-field">
              <ha-select
                .label=${localize("devices.idle_action", lang)}
                .value=${device.idle_action ?? "off"}
                .options=${[
                  { value: "off", label: localize("devices.idle_action_off", lang) },
                  ...(supportsFanOnly
                    ? [
                        {
                          value: "fan_only",
                          label: localize("devices.idle_action_fan_only", lang),
                        },
                      ]
                    : []),
                  { value: "setback", label: localize("devices.idle_action_setback", lang) },
                ]}
                @selected=${(e: Event) => this._onIdleActionChange(entityId, getSelectValue(e)!)}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="off"
                  >${localize("devices.idle_action_off", lang)}</ha-list-item
                >
                ${supportsFanOnly
                  ? html`<ha-list-item value="fan_only"
                      >${localize("devices.idle_action_fan_only", lang)}</ha-list-item
                    >`
                  : nothing}
                <ha-list-item value="setback"
                  >${localize("devices.idle_action_setback", lang)}</ha-list-item
                >
              </ha-select>
            </div>
            ${device.idle_action === "fan_only"
              ? html`<div class="detail-field">
                  <ha-select
                    .label=${localize("devices.idle_fan_mode", lang)}
                    .value=${device.idle_fan_mode === ""
                      ? "__keep__"
                      : (device.idle_fan_mode ?? "low")}
                    .options=${[
                      { value: "__keep__", label: localize("devices.idle_fan_mode_keep", lang) },
                      ...((entityState?.attributes?.fan_modes ?? []) as string[]).map((fm) => ({
                        value: fm,
                        label: fm,
                      })),
                    ]}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      this._onIdleFanModeChange(entityId, v === "__keep__" ? "" : v);
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  >
                    <ha-list-item value="__keep__"
                      >${localize("devices.idle_fan_mode_keep", lang)}</ha-list-item
                    >
                    ${((entityState?.attributes?.fan_modes ?? []) as string[]).map(
                      (fm) => html`<ha-list-item value="${fm}">${fm}</ha-list-item>`,
                    )}
                  </ha-select>
                </div>`
              : nothing}

            <div class="detail-field">
              <ha-select
                .label=${localize("devices.coil_dry", lang)}
                .value=${device.coil_dry ?? "inherit"}
                .options=${[
                  { value: "inherit", label: localize("devices.coil_dry_inherit", lang) },
                  { value: "on", label: localize("devices.coil_dry_on", lang) },
                  { value: "off", label: localize("devices.coil_dry_off", lang) },
                ]}
                @selected=${(e: Event) => this._onCoilDryChange(entityId, getSelectValue(e))}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="inherit"
                  >${localize("devices.coil_dry_inherit", lang)}</ha-list-item
                >
                <ha-list-item value="on">${localize("devices.coil_dry_on", lang)}</ha-list-item>
                <ha-list-item value="off">${localize("devices.coil_dry_off", lang)}</ha-list-item>
              </ha-select>
            </div>

            ${(device.coil_dry ?? "inherit") === "inherit" && !this.coilDryEnabledGlobal
              ? html`
                  <div class="boost-hint">
                    <ha-icon icon="mdi:information-outline"></ha-icon>
                    <span>${localize("devices.coil_dry_global_off_hint", lang)}</span>
                  </div>
                `
              : nothing}
            ${(device.coil_dry ?? "inherit") !== "off"
              ? html`
                  <div class="detail-field">
                    <ha-textfield
                      .value=${String(device.coil_dry_minutes ?? 0)}
                      .label=${localize("devices.coil_dry_minutes", lang, {
                        minutes: this.coilDryMinutesGlobal,
                      })}
                      type="number"
                      step="1"
                      min="0"
                      max="60"
                      @change=${(e: Event) => {
                        const v = parseInt((e.target as HTMLInputElement).value, 10);
                        if (!isNaN(v) && v >= 0 && v <= 60)
                          this._onCoilDryMinutesChange(entityId, v);
                      }}
                    ></ha-textfield>
                  </div>

                  <div class="detail-field with-info">
                    <ha-select
                      .label=${localize("devices.coil_dry_mode", lang)}
                      .value=${device.coil_dry_mode || INHERIT}
                      .options=${[
                        {
                          value: INHERIT,
                          label: localize("devices.coil_dry_mode_inherit", lang, {
                            value: this.coilDryModeGlobal,
                          }),
                        },
                        { value: "fan_only", label: "fan_only" },
                        { value: "dry", label: "dry" },
                      ]}
                      @selected=${(e: Event) =>
                        this._onCoilDryModeChange(entityId, fromInherit(getSelectValue(e)))}
                      @closed=${(e: Event) => e.stopPropagation()}
                      fixedMenuPosition
                    >
                      <ha-list-item value="${INHERIT}"
                        >${localize("devices.coil_dry_mode_inherit", lang, {
                          value: this.coilDryModeGlobal,
                        })}</ha-list-item
                      >
                      <ha-list-item value="fan_only">fan_only</ha-list-item>
                      <ha-list-item value="dry">dry</ha-list-item>
                    </ha-select>
                    ${device.coil_dry_mode === "dry"
                      ? html`<rs-info-icon
                          icon="mdi:alert-outline"
                          .text=${localize("coil_dry.mode_dry_warning", lang)}
                        ></rs-info-icon>`
                      : nothing}
                  </div>

                  <div class="detail-field">
                    <ha-select
                      .label=${localize("devices.coil_dry_fan_mode", lang)}
                      .value=${device.coil_dry_fan_mode || INHERIT}
                      .options=${[
                        {
                          value: INHERIT,
                          label: localize("devices.coil_dry_fan_mode_inherit", lang, {
                            value: this._globalFanModeLabel(lang),
                          }),
                        },
                        {
                          value: "__keep__",
                          label: localize("devices.coil_dry_fan_mode_keep", lang),
                        },
                        ...((entityState?.attributes?.fan_modes ?? []) as string[]).map((fm) => ({
                          value: fm,
                          label: fm,
                        })),
                      ]}
                      @selected=${(e: Event) =>
                        this._onCoilDryFanModeChange(entityId, fromInherit(getSelectValue(e)))}
                      @closed=${(e: Event) => e.stopPropagation()}
                      fixedMenuPosition
                    >
                      <ha-list-item value="${INHERIT}"
                        >${localize("devices.coil_dry_fan_mode_inherit", lang, {
                          value: this._globalFanModeLabel(lang),
                        })}</ha-list-item
                      >
                      <ha-list-item value="__keep__"
                        >${localize("devices.coil_dry_fan_mode_keep", lang)}</ha-list-item
                      >
                      ${((entityState?.attributes?.fan_modes ?? []) as string[]).map(
                        (fm) => html`<ha-list-item value="${fm}">${fm}</ha-list-item>`,
                      )}
                    </ha-select>
                  </div>
                `
              : nothing}
          `
        : nothing}
      ${isThermostat
        ? html`
            <div class="detail-field with-info">
              <ha-select
                .label=${localize("devices.idle_action", lang)}
                .value=${device.idle_action ?? "off"}
                .options=${[
                  { value: "off", label: localize("devices.idle_action_off", lang) },
                  { value: "low", label: localize("devices.idle_action_low", lang) },
                ]}
                @selected=${(e: Event) => this._onIdleActionChange(entityId, getSelectValue(e)!)}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="off"
                  >${localize("devices.idle_action_off", lang)}</ha-list-item
                >
                <ha-list-item value="low"
                  >${localize("devices.idle_action_low", lang)}</ha-list-item
                >
              </ha-select>
              ${device.idle_action === "low"
                ? html`<rs-info-icon
                    .text=${localize("devices.idle_action_low_hint", lang)}
                  ></rs-info-icon>`
                : nothing}
            </div>
          `
        : nothing}
      ${this.selectedTempSensor
        ? html`
            <div class="detail-field with-info">
              <ha-select
                .label=${localize("devices.setpoint_mode", lang)}
                .value=${device.setpoint_mode ?? "proportional"}
                .options=${[
                  {
                    value: "proportional",
                    label: localize("devices.setpoint_mode_proportional", lang),
                  },
                  {
                    value: "direct",
                    label: localize("devices.setpoint_mode_direct", lang),
                  },
                ]}
                @selected=${(e: Event) => this._onSetpointModeChange(entityId, getSelectValue(e)!)}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="proportional"
                  >${localize("devices.setpoint_mode_proportional", lang)}</ha-list-item
                >
                <ha-list-item value="direct"
                  >${localize("devices.setpoint_mode_direct", lang)}</ha-list-item
                >
              </ha-select>
              <rs-info-icon .text=${localize("devices.setpoint_mode_hint", lang)}></rs-info-icon>
            </div>
          `
        : nothing}
      ${isThermostat && this.valveProtectionEnabled
        ? html`
            <div class="detail-toggle-row">
              <ha-checkbox
                .checked=${isExcluded}
                @change=${(e: Event) => {
                  const target = e.target as HTMLElement & { checked: boolean };
                  this._onValveProtectionExcludeToggle(entityId, target.checked);
                }}
              ></ha-checkbox>
              <div class="detail-toggle-label">
                <ha-icon icon="mdi:shield-off-outline"></ha-icon>
                ${localize("devices.valve_protection_excluded", lang)}
                <rs-info-icon
                  .text=${localize("devices.valve_protection_exclude_hint", lang)}
                ></rs-info-icon>
              </div>
            </div>
          `
        : nothing}
    `;
  }

  // ---- Event handlers ----

  private _detectClimateType(entityId: string): "thermostat" | "ac" {
    const state = this.hass.states[entityId];
    const modes = (state?.attributes?.hvac_modes ?? []) as string[];
    // Only explicit heat/cool modes count. "auto" is ambiguous (device self-regulates)
    // and should not influence the initial classification. User can override manually.
    const canCool = modes.some((m) => ["cool", "heat_cool"].includes(m));
    if (canCool) return "ac";
    return "thermostat";
  }

  private _getDeviceDisplayType(entityId: string): string {
    const device = this.devices.find((d) => d.entity_id === entityId);
    if (!device) return "thermostat";
    if (device.type === "ac") return "ac";
    return "thermostat";
  }

  private _onClimateToggle(entityId: string, checked: boolean) {
    let newDevices: DeviceConfig[];
    if (checked) {
      const detected = this._detectClimateType(entityId);
      const type: DeviceType = detected === "thermostat" ? "trv" : "ac";
      newDevices = [...this.devices, { entity_id: entityId, type, role: "auto" }];
    } else {
      newDevices = this.devices.filter((d) => d.entity_id !== entityId);
    }
    this._fireDeviceChanged(newDevices);
  }

  private _onDeviceTypeChange(entityId: string, type: "thermostat" | "ac") {
    const deviceType: DeviceType = type === "thermostat" ? "trv" : "ac";
    const newDevices = this.devices.map((d) => {
      if (d.entity_id !== entityId) return d;
      const updated: DeviceConfig = { ...d, type: deviceType };
      // idle_action="low" is TRV-only; the backend schema rejects it for ACs.
      // Reset when switching to AC so the next save does not fail.
      if (deviceType === "ac" && updated.idle_action === "low") {
        updated.idle_action = "off";
      }
      // coil_dry="on" is AC-only (no evaporator coil on a TRV); the backend
      // schema rejects it. Reset when switching to TRV so the next save does not fail.
      if (deviceType === "trv" && updated.coil_dry === "on") {
        updated.coil_dry = "inherit";
      }
      return updated;
    });
    this._fireDeviceChanged(newDevices);
  }

  private _onValveProtectionExcludeToggle(entityId: string, excluded: boolean) {
    this.dispatchEvent(
      new CustomEvent("valve-protection-exclude-toggle", {
        detail: { entityId, excluded },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onIdleActionChange(entityId: string, idleAction: string): void {
    const newDevices = this.devices.map((d) => {
      if (d.entity_id !== entityId) return d;
      const updated = { ...d, idle_action: idleAction as "off" | "fan_only" | "setback" | "low" };
      if (idleAction === "fan_only" && !d.idle_fan_mode) {
        updated.idle_fan_mode = "low";
      }
      return updated;
    });
    this._fireDeviceChanged(newDevices);
  }

  private _onIdleFanModeChange(entityId: string, fanMode: string): void {
    const newDevices = this.devices.map((d) =>
      d.entity_id === entityId ? { ...d, idle_fan_mode: fanMode } : d,
    );
    this._fireDeviceChanged(newDevices);
  }

  private _onSetpointModeChange(entityId: string, mode: string): void {
    const newDevices = this.devices.map((d) =>
      d.entity_id === entityId ? { ...d, setpoint_mode: mode as "proportional" | "direct" } : d,
    );
    this._fireDeviceChanged(newDevices);
  }

  /** Global fan mode as shown in the inherit option ("" means keep current). */
  private _globalFanModeLabel(lang: string): string {
    return this.coilDryFanModeGlobal === ""
      ? localize("devices.coil_dry_fan_mode_keep", lang)
      : this.coilDryFanModeGlobal;
  }

  private _onCoilDryChange(entityId: string, value: string) {
    this._fireDeviceChanged(
      this.devices.map((d) =>
        d.entity_id === entityId ? { ...d, coil_dry: value as "inherit" | "on" | "off" } : d,
      ),
    );
  }

  private _onCoilDryMinutesChange(entityId: string, minutes: number) {
    this._fireDeviceChanged(
      this.devices.map((d) => (d.entity_id === entityId ? { ...d, coil_dry_minutes: minutes } : d)),
    );
  }

  private _onCoilDryModeChange(entityId: string, value: string) {
    this._fireDeviceChanged(
      this.devices.map((d) =>
        d.entity_id === entityId ? { ...d, coil_dry_mode: value as "" | "fan_only" | "dry" } : d,
      ),
    );
  }

  private _onCoilDryFanModeChange(entityId: string, value: string) {
    this._fireDeviceChanged(
      this.devices.map((d) => (d.entity_id === entityId ? { ...d, coil_dry_fan_mode: value } : d)),
    );
  }

  private _onHeatingSystemTypeChange(e: Event) {
    const raw = getSelectValue(e) ?? "";
    const value = raw === "standard" ? "" : raw;
    this._showBoostHint = true;
    const newDevices = this.devices.map((d) =>
      d.type === "trv" ? { ...d, heating_system_type: value } : d,
    );
    this._fireDeviceChanged(newDevices);
  }

  private _fireDeviceChanged(devices: DeviceConfig[]) {
    this.dispatchEvent(
      new CustomEvent("device-changed", {
        detail: { devices },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _entityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    const idAfterDot = id.substring(id.indexOf(".") + 1);
    if (idAfterDot.startsWith("roommind_")) return false;
    if (this.devices.some((d) => d.entity_id === id)) return false;
    return id.startsWith("climate.");
  };

  private _onEntityPicked(e: CustomEvent) {
    const entityId = e.detail?.value as string;
    const picker = e.target as HTMLElement & { value: string };
    picker.value = "";
    if (!entityId || !entityId.startsWith("climate.")) return;
    if (this.devices.some((d) => d.entity_id === entityId)) return;
    const detected = this._detectClimateType(entityId);
    const type: DeviceType = detected === "thermostat" ? "trv" : "ac";
    const newDevices = [...this.devices, { entity_id: entityId, type, role: "auto" as const }];
    this._fireDeviceChanged(newDevices);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-device-section": RsDeviceSection;
  }
}

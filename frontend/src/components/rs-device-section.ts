import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  HassArea,
} from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";

@customElement("rs-device-section")
export class RsDeviceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public selectedThermostats: Set<string> = new Set();
  @property({ attribute: false }) public selectedAcs: Set<string> = new Set();
  @property({ type: String }) public selectedTempSensor = "";
  @property({ type: String }) public selectedHumiditySensor = "";
  @property({ attribute: false }) public selectedWindowSensors: Set<string> = new Set();
  @property({ type: Number }) public windowOpenDelay = 0;
  @property({ type: Number }) public windowCloseDelay = 0;
  @property({ type: String }) public heatingSystemType = "";

  @property({ type: Boolean }) public editing = false;
  @state() private _systemTypeInfoExpanded = false;

  static styles = css`
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
    .info-icon:hover, .info-icon.info-active {
      opacity: 1;
      color: var(--primary-color);
    }

    .system-type-info {
      font-size: 12px;
      line-height: 1.5;
      color: var(--secondary-text-color);
      padding: 8px 14px 4px;
    }

    ha-entity-picker {
      width: 100%;
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

    .delay-fields {
      display: flex;
      gap: 12px;
      margin-top: 8px;
      padding: 0 14px;
    }

    .delay-fields ha-textfield {
      flex: 1;
    }

    .delay-view {
      font-size: 12px;
      color: var(--secondary-text-color);
      padding: 4px 14px 0;
    }

    .delay-hint {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      font-size: 12px;
      line-height: 1.5;
      color: var(--warning-color, #ff9800);
      padding: 8px 14px 0;
    }

    .delay-hint ha-icon {
      --mdc-icon-size: 16px;
      flex-shrink: 0;
      margin-top: 1px;
    }
  `;

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  private _renderViewMode() {
    const hasClimate = this.selectedThermostats.size > 0 || this.selectedAcs.size > 0;
    const hasTempSensor = !!this.selectedTempSensor;
    const hasHumiditySensor = !!this.selectedHumiditySensor;

    return html`
      ${hasClimate ? html`
        <div class="device-group">
          <div class="section-subtitle">${localize("devices.climate_entities", this.hass.language)}</div>
          ${[...this.selectedThermostats].map((id) => this._renderViewRow(id, "climate"))}
          ${[...this.selectedAcs].map((id) => this._renderViewRow(id, "climate"))}
        </div>
      ` : nothing}

      ${hasTempSensor ? html`
        <div class="device-group">
          <div class="section-subtitle">${localize("devices.temp_sensors", this.hass.language)}</div>
          ${this._renderViewRow(this.selectedTempSensor, "temp")}
        </div>
      ` : nothing}

      ${hasHumiditySensor ? html`
        <div class="device-group">
          <div class="section-subtitle">${localize("devices.humidity_sensors", this.hass.language)}</div>
          ${this._renderViewRow(this.selectedHumiditySensor, "humidity")}
        </div>
      ` : nothing}

      ${this.selectedWindowSensors.size > 0 ? html`
        <div class="device-group">
          <div class="section-subtitle">${localize("devices.window_sensors", this.hass.language)}</div>
          ${[...this.selectedWindowSensors].map((id) => this._renderWindowViewRow(id))}
          ${this.windowOpenDelay || this.windowCloseDelay ? html`
            <div class="delay-view">
              ${this.windowOpenDelay ? html`${localize("devices.window_open_delay", this.hass.language)}: ${this.windowOpenDelay}s` : nothing}
              ${this.windowOpenDelay && this.windowCloseDelay ? " · " : nothing}
              ${this.windowCloseDelay ? html`${localize("devices.window_close_delay", this.hass.language)}: ${this.windowCloseDelay}s` : nothing}
            </div>
          ` : nothing}
        </div>
      ` : nothing}

      ${this.heatingSystemType ? html`
        <div class="device-group">
          <div class="section-subtitle">${localize("devices.heating_system_type", this.hass.language)}</div>
          <div class="view-row">
            <span class="view-name">${
              this.heatingSystemType === "radiator"
                ? localize("devices.system_type_radiator", this.hass.language)
                : this.heatingSystemType === "underfloor"
                  ? localize("devices.system_type_underfloor", this.hass.language)
                  : this.heatingSystemType
            }</span>
          </div>
        </div>
      ` : nothing}
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
      if (ct != null) displayValue = `${ct.toFixed(1)}\u00B0`;
    } else if (type === "temp") {
      if (state && state !== "unknown" && state !== "unavailable") displayValue = `${Number(state).toFixed(1)}${tempUnit(this.hass)}`;
    } else {
      if (state && state !== "unknown" && state !== "unavailable") displayValue = `${Math.round(Number(state))}%`;
    }

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this,entityId)}>${friendlyName}</span>
        ${displayValue ? html`<span class="view-value">${displayValue}</span>` : nothing}
      </div>
    `;
  }

  private _renderWindowViewRow(entityId: string) {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const isOpen = entityState?.state === "on";

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this,entityId)}>${friendlyName}</span>
        <span class="view-value" style="color: ${isOpen ? "var(--warning-color, #ff9800)" : "var(--secondary-text-color)"}">
          ${isOpen ? "\u25CF" : "\u25CB"}
        </span>
      </div>
    `;
  }

  private _renderEditMode() {
    // Fetch all area entities once, then filter by category
    const allAreaEntities = getEntitiesForArea(
      this.area.area_id,
      this.hass?.entities,
      this.hass?.devices,
    );

    const areaClimateEntities = allAreaEntities.filter(
      (e) => e.entity_id.startsWith("climate."),
    );

    const areaTempSensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            e.entity_id.startsWith("sensor.") &&
            this.hass.states[e.entity_id]?.attributes?.device_class === "temperature",
        )
      : [];

    const areaHumiditySensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            e.entity_id.startsWith("sensor.") &&
            this.hass.states[e.entity_id]?.attributes?.device_class === "humidity",
        )
      : [];

    const areaWindowSensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            e.entity_id.startsWith("binary_sensor.") &&
            ["window", "door", "opening"].includes(
              this.hass.states[e.entity_id]?.attributes?.device_class as string,
            ),
        )
      : [];

    // Find selected entities not in this area (manually added)
    const areaClimateIds = new Set(areaClimateEntities.map((e) => e.entity_id));
    const allSelectedClimate = new Set([
      ...this.selectedThermostats,
      ...this.selectedAcs,
    ]);
    const externalClimateIds = [...allSelectedClimate].filter(
      (id) => !areaClimateIds.has(id)
    );

    const areaTempIds = new Set(areaTempSensors.map((e) => e.entity_id));
    const externalTempSensor =
      this.selectedTempSensor && !areaTempIds.has(this.selectedTempSensor)
        ? this.selectedTempSensor
        : null;

    const areaHumidityIds = new Set(
      areaHumiditySensors.map((e) => e.entity_id)
    );
    const externalHumiditySensor =
      this.selectedHumiditySensor &&
      !areaHumidityIds.has(this.selectedHumiditySensor)
        ? this.selectedHumiditySensor
        : null;

    const areaWindowIds = new Set(areaWindowSensors.map((e) => e.entity_id));
    const externalWindowSensors = [...this.selectedWindowSensors].filter(
      (id) => !areaWindowIds.has(id)
    );

    return html`
      <div class="device-group">
        <div class="section-subtitle">${localize("devices.climate_entities", this.hass.language)}</div>
        <div class="device-list-scroll">
          ${areaClimateEntities.length > 0
            ? areaClimateEntities.map((entity) =>
                this._renderClimateRow(entity.entity_id, false)
              )
            : html`<div class="no-devices">
                ${localize("devices.no_climate", this.hass.language)}
              </div>`}
          ${externalClimateIds.map((id) => this._renderClimateRow(id, true))}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${localize("devices.temp_sensors", this.hass.language)}</div>
        <div class="device-list-scroll">
          ${areaTempSensors.length > 0
            ? areaTempSensors.map((entity) =>
                this._renderSensorRow(entity.entity_id, "temp", false)
              )
            : html`<div class="no-devices">
                ${localize("devices.no_temp_sensors", this.hass.language)}
              </div>`}
          ${externalTempSensor
            ? this._renderSensorRow(externalTempSensor, "temp", true)
            : nothing}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${localize("devices.humidity_sensors", this.hass.language)}</div>
        <div class="device-list-scroll">
          ${areaHumiditySensors.length > 0
            ? areaHumiditySensors.map((entity) =>
                this._renderSensorRow(entity.entity_id, "humidity", false)
              )
            : html`<div class="no-devices">
                ${localize("devices.no_humidity_sensors", this.hass.language)}
              </div>`}
          ${externalHumiditySensor
            ? this._renderSensorRow(externalHumiditySensor, "humidity", true)
            : nothing}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${localize("devices.window_sensors", this.hass.language)}</div>
        <div class="device-list-scroll">
          ${areaWindowSensors.length > 0
            ? areaWindowSensors.map((entity) =>
                this._renderWindowRow(entity.entity_id, false)
              )
            : html`<div class="no-devices">
                ${localize("devices.no_window_sensors", this.hass.language)}
            </div>`}
          ${externalWindowSensors.map((id) => this._renderWindowRow(id, true))}
        </div>
        ${this.selectedWindowSensors.size > 0 ? html`
          <div class="delay-fields">
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${localize("devices.window_open_delay", this.hass.language)}
              .value=${String(this.windowOpenDelay)}
              @change=${this._onWindowOpenDelayChange}
            ></ha-textfield>
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${localize("devices.window_close_delay", this.hass.language)}
              .value=${String(this.windowCloseDelay)}
              @change=${this._onWindowCloseDelayChange}
            ></ha-textfield>
          </div>
          ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300 ? html`
            <div class="delay-hint">
              <ha-icon icon="mdi:information-outline"></ha-icon>
              ${localize("devices.underfloor_delay_hint", this.hass.language)}
            </div>
          ` : nothing}
        ` : nothing}
      </div>

      <div class="entity-picker-wrap">
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["climate", "sensor", "binary_sensor", "input_number"]}
          .entityFilter=${this._entityFilter}
          .value=${""}
          label=${localize("devices.add_entity", this.hass.language)}
          @value-changed=${this._onEntityPicked}
        ></ha-entity-picker>
      </div>

      ${this.selectedThermostats.size > 0 ? html`
        <div class="device-group">
          <div class="subtitle-row">
            <div class="section-subtitle">${localize("devices.heating_system_type", this.hass.language)}</div>
            <ha-icon
              class="info-icon ${this._systemTypeInfoExpanded ? "info-active" : ""}"
              icon="mdi:information-outline"
              @click=${() => { this._systemTypeInfoExpanded = !this._systemTypeInfoExpanded; }}
            ></ha-icon>
          </div>
          ${this._systemTypeInfoExpanded ? html`
            <div class="system-type-info">${localize("devices.heating_system_type_info", this.hass.language)}</div>
          ` : nothing}
          <ha-select
            .value=${this.heatingSystemType || "standard"}
            .options=${[
              { value: "standard", label: localize("devices.system_type_none", this.hass.language) },
              { value: "radiator", label: localize("devices.system_type_radiator", this.hass.language) },
              { value: "underfloor", label: localize("devices.system_type_underfloor", this.hass.language) },
            ]}
            @selected=${this._onHeatingSystemTypeChange}
            @closed=${(e: Event) => e.stopPropagation()}
            fixedMenuPosition
            style="width: 100%;"
          >
            <ha-list-item value="standard">${localize("devices.system_type_none", this.hass.language)}</ha-list-item>
            <ha-list-item value="radiator">${localize("devices.system_type_radiator", this.hass.language)}</ha-list-item>
            <ha-list-item value="underfloor">${localize("devices.system_type_underfloor", this.hass.language)}</ha-list-item>
          </ha-select>
        </div>
      ` : nothing}

    `;
  }

  private _renderClimateRow(entityId: string, external: boolean) {
    const isThermostat = this.selectedThermostats.has(entityId);
    const isAc = this.selectedAcs.has(entityId);
    const isSelected = isThermostat || isAc;
    const entityState = this.hass.states[entityId];
    const friendlyName =
      (entityState?.attributes?.friendly_name as string) || entityId;
    const currentState = entityState?.state;
    const currentTemp = entityState?.attributes?.current_temperature as
      | number
      | undefined;

    return html`
      <div class="device-row ${isSelected ? "selected" : ""}">
        <ha-checkbox
          .checked=${isSelected}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onClimateToggle(entityId, target.checked);
          }}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge">${localize("devices.other_area", this.hass.language)}</span>`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        ${currentTemp != null
          ? html`<span class="device-value"
              >${currentTemp.toFixed(1)}\u00B0</span
            >`
          : currentState && currentState !== "unavailable"
            ? html`<span
                class="device-value"
                style="font-size:12px; opacity:0.6"
                >${currentState}</span
              >`
            : nothing}
        ${isSelected
          ? html`
              <ha-select
                class="device-type-select"
                outlined
                .value=${isAc ? "ac" : "thermostat"}
                .options=${[
                  { value: "thermostat", label: localize("devices.type_thermostat", this.hass.language) },
                  { value: "ac", label: localize("devices.type_ac", this.hass.language) },
                ]}
                @selected=${(e: Event) => {
                  this._onDeviceTypeChange(
                    entityId,
                    getSelectValue(e) as "thermostat" | "ac"
                  );
                }}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="thermostat">${localize("devices.type_thermostat", this.hass.language)}</ha-list-item>
                <ha-list-item value="ac">${localize("devices.type_ac", this.hass.language)}</ha-list-item>
              </ha-select>
            `
          : nothing}
      </div>
    `;
  }

  private _renderSensorRow(
    entityId: string,
    type: "temp" | "humidity",
    external: boolean
  ) {
    const entityState = this.hass.states[entityId];
    const friendlyName =
      (entityState?.attributes?.friendly_name as string) || entityId;
    const currentValue = entityState?.state;
    const selected =
      type === "temp" ? this.selectedTempSensor : this.selectedHumiditySensor;
    const isSelected = selected === entityId;
    const unit = type === "temp" ? tempUnit(this.hass) : "%";
    const hasValue =
      currentValue &&
      currentValue !== "unknown" &&
      currentValue !== "unavailable";

    return html`
      <div class="device-row ${isSelected ? "selected" : ""}"
        @click=${() => this._onSensorSelected(isSelected ? "" : entityId, type)}
      >
        <ha-radio
          .checked=${isSelected}
          name="${type}-sensor"
        ></ha-radio>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge">${localize("devices.other_area", this.hass.language)}</span>`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        ${hasValue
          ? html`<span class="device-value">${type === "humidity" ? Math.round(Number(currentValue)) : currentValue}${unit}</span>`
          : nothing}
      </div>
    `;
  }

  private _renderWindowRow(entityId: string, external: boolean) {
    const isSelected = this.selectedWindowSensors.has(entityId);
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const isOpen = entityState?.state === "on";

    return html`
      <div class="device-row ${isSelected ? "selected" : ""}">
        <ha-checkbox
          .checked=${isSelected}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onWindowSensorToggle(entityId, target.checked);
          }}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge">${localize("devices.other_area", this.hass.language)}</span>`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        <span class="device-value" style="color: ${isOpen ? "var(--warning-color, #ff9800)" : "var(--secondary-text-color)"}">
          ${isOpen ? "\u25CF" : "\u25CB"}
        </span>
      </div>
    `;
  }

  // ---- Event handlers ----

  private _detectClimateType(entityId: string): "thermostat" | "ac" {
    const modes = this.hass.states[entityId]?.attributes?.hvac_modes as string[] | undefined;
    if (!modes) return "thermostat";
    const canCool = modes.includes("cool") || modes.includes("heat_cool");
    return canCool ? "ac" : "thermostat";
  }

  private _onClimateToggle(entityId: string, checked: boolean) {
    this.dispatchEvent(
      new CustomEvent("climate-toggle", {
        detail: { entityId, checked, detectedType: this._detectClimateType(entityId) },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onDeviceTypeChange(entityId: string, type: "thermostat" | "ac") {
    this.dispatchEvent(
      new CustomEvent("device-type-change", {
        detail: { entityId, type },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onSensorSelected(entityId: string, type: "temp" | "humidity") {
    this.dispatchEvent(
      new CustomEvent("sensor-selected", {
        detail: { entityId, type },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onWindowSensorToggle(entityId: string, checked: boolean) {
    this.dispatchEvent(
      new CustomEvent("window-sensor-toggle", {
        detail: { entityId, checked },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onWindowOpenDelayChange(e: Event) {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("window-open-delay-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onWindowCloseDelayChange(e: Event) {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("window-close-delay-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _onHeatingSystemTypeChange(e: Event) {
    const raw = getSelectValue(e) ?? "";
    const value = raw === "standard" ? "" : raw;
    this.dispatchEvent(
      new CustomEvent("heating-system-type-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _entityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    // Exclude already-selected entities
    if (this.selectedThermostats.has(id) || this.selectedAcs.has(id)) return false;
    if (this.selectedTempSensor === id) return false;
    if (this.selectedHumiditySensor === id) return false;
    if (this.selectedWindowSensors.has(id)) return false;
    // For sensors, only show temperature and humidity
    if (id.startsWith("sensor.")) {
      const dc = this.hass.states[id]?.attributes?.device_class;
      if (dc !== "temperature" && dc !== "humidity") return false;
    }
    if (id.startsWith("binary_sensor.")) {
      const dc = this.hass.states[id]?.attributes?.device_class;
      if (dc !== "window" && dc !== "door" && dc !== "opening") return false;
    }
    // input_number: allow all (no device_class filtering)
    return true;
  };

  private _onEntityPicked(e: CustomEvent) {
    const entityId = e.detail?.value as string;
    if (!entityId) return;

    // Auto-categorize based on domain and device_class
    let category: "climate" | "temp" | "humidity" | "window";
    if (entityId.startsWith("climate.")) {
      category = "climate";
    } else if (entityId.startsWith("binary_sensor.")) {
      category = "window";
    } else if (entityId.startsWith("input_number.")) {
      const uom = this.hass.states[entityId]?.attributes?.unit_of_measurement;
      category = uom === "%" ? "humidity" : "temp";
    } else {
      const deviceClass =
        this.hass.states[entityId]?.attributes?.device_class;
      category = deviceClass === "humidity" ? "humidity" : "temp";
    }

    const detectedType = category === "climate" ? this._detectClimateType(entityId) : undefined;

    this.dispatchEvent(
      new CustomEvent("external-entity-added", {
        detail: { entityId, category, detectedType },
        bubbles: true,
        composed: true,
      })
    );

    // Clear the picker value
    const picker = e.target as HTMLElement & { value: string };
    picker.value = "";
  }

}

declare global {
  interface HTMLElementTagNameMap {
    "rs-device-section": RsDeviceSection;
  }
}

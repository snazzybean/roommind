import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, HassArea } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";

@customElement("rs-sensor-section")
export class RsSensorSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ type: String }) public temperatureSensor = "";
  @property({ type: String }) public humiditySensor = "";
  @property({ attribute: false }) public occupancySensors: Set<string> = new Set();
  @property({ type: Boolean }) public editing = false;
  @property() public language = "en";

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

    .no-devices {
      color: var(--secondary-text-color);
      font-size: 13px;
      font-style: italic;
      padding: 12px 14px;
    }

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
  `;

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  private _renderViewMode() {
    const hasTempSensor = !!this.temperatureSensor;
    const hasHumiditySensor = !!this.humiditySensor;
    const hasOccupancySensors = this.occupancySensors.size > 0;

    if (!hasTempSensor && !hasHumiditySensor && !hasOccupancySensors) {
      return nothing;
    }

    return html`
      ${hasTempSensor
        ? html`
            <div class="device-group">
              <div class="section-subtitle">
                ${localize("devices.temp_sensors", this.hass.language)}
              </div>
              ${this._renderSensorViewRow(this.temperatureSensor, "temp")}
            </div>
          `
        : nothing}
      ${hasHumiditySensor
        ? html`
            <div class="device-group">
              <div class="section-subtitle">
                ${localize("devices.humidity_sensors", this.hass.language)}
              </div>
              ${this._renderSensorViewRow(this.humiditySensor, "humidity")}
            </div>
          `
        : nothing}
      ${hasOccupancySensors
        ? html`
            <div class="device-group">
              <div class="section-subtitle">
                ${localize("devices.occupancy_sensors", this.hass.language)}
              </div>
              ${[...this.occupancySensors].map((id) => this._renderOccupancyViewRow(id))}
            </div>
          `
        : nothing}
    `;
  }

  private _renderSensorViewRow(entityId: string, type: "temp" | "humidity") {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const state = entityState?.state;
    const attrs = entityState?.attributes ?? {};

    let displayValue = "";
    if (type === "temp") {
      const tempVal = entityId.startsWith("climate.") ? attrs.current_temperature : state;
      if (tempVal != null && tempVal !== "" && tempVal !== "unknown" && tempVal !== "unavailable")
        displayValue = `${Number(tempVal).toFixed(1)}${tempUnit(this.hass)}`;
    } else {
      if (state && state !== "unknown" && state !== "unavailable")
        displayValue = `${Math.round(Number(state))}%`;
    }

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this, entityId)}
          >${friendlyName}</span
        >
        ${displayValue ? html`<span class="view-value">${displayValue}</span>` : nothing}
      </div>
    `;
  }

  private _renderOccupancyViewRow(entityId: string) {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const isOn = entityState?.state === "on";

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this, entityId)}
          >${friendlyName}</span
        >
        <span
          class="view-value"
          style="color: ${isOn ? "var(--primary-color)" : "var(--secondary-text-color)"}"
        >
          ${isOn ? "\u25CF" : "\u25CB"}
        </span>
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

    const areaTempSensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            (e.entity_id.startsWith("sensor.") &&
              this.hass.states[e.entity_id]?.attributes?.device_class === "temperature") ||
            (e.entity_id.startsWith("climate.") &&
              this.hass.states[e.entity_id]?.attributes?.current_temperature != null),
        )
      : [];

    const areaHumiditySensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            e.entity_id.startsWith("sensor.") &&
            this.hass.states[e.entity_id]?.attributes?.device_class === "humidity",
        )
      : [];

    const areaOccupancySensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            (e.entity_id.startsWith("binary_sensor.") &&
              ["occupancy", "motion", "presence"].includes(
                this.hass.states[e.entity_id]?.attributes?.device_class as string,
              )) ||
            e.entity_id.startsWith("input_boolean."),
        )
      : [];

    const areaTempIds = new Set(areaTempSensors.map((e) => e.entity_id));
    const externalTempSensor =
      this.temperatureSensor && !areaTempIds.has(this.temperatureSensor)
        ? this.temperatureSensor
        : null;

    const areaHumidityIds = new Set(areaHumiditySensors.map((e) => e.entity_id));
    const externalHumiditySensor =
      this.humiditySensor && !areaHumidityIds.has(this.humiditySensor) ? this.humiditySensor : null;

    const areaOccupancyIds = new Set(areaOccupancySensors.map((e) => e.entity_id));
    const externalOccupancySensors = [...this.occupancySensors].filter(
      (id) => !areaOccupancyIds.has(id),
    );

    return html`
      <div class="device-group">
        <div class="section-subtitle">${localize("devices.temp_sensors", this.hass.language)}</div>
        <div class="device-list-scroll">
          ${areaTempSensors.length > 0
            ? areaTempSensors.map((entity) =>
                this._renderSensorRow(entity.entity_id, "temp", false),
              )
            : html`<div class="no-devices">
                ${localize("devices.no_temp_sensors", this.hass.language)}
              </div>`}
          ${externalTempSensor ? this._renderSensorRow(externalTempSensor, "temp", true) : nothing}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">
          ${localize("devices.humidity_sensors", this.hass.language)}
        </div>
        <div class="device-list-scroll">
          ${areaHumiditySensors.length > 0
            ? areaHumiditySensors.map((entity) =>
                this._renderSensorRow(entity.entity_id, "humidity", false),
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
        <div class="section-subtitle">
          ${localize("devices.occupancy_sensors", this.hass.language)}
        </div>
        <div class="device-list-scroll">
          ${areaOccupancySensors.length > 0
            ? areaOccupancySensors.map((entity) =>
                this._renderOccupancyRow(entity.entity_id, false),
              )
            : html`<div class="no-devices">
                ${localize("devices.no_occupancy_sensors", this.hass.language)}
              </div>`}
          ${externalOccupancySensors.map((id) => this._renderOccupancyRow(id, true))}
        </div>
      </div>
    `;
  }

  private _renderSensorRow(entityId: string, type: "temp" | "humidity", external: boolean) {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const currentValue = entityId.startsWith("climate.")
      ? entityState?.attributes?.current_temperature
      : entityState?.state;
    const selected = type === "temp" ? this.temperatureSensor : this.humiditySensor;
    const isSelected = selected === entityId;
    const unit = type === "temp" ? tempUnit(this.hass) : "%";
    const hasValue = currentValue && currentValue !== "unknown" && currentValue !== "unavailable";

    return html`
      <div
        class="device-row ${isSelected ? "selected" : ""}"
        @click=${() => this._onSensorSelected(isSelected ? "" : entityId, type)}
      >
        <ha-radio .checked=${isSelected} name="${type}-sensor"></ha-radio>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge"
                  >${localize("devices.other_area", this.hass.language)}</span
                >`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        ${hasValue
          ? html`<span class="device-value"
              >${type === "humidity"
                ? Math.round(Number(currentValue))
                : Number(currentValue).toFixed(1)}${unit}</span
            >`
          : nothing}
      </div>
    `;
  }

  private _renderOccupancyRow(entityId: string, external: boolean) {
    const isSelected = this.occupancySensors.has(entityId);
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const isOn = entityState?.state === "on";

    return html`
      <div class="device-row ${isSelected ? "selected" : ""}">
        <ha-checkbox
          .checked=${isSelected}
          @change=${(e: Event) => {
            const target = e.target as HTMLElement & { checked: boolean };
            this._onOccupancySensorToggle(entityId, target.checked);
          }}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${friendlyName}</span>
            ${external
              ? html`<span class="external-badge"
                  >${localize("devices.other_area", this.hass.language)}</span
                >`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        <span
          class="device-value"
          style="color: ${isOn ? "var(--primary-color)" : "var(--secondary-text-color)"}"
        >
          ${isOn ? "\u25CF" : "\u25CB"}
        </span>
      </div>
    `;
  }

  private _onSensorSelected(entityId: string, type: "temp" | "humidity") {
    const key = type === "temp" ? "temperature_sensor" : "humidity_sensor";
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key, value: entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onOccupancySensorToggle(entityId: string, checked: boolean) {
    const next = new Set(this.occupancySensors);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "occupancy_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-sensor-section": RsSensorSection;
  }
}

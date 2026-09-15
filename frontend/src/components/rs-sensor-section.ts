import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";
import { inputStyles } from "../styles/input-styles";

type SensorKind = "temp" | "humidity" | "occupancy" | "window";

@customElement("rs-sensor-section")
export class RsSensorSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ type: String }) public temperatureSensor = "";
  @property({ type: String }) public humiditySensor = "";
  @property({ attribute: false }) public occupancySensors: Set<string> = new Set();
  @property({ attribute: false }) public windowSensors: Set<string> = new Set();
  @property({ type: Number }) public windowOpenDelay = 0;
  @property({ type: Number }) public windowCloseDelay = 0;
  @property({ type: String }) public heatingSystemType = "";
  @property({ type: Boolean }) public editing = false;
  @property() public language = "en";

  @state() private _pickerOpen = false;
  @state() private _collapsed: Partial<Record<SensorKind, boolean>> = {};

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }

      .sensor-block {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 12px 14px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.08));
        border-radius: 12px;
      }

      .sensor-block + .sensor-block {
        margin-top: 12px;
      }

      .block-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding-bottom: 6px;
        cursor: pointer;
        user-select: none;
      }

      .block-header:hover .block-title {
        color: var(--primary-color);
      }

      .block-header ha-icon {
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
      }

      .chevron {
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        transition: transform 0.2s ease;
      }

      .chevron.collapsed {
        transform: rotate(-90deg);
      }

      .block-body {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .sensor-block.collapsed .block-header {
        padding-bottom: 0;
      }

      .block-title {
        font-size: 13px;
        font-weight: 500;
        color: var(--primary-text-color);
        letter-spacing: 0.2px;
        flex: 1;
      }

      .count-chip {
        font-size: 11px;
        font-weight: 500;
        padding: 1px 7px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.06);
        color: var(--secondary-text-color);
      }

      .count-chip.has-selection {
        background: rgba(3, 169, 244, 0.15);
        color: var(--primary-color);
      }

      .row-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
        max-height: 168px;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-width: thin;
      }

      .row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 8px;
        border-radius: 8px;
        cursor: pointer;
        border-left: 2px solid transparent;
        transition:
          background 0.15s,
          border-color 0.15s;
        min-width: 0;
      }

      .row:hover {
        background: rgba(255, 255, 255, 0.03);
      }

      .row.selected {
        background: rgba(3, 169, 244, 0.08);
        border-left-color: var(--primary-color);
      }

      .row ha-checkbox,
      .row ha-radio {
        flex-shrink: 0;
        margin: -4px 0;
      }

      .row-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 1px;
      }

      .row-name-line {
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
      }

      .row-name {
        font-size: 13px;
        font-weight: 450;
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .row-eid {
        font-family: var(--code-font-family, monospace);
        font-size: 10.5px;
        color: var(--secondary-text-color);
        opacity: 0.65;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .external-badge {
        display: inline-flex;
        align-items: center;
        font-size: 9.5px;
        font-weight: 500;
        color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.1);
        padding: 1px 6px;
        border-radius: 8px;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        flex-shrink: 0;
      }

      .value-chip {
        flex-shrink: 0;
        font-size: 12px;
        font-weight: 500;
        padding: 3px 9px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.05);
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .row.selected .value-chip {
        background: rgba(3, 169, 244, 0.15);
        color: var(--primary-color);
      }

      .occupancy-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
        transition: background 0.2s;
      }

      .occupancy-dot.on {
        background: var(--success-color, #4caf50);
        box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.18);
      }

      .occupancy-dot.off {
        background: rgba(255, 255, 255, 0.2);
      }

      .window-dot.on {
        background: var(--warning-color, #ff9800);
        box-shadow: 0 0 0 3px rgba(255, 152, 0, 0.18);
      }

      .window-dot.off {
        background: rgba(255, 255, 255, 0.2);
      }

      .delay-fields {
        display: flex;
        gap: 8px;
        margin-top: 8px;
      }

      .delay-fields ha-textfield {
        flex: 1;
      }

      .delay-hint {
        display: flex;
        align-items: flex-start;
        gap: 6px;
        font-size: 11.5px;
        line-height: 1.5;
        color: var(--warning-color, #ff9800);
        margin-top: 6px;
      }

      .delay-hint ha-icon {
        --mdc-icon-size: 16px;
        flex-shrink: 0;
        margin-top: 1px;
      }

      .delay-view {
        font-size: 12px;
        color: var(--secondary-text-color);
        padding-top: 4px;
      }

      .empty-row {
        color: var(--secondary-text-color);
        font-size: 12.5px;
        font-style: italic;
        padding: 6px 4px;
        opacity: 0.7;
      }

      .add-row,
      .global-add {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .global-add {
        margin-top: 12px;
      }

      .add-row ha-entity-picker,
      .global-add ha-entity-picker {
        flex: 1;
      }

      .add-button {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        margin: 12px 0 0 0;
        background: none;
        border: none;
        cursor: pointer;
        color: var(--secondary-text-color);
        font-size: 12px;
        font-weight: 500;
        border-radius: 6px;
        transition:
          color 0.15s,
          background 0.15s;
      }

      .add-button:hover,
      .add-button:focus-visible {
        color: var(--primary-color);
        background: rgba(3, 169, 244, 0.08);
        outline: none;
      }

      .add-button ha-icon {
        --mdc-icon-size: 16px;
      }

      .picker-close {
        --mdc-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        flex-shrink: 0;
      }

      /* View mode rows */
      .view-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 0;
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

      .section-subtitle {
        font-size: 12px;
        font-weight: 500;
        color: var(--secondary-text-color);
        margin: 12px 0 4px 0;
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }

      .section-subtitle:first-child {
        margin-top: 0;
      }
    `,
  ];

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  // ─── View mode ───

  private _renderViewMode() {
    const hasTempSensor = !!this.temperatureSensor;
    const hasHumiditySensor = !!this.humiditySensor;
    const hasOccupancySensors = this.occupancySensors.size > 0;
    const hasWindowSensors = this.windowSensors.size > 0;

    if (!hasTempSensor && !hasHumiditySensor && !hasOccupancySensors && !hasWindowSensors) {
      return nothing;
    }

    const lang = this.hass.language;
    return html`
      ${
        hasTempSensor
          ? html`
              <div class="section-subtitle">${localize("devices.temp_sensors", lang)}</div>
              ${this._renderSensorViewRow(this.temperatureSensor, "temp")}
            `
          : nothing
      }
      ${
        hasHumiditySensor
          ? html`
              <div class="section-subtitle">${localize("devices.humidity_sensors", lang)}</div>
              ${this._renderSensorViewRow(this.humiditySensor, "humidity")}
            `
          : nothing
      }
      ${
        hasOccupancySensors
          ? html`
              <div class="section-subtitle">${localize("devices.occupancy_sensors", lang)}</div>
              ${[...this.occupancySensors].map((id) => this._renderOccupancyViewRow(id))}
            `
          : nothing
      }
      ${
        hasWindowSensors
          ? html`
              <div class="section-subtitle">${localize("devices.window_sensors", lang)}</div>
              ${[...this.windowSensors].map((id) => this._renderWindowViewRow(id))}
              ${
                this.windowOpenDelay || this.windowCloseDelay
                  ? html`<div class="delay-view">
                      ${
                        this.windowOpenDelay
                          ? html`${localize("devices.window_open_delay", lang)}:
                            ${this.windowOpenDelay}s`
                          : nothing
                      }
                      ${this.windowOpenDelay && this.windowCloseDelay ? " · " : nothing}
                      ${
                        this.windowCloseDelay
                          ? html`${localize("devices.window_close_delay", lang)}:
                            ${this.windowCloseDelay}s`
                          : nothing
                      }
                    </div>`
                  : nothing
              }
            `
          : nothing
      }
    `;
  }

  private _renderWindowViewRow(entityId: string) {
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const isOpen = entityState?.state === "on";

    return html`
      <div class="view-row">
        <span class="view-name entity-link" @click=${() => openEntityInfo(this, entityId)}
          >${friendlyName}</span
        >
        <span class="occupancy-dot window-dot ${isOpen ? "on" : "off"}"></span>
      </div>
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
        <span class="occupancy-dot ${isOn ? "on" : "off"}"></span>
      </div>
    `;
  }

  // ─── Edit mode ───

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

    const areaWindowSensors = this.hass?.states
      ? allAreaEntities.filter(
          (e) =>
            e.entity_id.startsWith("binary_sensor.") &&
            ["window", "door", "opening"].includes(
              this.hass.states[e.entity_id]?.attributes?.device_class as string,
            ),
        )
      : [];
    const areaWindowIds = new Set(areaWindowSensors.map((e) => e.entity_id));
    const externalWindowSensors = [...this.windowSensors].filter((id) => !areaWindowIds.has(id));

    const lang = this.hass.language;

    return html`
      ${this._renderBlock({
        kind: "temp",
        icon: "mdi:thermometer",
        title: localize("devices.temp_sensors", lang),
        emptyText: localize("devices.no_temp_sensors", lang),
        areaSensors: areaTempSensors,
        externalSensors: externalTempSensor ? [externalTempSensor] : [],
        selectedCount: this.temperatureSensor ? 1 : 0,
      })}
      ${this._renderBlock({
        kind: "humidity",
        icon: "mdi:water-percent",
        title: localize("devices.humidity_sensors", lang),
        emptyText: localize("devices.no_humidity_sensors", lang),
        areaSensors: areaHumiditySensors,
        externalSensors: externalHumiditySensor ? [externalHumiditySensor] : [],
        selectedCount: this.humiditySensor ? 1 : 0,
      })}
      ${this._renderBlock({
        kind: "occupancy",
        icon: "mdi:account-eye",
        title: localize("devices.occupancy_sensors", lang),
        emptyText: localize("devices.no_occupancy_sensors", lang),
        areaSensors: areaOccupancySensors,
        externalSensors: externalOccupancySensors,
        selectedCount: this.occupancySensors.size,
      })}
      ${this._renderBlock({
        kind: "window",
        icon: "mdi:window-open-variant",
        title: localize("devices.window_sensors", lang),
        emptyText: localize("devices.no_window_sensors", lang),
        areaSensors: areaWindowSensors,
        externalSensors: externalWindowSensors,
        selectedCount: this.windowSensors.size,
        extras: this._renderWindowExtras(lang),
      })}
      ${this._renderGlobalAdd(lang)}
    `;
  }

  private _renderWindowExtras(lang: string) {
    if (this.windowSensors.size === 0) return nothing;
    return html`
      <div class="delay-fields">
        <ha-textfield
          type="number"
          min="0"
          suffix="s"
          .label=${localize("devices.window_open_delay", lang)}
          .value=${String(this.windowOpenDelay)}
          @change=${this._onWindowOpenDelayChange}
        ></ha-textfield>
        <ha-textfield
          type="number"
          min="0"
          suffix="s"
          .label=${localize("devices.window_close_delay", lang)}
          .value=${String(this.windowCloseDelay)}
          @change=${this._onWindowCloseDelayChange}
        ></ha-textfield>
      </div>
      ${
        this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300
          ? html`
              <div class="delay-hint">
                <ha-icon icon="mdi:information-outline"></ha-icon>
                ${localize("devices.underfloor_delay_hint", lang)}
              </div>
            `
          : nothing
      }
    `;
  }

  private _renderGlobalAdd(lang: string) {
    if (this._pickerOpen) {
      return html`
        <div class="global-add">
          <ha-entity-picker
            .hass=${this.hass}
            .includeDomains=${[
              "sensor",
              "binary_sensor",
              "climate",
              "input_number",
              "input_boolean",
            ]}
            .entityFilter=${this._globalEntityFilter}
            .value=${""}
            .autofocus=${true}
            label=${localize("devices.add_entity", lang)}
            @value-changed=${this._onGlobalPickerValueChanged}
          ></ha-entity-picker>
          <ha-icon-button
            class="picker-close"
            .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
            @click=${() => (this._pickerOpen = false)}
          ></ha-icon-button>
        </div>
      `;
    }
    return html`
      <button type="button" class="add-button global" @click=${() => (this._pickerOpen = true)}>
        <ha-icon icon="mdi:plus"></ha-icon>
        ${localize("devices.add_entity", lang)}
      </button>
    `;
  }

  private _renderBlock(opts: {
    kind: SensorKind;
    icon: string;
    title: string;
    emptyText: string;
    areaSensors: { entity_id: string }[];
    externalSensors: string[];
    selectedCount: number;
    extras?: unknown;
  }) {
    const total = opts.areaSensors.length + opts.externalSensors.length;
    const isCollapsed = this._collapsed[opts.kind] ?? true;
    return html`
      <div class="sensor-block ${isCollapsed ? "collapsed" : ""}">
        <div class="block-header" @click=${() => this._toggleBlock(opts.kind)}>
          <ha-icon icon=${opts.icon}></ha-icon>
          <div class="block-title">${opts.title}</div>
          ${
            opts.selectedCount > 0
              ? html`<span class="count-chip has-selection">${opts.selectedCount}</span>`
              : total > 0
                ? html`<span class="count-chip">${total}</span>`
                : nothing
          }
          <ha-icon
            class="chevron ${isCollapsed ? "collapsed" : ""}"
            icon="mdi:chevron-down"
          ></ha-icon>
        </div>
        ${
          isCollapsed
            ? nothing
            : html`
                <div class="block-body">
                  <div class="row-list">
                    ${
                      opts.areaSensors.length > 0 || opts.externalSensors.length > 0
                        ? html`
                            ${opts.areaSensors.map((e) =>
                              this._renderEditRow(e.entity_id, opts.kind, false),
                            )}
                            ${opts.externalSensors.map((id) =>
                              this._renderEditRow(id, opts.kind, true),
                            )}
                          `
                        : html`<div class="empty-row">${opts.emptyText}</div>`
                    }
                  </div>
                  ${opts.extras ?? nothing}
                </div>
              `
        }
      </div>
    `;
  }

  private _toggleBlock(kind: SensorKind) {
    const currentlyCollapsed = this._collapsed[kind] ?? true;
    this._collapsed = { ...this._collapsed, [kind]: !currentlyCollapsed };
  }

  private _renderEditRow(entityId: string, kind: SensorKind, external: boolean) {
    const state = this.hass.states[entityId];
    const friendlyName = (state?.attributes?.friendly_name as string) || entityId;
    const lang = this.hass.language;

    if (kind === "occupancy" || kind === "window") {
      const set = kind === "occupancy" ? this.occupancySensors : this.windowSensors;
      const isSelected = set.has(entityId);
      const isOn = state?.state === "on";
      const dotClass = kind === "window" ? "occupancy-dot window-dot" : "occupancy-dot";
      const onChange = (checked: boolean) =>
        kind === "occupancy"
          ? this._onOccupancyToggle(entityId, checked)
          : this._onWindowToggle(entityId, checked);
      return html`
        <div
          class="row ${isSelected ? "selected" : ""}"
          @click=${(e: Event) => {
            if ((e.target as HTMLElement).tagName === "HA-CHECKBOX") return;
            onChange(!isSelected);
          }}
        >
          <ha-checkbox
            .checked=${isSelected}
            @change=${(e: Event) => {
              const t = e.target as HTMLElement & { checked: boolean };
              onChange(t.checked);
            }}
          ></ha-checkbox>
          <div class="row-info">
            <div class="row-name-line">
              <span class="row-name">${friendlyName}</span>
              ${
                external
                  ? html`<span class="external-badge"
                      >${localize("devices.other_area", lang)}</span
                    >`
                  : nothing
              }
            </div>
            <div class="row-eid">${entityId}</div>
          </div>
          <span class="${dotClass} ${isOn ? "on" : "off"}"></span>
        </div>
      `;
    }

    const selected = kind === "temp" ? this.temperatureSensor : this.humiditySensor;
    const isSelected = selected === entityId;
    const unit = kind === "temp" ? tempUnit(this.hass) : "%";
    const currentValue = entityId.startsWith("climate.")
      ? state?.attributes?.current_temperature
      : state?.state;
    const hasValue = currentValue && currentValue !== "unknown" && currentValue !== "unavailable";
    const formatted = hasValue
      ? `${kind === "humidity" ? Math.round(Number(currentValue)) : Number(currentValue).toFixed(1)}${unit}`
      : "";

    return html`
      <div
        class="row ${isSelected ? "selected" : ""}"
        @click=${() => this._onSensorSelected(isSelected ? "" : entityId, kind)}
      >
        <ha-radio .checked=${isSelected} name="${kind}-sensor"></ha-radio>
        <div class="row-info">
          <div class="row-name-line">
            <span class="row-name">${friendlyName}</span>
            ${
              external
                ? html`<span class="external-badge">${localize("devices.other_area", lang)}</span>`
                : nothing
            }
          </div>
          <div class="row-eid">${entityId}</div>
        </div>
        ${formatted ? html`<span class="value-chip">${formatted}</span>` : nothing}
      </div>
    `;
  }

  private _globalEntityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    const idAfterDot = id.substring(id.indexOf(".") + 1);
    if (idAfterDot.startsWith("roommind_")) return false;
    if (this.temperatureSensor === id) return false;
    if (this.humiditySensor === id) return false;
    if (this.occupancySensors.has(id)) return false;
    if (this.windowSensors.has(id)) return false;
    if (id.startsWith("sensor.")) {
      const dc = this.hass.states[id]?.attributes?.device_class;
      return dc === "temperature" || dc === "humidity";
    }
    if (id.startsWith("binary_sensor.")) {
      const dc = this.hass.states[id]?.attributes?.device_class;
      return (
        dc === "occupancy" ||
        dc === "motion" ||
        dc === "presence" ||
        dc === "window" ||
        dc === "door" ||
        dc === "opening"
      );
    }
    if (id.startsWith("climate.")) {
      return this.hass.states[id]?.attributes?.current_temperature != null;
    }
    return id.startsWith("input_number.") || id.startsWith("input_boolean.");
  };

  private _onGlobalPickerValueChanged = (e: CustomEvent) => {
    const entityId = e.detail?.value as string;
    const picker = e.target as HTMLElement & { value: string };
    picker.value = "";
    if (!entityId) {
      return;
    }

    if (entityId.startsWith("binary_sensor.")) {
      const dc = this.hass.states[entityId]?.attributes?.device_class;
      if (dc === "window" || dc === "door" || dc === "opening") {
        if (!this.windowSensors.has(entityId)) this._onWindowToggle(entityId, true);
      } else if (!this.occupancySensors.has(entityId)) {
        this._onOccupancyToggle(entityId, true);
      }
    } else if (entityId.startsWith("input_boolean.")) {
      if (!this.occupancySensors.has(entityId)) this._onOccupancyToggle(entityId, true);
    } else if (entityId.startsWith("input_number.")) {
      const uom = this.hass.states[entityId]?.attributes?.unit_of_measurement;
      this._onSensorSelected(entityId, uom === "%" ? "humidity" : "temp");
    } else if (entityId.startsWith("climate.")) {
      this._onSensorSelected(entityId, "temp");
    } else {
      const dc = this.hass.states[entityId]?.attributes?.device_class;
      this._onSensorSelected(entityId, dc === "humidity" ? "humidity" : "temp");
    }
    this._pickerOpen = false;
  };

  private _onSensorSelected(entityId: string, kind: "temp" | "humidity") {
    const key = kind === "temp" ? "temperature_sensor" : "humidity_sensor";
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key, value: entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onOccupancyToggle(entityId: string, checked: boolean) {
    const next = new Set(this.occupancySensors);
    if (checked) next.add(entityId);
    else next.delete(entityId);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "occupancy_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindowToggle(entityId: string, checked: boolean) {
    const next = new Set(this.windowSensors);
    if (checked) next.add(entityId);
    else next.delete(entityId);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "window_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindowOpenDelayChange = (e: Event) => {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "window_open_delay", value },
        bubbles: true,
        composed: true,
      }),
    );
  };

  private _onWindowCloseDelayChange = (e: Event) => {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "window_close_delay", value },
        bubbles: true,
        composed: true,
      }),
    );
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-sensor-section": RsSensorSection;
  }
}

import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, DeviceConfig, DeviceType } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { tempUnit, toDisplayDelta, toCelsiusDelta, usesFahrenheit } from "../utils/temperature";
import { resolveHeatingSystemType } from "../utils/device-utils";
import { formatNumber } from "../utils/format";
import { tokens } from "../styles/tokens";
import { inputStyles } from "../styles/input-styles";
import { formStyles } from "../styles/form-styles";
import type { RsSegmentOption } from "./shared/rs-segmented";
import "./shared/rs-field";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";
import "./shared/rs-segmented";

/**
 * UI-only sentinel for "inherit the global setting".  ha-select cannot render an
 * option whose value is the empty string, so the stored "" would show up as a
 * blank field.  Mapped back to "" on save; "__keep__" keeps its own meaning
 * (send no fan mode at all) and must not be folded into this.
 */
const INHERIT = "__inherit__";

const fromInherit = (value: string | undefined): string => (value === INHERIT ? "" : (value ?? ""));

/** Below this own width the dialog shows the device list and one device's settings in turn. */
const NARROW_PX = 600;

/** `_returnFocus` value: focus the first entry of the device list (after a removal). */
const LIST_FOCUS = "\u0000list";

type IdleAction = NonNullable<DeviceConfig["idle_action"]>;

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
  /** Device the edit view opens with (e.g. the row the user tapped). */
  @property({ type: String }) public focusEntity = "";
  @state() private _showBoostHint = false;
  @state() private _selectedThermostats: Set<string> = new Set();
  @state() private _selectedCoolingDevices: Set<string> = new Set();
  @state() private _heatingSystemType = "";
  @state() private _selectedForEdit = "";
  /** Narrow layout: the selected device's settings replace the list. */
  @state() private _detailOpen = false;
  @state() private _narrow = false;
  /** Device whose removal waits for confirmation. */
  @state() private _confirmRemove = "";

  private _resize?: ResizeObserver;
  /** Row to focus after going back from a device's settings (narrow layout). */
  private _returnFocus = "";
  /** Device just added; focus moves to it once it arrived in `devices`. */
  private _focusAdded = "";

  connectedCallback(): void {
    super.connectedCallback();
    this._resize = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      const narrow = width > 0 && width < NARROW_PX;
      if (narrow !== this._narrow) this._narrow = narrow;
    });
    this._resize.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._resize?.disconnect();
  }

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
        this._detailOpen = false;
      }
      if (!this._selectedForEdit && this.devices.length > 0) {
        this._selectedForEdit = this._orderedDevices()[0].entity_id;
      }
    }
    if (changed.has("focusEntity") && this.devices.some((d) => d.entity_id === this.focusEntity)) {
      this._selectedForEdit = this.focusEntity;
      this._detailOpen = true;
    }
  }

  protected updated(changed: PropertyValues): void {
    if (!this.editing) return;
    const root = this.renderRoot;
    if (this._returnFocus === LIST_FOCUS) {
      if (changed.has("devices")) {
        this._returnFocus = "";
        void this._focusWhenReady(".list rs-list-row, .list ha-entity-picker");
      }
      return;
    }
    if (this._focusAdded && changed.has("devices")) {
      // The pressed suggestion is gone: continue at the new device's settings or row
      const id = this._focusAdded;
      this._focusAdded = "";
      void this._focusWhenReady(
        this._narrow ? ".back" : `rs-list-row[data-eid="${CSS.escape(id)}"]`,
      );
      return;
    }
    if (changed.has("_confirmRemove") && changed.get("_confirmRemove") !== undefined) {
      // The pressed control is gone either way: focus the safe answer, or the row again
      if (this._confirmRemove) void this._focusWhenReady(".confirm ha-button");
      else void this._focusWhenReady("rs-list-row.remove");
    }
    // Only a switch the user made moves the focus; opening the dialog leaves it to the dialog
    if (!this._narrow || changed.get("_detailOpen") === undefined) return;
    if (this._detailOpen) {
      root.querySelector<HTMLElement>(".back")?.focus();
    } else if (this._returnFocus) {
      const selector = `rs-list-row[data-eid="${CSS.escape(this._returnFocus)}"]`;
      this._returnFocus = "";
      void this._focusWhenReady(selector);
    }
  }

  /** Focus after the element rendered its own content (ha-button focuses an inner button). */
  private async _focusWhenReady(selector: string) {
    const el = this.renderRoot.querySelector<HTMLElement & { updateComplete?: Promise<unknown> }>(
      selector,
    );
    await el?.updateComplete;
    el?.focus();
  }

  static styles = [
    tokens,
    inputStyles,
    formStyles,
    css`
      :host {
        display: block;
      }

      .md {
        display: grid;
        grid-template-columns: minmax(0, 260px) minmax(0, 1fr);
        gap: var(--rs-space-5);
        align-items: start;
      }

      .md.single {
        grid-template-columns: minmax(0, 1fr);
      }

      .list {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-1);
        min-width: 0;
        --rs-list-row-padding: var(--rs-space-3);
      }

      /* rows reach past the column so their text lines up with the titles */
      .list rs-list-row {
        margin-inline: calc(-1 * var(--rs-space-3));
      }

      .list .group-title {
        margin: var(--rs-space-3) 0 var(--rs-space-1);
      }

      .list .group-title:first-child {
        margin-top: 0;
      }

      .list ha-entity-picker {
        margin-top: var(--rs-space-3);
      }

      .detail {
        --rs-form-inline: var(--rs-space-4);
        min-width: 0;
      }

      .detail.box {
        padding: var(--rs-space-2) var(--rs-space-4) var(--rs-space-4);
        border: 1px solid var(--rs-border);
        border-radius: var(--rs-radius);
      }

      .detail.flat {
        --rs-form-inline: var(--rs-space-6);
      }

      .detail-head {
        margin: 0 calc(-1 * var(--rs-form-inline)) var(--rs-space-3);
        --rs-list-row-padding: var(--rs-form-inline);
      }

      .back {
        display: inline-flex;
        align-items: center;
        gap: var(--rs-space-2);
        min-height: var(--rs-touch);
        margin: calc(-1 * var(--rs-space-2)) 0 var(--rs-space-2) calc(-1 * var(--rs-space-2));
        padding: 0 var(--rs-space-3) 0 var(--rs-space-2);
        border: none;
        border-radius: var(--rs-radius-sm);
        background: none;
        color: var(--primary-color);
        font: inherit;
        font-size: var(--rs-font-md);
        font-weight: 500;
        cursor: pointer;
        --mdc-icon-size: 20px;
      }

      .back:hover {
        background: var(--rs-fill-primary);
      }

      .back:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      .room-section {
        margin-top: var(--rs-space-6);
        padding-top: var(--rs-space-5);
        border-top: 1px solid var(--rs-border);
      }

      .confirm {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-3);
        padding: var(--rs-space-3);
        border-radius: var(--rs-radius-sm);
        background: color-mix(in srgb, var(--rs-err) 8%, transparent);
      }

      .confirm p {
        margin: 0;
        font-size: var(--rs-font-md);
        line-height: 1.5;
      }

      .confirm .actions {
        display: flex;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
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
    const l = this.hass.language;
    const ordered = [
      ...this.devices.filter((d) => d.type === "trv"),
      ...this.devices.filter((d) => d.type !== "trv"),
    ];
    return html`
      ${ordered.map((d) => this._renderViewRow(d))}
      <rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("detail.devices.add", l)}
        @row-click=${(e: Event) => this._fireEdit(e)}
      ></rs-list-row>
    `;
  }

  /** "Thermostat · Heizkörper · Absenkung · Direktes Ventil": type and what is set apart. */
  private _deviceSummary(device: DeviceConfig): string {
    const l = this.hass.language;
    const parts: string[] = [localize(device.type === "trv" ? "card.thermostat" : "card.ac", l)];
    if (device.type === "trv" && this._heatingSystemType) {
      parts.push(
        this._heatingSystemType === "radiator"
          ? localize("devices.system_type_radiator", l)
          : this._heatingSystemType === "underfloor"
            ? localize("devices.system_type_underfloor", l)
            : this._heatingSystemType,
      );
    }
    if (device.idle_action === "fan_only") {
      parts.push(
        localize("devices.idle_action_fan_only", l) +
          (device.idle_fan_mode ? ` (${device.idle_fan_mode})` : ""),
      );
    } else if (device.idle_action === "low") {
      parts.push(localize("devices.idle_action_low", l));
    } else if (device.idle_action === "setback") {
      parts.push(localize("devices.idle_action_setback", l));
    }
    const hasValve =
      device.type === "trv" && !!device.valve_opening_entity && !!device.valve_closing_entity;
    if (device.setpoint_mode === "direct" && this.selectedTempSensor && !hasValve) {
      parts.push(localize("devices.setpoint_mode_direct", l));
    }
    if (hasValve && this.selectedTempSensor) parts.push(localize("devices.valve_direct_badge", l));
    if (this.valveProtectionEnabled && this.valveProtectionExclude.has(device.entity_id)) {
      parts.push(localize("devices.valve_protection_excluded", l));
    }
    return parts.join(" · ");
  }

  private _renderViewRow(device: DeviceConfig) {
    const l = this.hass.language;
    const entityId = device.entity_id;
    const entityState = this.hass.states[entityId];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || entityId;
    const attrs = entityState?.attributes ?? {};
    const action = attrs.hvac_action as string | undefined;
    const unavailable = !entityState || entityState.state === "unavailable";

    let status = "";
    let color = "";
    if (unavailable) status = localize("detail.devices.unavailable", l);
    else if (action === "heating" || action === "preheating") {
      status = localize("card.state.heating", l);
      color = "var(--rs-heat)";
    } else if (action === "cooling") {
      status = localize("card.state.cooling", l);
      color = "var(--rs-cool)";
    } else if (entityState.state === "off") status = localize("card.state.off", l);
    const ct = attrs.current_temperature;
    // Device readings are already in Home Assistant's unit.
    const temp =
      typeof ct === "number" ? `${formatNumber(ct, this.hass, 1)} ${tempUnit(this.hass)}` : "";
    const value = [status, temp].filter(Boolean).join(" · ");

    return html`<rs-list-row
      clickable
      chevron
      .icon=${device.type === "trv" ? "mdi:thermostat" : "mdi:air-conditioner"}
      .iconColor=${color}
      icon-label=${localize("detail.more_info", l)}
      .heading=${friendlyName}
      .secondary=${this._deviceSummary(device)}
      .value=${value}
      @row-click=${(e: Event) => this._fireEdit(e, entityId)}
      @icon-click=${() => openEntityInfo(this, entityId)}
    ></rs-list-row>`;
  }

  private _fireEdit(e: Event, entityId?: string) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("edit-click", { detail: { entityId }, bubbles: true, composed: true }),
    );
  }

  /** TRVs first, then ACs, each in stored order (as on the room page). */
  private _orderedDevices(): DeviceConfig[] {
    return [
      ...this.devices.filter((d) => d.type === "trv"),
      ...this.devices.filter((d) => d.type !== "trv"),
    ];
  }

  private _name(entityId: string): string {
    return (this.hass.states[entityId]?.attributes?.friendly_name as string) || entityId;
  }

  /** What the device does right now and its own reading, for list rows and the detail head. */
  private _liveStatus(
    entityId: string,
    withMode: boolean,
  ): { text: string; color: string; temp: string } {
    const l = this.hass.language;
    const st = this.hass.states[entityId];
    if (!st || st.state === "unavailable") {
      return { text: localize("detail.devices.unavailable", l), color: "", temp: "" };
    }
    const action = st.attributes?.hvac_action as string | undefined;
    let text = "";
    let color = "";
    if (action === "heating" || action === "preheating") {
      text = localize("card.state.heating", l);
      color = "var(--rs-heat)";
    } else if (action === "cooling") {
      text = localize("card.state.cooling", l);
      color = "var(--rs-cool)";
    } else if (st.state === "off") {
      text = localize("card.state.off", l);
    } else if (withMode) {
      text = localize("detail.devices.mode", l, {
        mode: this.hass.formatEntityState?.(st) ?? st.state,
      });
    }
    const ct = st.attributes?.current_temperature;
    // Device readings are already in Home Assistant's unit.
    const temp =
      typeof ct === "number" ? `${formatNumber(ct, this.hass, 1)} ${tempUnit(this.hass)}` : "";
    return { text, color, temp };
  }

  /** Climate entities of the area (RoomMind's own excluded). */
  private _areaClimateIds(): string[] {
    return getEntitiesForArea(this.area.area_id, this.hass?.entities, this.hass?.devices)
      .map((e) => e.entity_id)
      .filter((id) => id.startsWith("climate.") && !id.startsWith("climate.roommind_"));
  }

  private _renderEditMode() {
    const device = this.devices.find((d) => d.entity_id === this._selectedForEdit);
    if (this._narrow) {
      if (this._detailOpen && device) {
        return html`<button type="button" class="back" @click=${this._onBack}>
            <ha-icon icon="mdi:arrow-left" aria-hidden="true"></ha-icon>
            ${localize("detail.devices.back", this.hass.language)}
          </button>
          <div class="detail flat">${this._renderDeviceDetail(device)}</div>`;
      }
      return html`${this._renderList()} ${this._renderRoomSection()}`;
    }
    return html`
      <div class="md ${device ? "" : "single"}">
        ${this._renderList()}
        ${device ? html`<div class="detail box">${this._renderDeviceDetail(device)}</div>` : nothing}
      </div>
      ${this._renderRoomSection()}
    `;
  }

  private _renderList() {
    const l = this.hass.language;
    const inRoom = new Set(this.devices.map((d) => d.entity_id));
    const suggestions = this._areaClimateIds().filter((id) => !inRoom.has(id));
    return html`<div class="list">
      ${
        this.devices.length
          ? html`<h4 class="group-title">${localize("detail.devices.in_room", l)}</h4>
              ${this._orderedDevices().map((d) => this._renderListRow(d))}`
          : nothing
      }
      ${
        suggestions.length
          ? html`<h4 class="group-title">${localize("detail.devices.in_area", l)}</h4>
              ${suggestions.map((id) => this._renderSuggestion(id))}`
          : nothing
      }
      ${
        !this.devices.length && !suggestions.length
          ? html`<p class="note">${localize("devices.no_climate", l)}</p>`
          : nothing
      }
      <ha-entity-picker
        .hass=${this.hass}
        .includeDomains=${["climate"]}
        .entityFilter=${this._entityFilter}
        .value=${""}
        .label=${localize("detail.devices.add", l)}
        @value-changed=${this._onEntityPicked}
      ></ha-entity-picker>
    </div>`;
  }

  private _renderListRow(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    const status = this._liveStatus(id, false);
    const external = !this._areaClimateIds().includes(id);
    const secondary = [
      localize(device.type === "trv" ? "devices.type_thermostat" : "devices.type_ac", l),
      status.text,
      external ? localize("devices.other_area", l) : "",
    ].filter(Boolean);
    return html`<rs-list-row
      clickable
      data-eid=${id}
      .chevron=${this._narrow}
      .selected=${!this._narrow && id === this._selectedForEdit}
      .icon=${device.type === "trv" ? "mdi:thermostat" : "mdi:air-conditioner"}
      .iconColor=${status.color}
      .heading=${this._name(id)}
      .secondary=${secondary.join(" · ")}
      .value=${status.temp}
      @row-click=${() => this._openDetail(id)}
    ></rs-list-row>`;
  }

  private _renderSuggestion(entityId: string) {
    const l = this.hass.language;
    return html`<rs-list-row
      clickable
      plain-icon
      icon="mdi:plus"
      .heading=${this._name(entityId)}
      .secondary=${localize("detail.devices.add_suggestion", l)}
      .value=${this._liveStatus(entityId, false).temp}
      @row-click=${() => this._addDevice(entityId)}
    ></rs-list-row>`;
  }

  /** Heating system type: one value for all TRVs of the room. */
  private _renderRoomSection() {
    if (this._selectedThermostats.size === 0) return nothing;
    const l = this.hass.language;
    return html`<section class="room-section group">
      <h4 class="group-title">
        ${localize("devices.heating_system_type", l)}
        <rs-info-icon .text=${localize("devices.heating_system_type_info", l)}></rs-info-icon>
      </h4>
      <p class="note">${localize("devices.heating_system_type_scope", l)}</p>
      <rs-segmented
        wrap
        .label=${localize("devices.heating_system_type", l)}
        .options=${[
          { value: "", label: localize("devices.system_type_none", l) },
          { value: "radiator", label: localize("devices.system_type_radiator", l) },
          { value: "underfloor", label: localize("devices.system_type_underfloor", l) },
        ]}
        .value=${this._heatingSystemType}
        @value-changed=${(e: CustomEvent<{ value: string }>) => {
          e.stopPropagation();
          this._onHeatingSystemTypeChange(e.detail.value);
        }}
      ></rs-segmented>
      ${
        this._showBoostHint
          ? html`<p class="note">${localize("devices.heating_system_type_boost_hint", l)}</p>`
          : nothing
      }
    </section>`;
  }

  /** Segmented choice with the stored value kept visible even when it is not offered. */
  private _choice(
    label: string,
    options: RsSegmentOption[],
    value: string,
    onPick: (value: string) => void,
    extra?: RsSegmentOption,
  ) {
    const opts = extra && !options.some((o) => o.value === value) ? [...options, extra] : options;
    return html`<rs-segmented
      wrap
      .label=${label}
      .options=${opts}
      .value=${value}
      @value-changed=${(e: CustomEvent<{ value: string }>) => {
        e.stopPropagation();
        onPick(e.detail.value);
      }}
    ></rs-segmented>`;
  }

  private _renderDeviceDetail(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    const isTrv = device.type === "trv";
    const status = this._liveStatus(id, true);
    const external = !this._areaClimateIds().includes(id);
    const hasSensor = !!this.selectedTempSensor;
    const hasValve = isTrv && !!device.valve_opening_entity && !!device.valve_closing_entity;
    const showValve = this._showValveFields(device);

    return html`
      <rs-list-row
        class="detail-head"
        wrap
        .icon=${isTrv ? "mdi:thermostat" : "mdi:air-conditioner"}
        .iconColor=${status.color}
        icon-label=${localize("detail.more_info", l)}
        .heading=${this._name(id)}
        .secondary=${[id, external ? localize("devices.other_area", l) : ""]
          .filter(Boolean)
          .join(" · ")}
        .value=${[status.text, status.temp].filter(Boolean).join(" · ")}
        @icon-click=${() => openEntityInfo(this, id)}
      ></rs-list-row>

      <div class="group">
        <rs-field
          .label=${localize("devices.type_label", l)}
          .info=${localize("devices.type_info", l)}
        >
          ${this._choice(
            localize("devices.type_label", l),
            [
              {
                value: "trv",
                label: localize("devices.type_thermostat", l),
                icon: "mdi:thermostat",
              },
              { value: "ac", label: localize("devices.type_ac", l), icon: "mdi:air-conditioner" },
            ],
            device.type,
            (v) => this._onDeviceTypeChange(id, v as DeviceType),
          )}
        </rs-field>
        ${hasSensor ? nothing : html`<p class="note">${localize("devices.managed_note", l)}</p>`}
      </div>

      ${hasSensor && !hasValve ? this._renderControlGroup(device) : nothing}
      ${this._renderIdleGroup(device)}
      ${isTrv && (showValve || this.valveProtectionEnabled) ? this._renderValveGroup(device) : nothing}
      ${device.type === "ac" ? this._renderCoilDryGroup(device) : nothing}
      <div class="group">${this._renderRemove(device)}</div>
    `;
  }

  private _renderControlGroup(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    return html`<div class="group">
      <h4 class="group-title">${localize("devices.group_control", l)}</h4>
      <rs-field
        .label=${localize("devices.setpoint_mode", l)}
        .info=${localize("devices.setpoint_mode_info", l)}
      >
        ${this._choice(
          localize("devices.setpoint_mode", l),
          [
            { value: "proportional", label: localize("devices.setpoint_mode_proportional", l) },
            { value: "direct", label: localize("devices.setpoint_mode_direct", l) },
          ],
          device.setpoint_mode ?? "proportional",
          (v) => this._onSetpointModeChange(id, v),
        )}
      </rs-field>
      ${
        device.setpoint_mode === "direct"
          ? html`<rs-field .info=${localize("devices.setpoint_offset_info", l)}>
              <ha-textfield
                .label=${localize("devices.setpoint_offset", l)}
                .suffix=${tempUnit(this.hass)}
                .value=${String(
                  Math.round(toDisplayDelta(device.setpoint_offset ?? 0, this.hass) * 10) / 10,
                )}
                type="number"
                .step=${usesFahrenheit(this.hass) ? "1" : "0.5"}
                .min=${String(Math.round(toDisplayDelta(-5, this.hass)))}
                .max=${String(Math.round(toDisplayDelta(5, this.hass)))}
                @change=${(e: Event) => {
                  const v = parseFloat((e.target as HTMLInputElement).value);
                  if (!isNaN(v)) this._onSetpointOffsetChange(id, v);
                }}
              ></ha-textfield>
            </rs-field>`
          : nothing
      }
    </div>`;
  }

  private _renderIdleGroup(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    const isTrv = device.type === "trv";
    const st = this.hass.states[id];
    const hvacModes = (st?.attributes?.hvac_modes ?? []) as string[];
    const fanModes = (st?.attributes?.fan_modes ?? []) as string[];
    const idle: IdleAction = device.idle_action ?? "off";
    const option = (value: IdleAction) => ({
      value,
      label: localize(`devices.idle_action_${value}`, l),
    });
    const options = isTrv
      ? [option("off"), option("low")]
      : [
          option("off"),
          ...(hvacModes.includes("fan_only") ? [option("fan_only")] : []),
          option("setback"),
        ];
    return html`<div class="group">
      <h4 class="group-title">
        ${localize("devices.idle_action", l)}
        <rs-info-icon
          .text=${localize(isTrv ? "devices.idle_info_trv" : "devices.idle_info_ac", l)}
        ></rs-info-icon>
      </h4>
      ${this._choice(
        localize("devices.idle_action", l),
        options,
        idle,
        (v) => this._onIdleActionChange(id, v),
        option(idle),
      )}
      ${
        !isTrv && idle === "fan_only"
          ? html`<rs-field .info=${localize("devices.idle_fan_mode_info", l)}>
              <ha-select
                .label=${localize("devices.idle_fan_mode", l)}
                .value=${device.idle_fan_mode === "" ? "__keep__" : (device.idle_fan_mode ?? "low")}
                .options=${[
                  { value: "__keep__", label: localize("devices.idle_fan_mode_keep", l) },
                  ...fanModes.map((fm) => ({ value: fm, label: fm })),
                ]}
                @selected=${(e: Event) => {
                  const v = getSelectValue(e);
                  this._onIdleFanModeChange(id, v === "__keep__" ? "" : v);
                }}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="__keep__"
                  >${localize("devices.idle_fan_mode_keep", l)}</ha-list-item
                >
                ${fanModes.map((fm) => html`<ha-list-item value=${fm}>${fm}</ha-list-item>`)}
              </ha-select>
            </rs-field>`
          : nothing
      }
      ${
        !isTrv && idle === "setback" && this.selectedTempSensor
          ? html`<rs-list-row
              switch
              wrap
              .heading=${localize("devices.setback_auto_off", l)}
              .checked=${device.setback_auto_off ?? false}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._onSetbackAutoOffChange(id, e.detail)}
            >
              <rs-info-icon
                slot="end"
                .text=${localize("devices.setback_auto_off_info", l)}
              ></rs-info-icon>
            </rs-list-row>`
          : nothing
      }
    </div>`;
  }

  /** Direct valve control needs the room sensor; offered when the TRV has number entities. */
  private _showValveFields(device: DeviceConfig): boolean {
    if (device.type !== "trv" || !this.selectedTempSensor) return false;
    const hasValve = !!device.valve_opening_entity && !!device.valve_closing_entity;
    return hasValve || this._deviceNumberEntities(device.entity_id).length > 0;
  }

  private _renderValveGroup(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    const numbers = this._deviceNumberEntities(id);
    const hasValve = !!device.valve_opening_entity && !!device.valve_closing_entity;
    // A recognised pair needs no entity picking: one switch, the pickers stay for anything else
    const pair = this._detectValvePair(numbers);
    const idleOpening = device.valve_closing_mode === "idle_opening";
    const asToggle =
      !!pair &&
      !idleOpening &&
      (!device.valve_opening_entity ||
        (device.valve_opening_entity === pair[0] && device.valve_closing_entity === pair[1]));
    const show = this._showValveFields(device);
    const picker = (value: string, label: string, onChange: (v: string) => void) =>
      html`<ha-entity-picker
        .hass=${this.hass}
        .includeDomains=${["number"]}
        .includeEntities=${numbers.length ? numbers : undefined}
        .value=${value}
        .label=${label}
        @value-changed=${(e: CustomEvent) => onChange(e.detail.value as string)}
      ></ha-entity-picker>`;

    return html`<div class="group">
      <h4 class="group-title">${localize("devices.group_valve", l)}</h4>
      ${
        show && asToggle
          ? html`<rs-list-row
              switch
              wrap
              .heading=${localize("devices.valve_direct_control", l)}
              .checked=${hasValve}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._onValveToggle(id, e.detail ? pair : null)}
            >
              <rs-info-icon
                slot="end"
                .text=${localize("devices.valve_direct_info", l)}
              ></rs-info-icon>
            </rs-list-row>`
          : nothing
      }
      ${
        show && !asToggle
          ? html`<rs-field .info=${localize("devices.valve_opening_info", l)}>
                ${picker(
                  device.valve_opening_entity ?? "",
                  localize("devices.valve_opening_entity", l),
                  (v) => this._onValveOpeningChange(id, v, numbers),
                )}
              </rs-field>
              <rs-field
                .info=${localize(
                  idleOpening ? "devices.valve_idle_opening_info" : "devices.valve_closing_info",
                  l,
                )}
              >
                ${picker(
                  device.valve_closing_entity ?? "",
                  localize(
                    idleOpening
                      ? "devices.valve_idle_opening_entity"
                      : "devices.valve_closing_entity",
                    l,
                  ),
                  (v) => this._onValveClosingChange(id, v),
                )}
              </rs-field>
              <rs-field
                .label=${localize("devices.valve_closing_mode", l)}
                .info=${localize("devices.valve_closing_mode_info", l)}
              >
                ${this._choice(
                  localize("devices.valve_closing_mode", l),
                  [
                    {
                      value: "closing_degree",
                      label: localize("devices.valve_closing_mode_closing_degree", l),
                    },
                    {
                      value: "idle_opening",
                      label: localize("devices.valve_closing_mode_idle_opening", l),
                    },
                  ],
                  idleOpening ? "idle_opening" : "closing_degree",
                  (v) => this._onValveClosingModeChange(id, v),
                )}
              </rs-field>`
          : nothing
      }
      ${
        this.valveProtectionEnabled
          ? html`<rs-list-row
              switch
              wrap
              .heading=${localize("devices.valve_protection_exclude", l)}
              .checked=${this.valveProtectionExclude.has(id)}
              @toggle-changed=${(e: CustomEvent<boolean>) =>
                this._onValveProtectionExcludeToggle(id, e.detail)}
            >
              <rs-info-icon
                slot="end"
                .text=${localize("devices.valve_protection_exclude_info", l)}
              ></rs-info-icon>
            </rs-list-row>`
          : nothing
      }
    </div>`;
  }

  private _renderCoilDryGroup(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    const coilDry = device.coil_dry ?? "inherit";
    const fanModes = (this.hass.states[id]?.attributes?.fan_modes ?? []) as string[];
    const modeInherit = localize("devices.coil_dry_mode_inherit", l, {
      value: this.coilDryModeGlobal,
    });
    const fanInherit = localize("devices.coil_dry_fan_mode_inherit", l, {
      value: this._globalFanModeLabel(l),
    });
    return html`<div class="group">
      <h4 class="group-title">
        ${localize("devices.group_coil_dry", l)}
        <rs-info-icon .text=${localize("devices.coil_dry_info", l)}></rs-info-icon>
      </h4>
      ${this._choice(
        localize("devices.group_coil_dry", l),
        [
          {
            value: "inherit",
            label: localize(
              this.coilDryEnabledGlobal
                ? "devices.coil_dry_inherit_on"
                : "devices.coil_dry_inherit_off",
              l,
            ),
          },
          { value: "on", label: localize("devices.coil_dry_on", l) },
          { value: "off", label: localize("devices.coil_dry_off", l) },
        ],
        coilDry,
        (v) => this._onCoilDryChange(id, v),
      )}
      ${
        coilDry === "inherit" && !this.coilDryEnabledGlobal
          ? html`<p class="note">${localize("devices.coil_dry_global_off_hint", l)}</p>`
          : nothing
      }
      ${
        coilDry !== "off"
          ? html`<rs-field
                .info=${localize("devices.coil_dry_minutes_info", l, {
                  minutes: this.coilDryMinutesGlobal,
                })}
              >
                <ha-textfield
                  .value=${String(device.coil_dry_minutes ?? 0)}
                  .label=${localize("devices.coil_dry_minutes", l)}
                  suffix="min"
                  type="number"
                  step="1"
                  min="0"
                  max="60"
                  @change=${(e: Event) => {
                    const v = parseInt((e.target as HTMLInputElement).value, 10);
                    if (!isNaN(v) && v >= 0 && v <= 60) this._onCoilDryMinutesChange(id, v);
                  }}
                ></ha-textfield>
              </rs-field>
              <rs-field
                .label=${localize("devices.coil_dry_mode", l)}
                .info=${localize("devices.coil_dry_mode_info", l)}
              >
                ${this._choice(
                  localize("devices.coil_dry_mode", l),
                  [
                    { value: INHERIT, label: modeInherit },
                    { value: "fan_only", label: "fan_only" },
                    { value: "dry", label: "dry" },
                  ],
                  device.coil_dry_mode || INHERIT,
                  (v) => this._onCoilDryModeChange(id, fromInherit(v)),
                )}
              </rs-field>
              ${
                device.coil_dry_mode === "dry"
                  ? html`<p class="note warn">
                      <ha-icon icon="mdi:alert-outline" aria-hidden="true"></ha-icon>
                      <span>${localize("coil_dry.mode_dry_warning", l)}</span>
                    </p>`
                  : nothing
              }
              <rs-field .info=${localize("devices.coil_dry_fan_mode_info", l)}>
                <ha-select
                  .label=${localize("devices.coil_dry_fan_mode", l)}
                  .value=${device.coil_dry_fan_mode || INHERIT}
                  .options=${[
                    { value: INHERIT, label: fanInherit },
                    { value: "__keep__", label: localize("devices.coil_dry_fan_mode_keep", l) },
                    ...fanModes.map((fm) => ({ value: fm, label: fm })),
                  ]}
                  @selected=${(e: Event) =>
                    this._onCoilDryFanModeChange(id, fromInherit(getSelectValue(e)))}
                  @closed=${(e: Event) => e.stopPropagation()}
                  fixedMenuPosition
                >
                  <ha-list-item value=${INHERIT}>${fanInherit}</ha-list-item>
                  <ha-list-item value="__keep__"
                    >${localize("devices.coil_dry_fan_mode_keep", l)}</ha-list-item
                  >
                  ${fanModes.map((fm) => html`<ha-list-item value=${fm}>${fm}</ha-list-item>`)}
                </ha-select>
              </rs-field>`
          : nothing
      }
    </div>`;
  }

  /** Removing drops the device's own settings, so it asks once. */
  private _renderRemove(device: DeviceConfig) {
    const l = this.hass.language;
    const id = device.entity_id;
    if (this._confirmRemove !== id) {
      return html`<rs-list-row
        class="remove"
        clickable
        variant="danger"
        icon="mdi:minus-circle-outline"
        .heading=${localize("detail.devices.remove", l)}
        @row-click=${() => {
          this._confirmRemove = id;
        }}
      ></rs-list-row>`;
    }
    return html`<div
      class="confirm"
      role="group"
      aria-label=${localize("detail.devices.remove", l)}
    >
      <p>${localize("detail.devices.remove_confirm", l, { name: this._name(id) })}</p>
      <div class="actions">
        <ha-button
          appearance="plain"
          @click=${() => {
            this._confirmRemove = "";
          }}
          >${localize("detail.cancel", l)}</ha-button
        >
        <ha-button variant="danger" @click=${() => this._removeDevice(id)}
          >${localize("detail.devices.remove_action", l)}</ha-button
        >
      </div>
    </div>`;
  }

  private _openDetail(entityId: string) {
    this._selectedForEdit = entityId;
    this._confirmRemove = "";
    this._detailOpen = true;
  }

  private _onBack = () => {
    this._returnFocus = this._selectedForEdit;
    this._confirmRemove = "";
    this._detailOpen = false;
  };

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

  /** Adds a climate entity with its detected type and opens its settings. */
  private _addDevice(entityId: string) {
    if (this.devices.some((d) => d.entity_id === entityId)) return;
    const type: DeviceType = this._detectClimateType(entityId) === "thermostat" ? "trv" : "ac";
    this._focusAdded = entityId;
    this._fireDeviceChanged([...this.devices, { entity_id: entityId, type, role: "auto" }]);
    this._selectedForEdit = entityId;
    this._confirmRemove = "";
    this._detailOpen = true;
  }

  private _removeDevice(entityId: string) {
    this._confirmRemove = "";
    this._returnFocus = LIST_FOCUS;
    this._fireDeviceChanged(this.devices.filter((d) => d.entity_id !== entityId));
  }

  private _onDeviceTypeChange(entityId: string, deviceType: DeviceType) {
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
      // Direct valve control is TRV-only; the backend schema rejects it for ACs.
      if (deviceType === "ac") {
        delete updated.valve_opening_entity;
        delete updated.valve_closing_entity;
        delete updated.valve_closing_mode;
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

  private _onSetbackAutoOffChange(entityId: string, enabled: boolean): void {
    const newDevices = this.devices.map((d) => {
      if (d.entity_id !== entityId) return d;
      const updated = { ...d };
      if (enabled) updated.setback_auto_off = true;
      else delete updated.setback_auto_off;
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

  private _onSetpointOffsetChange(entityId: string, displayValue: number): void {
    const celsius = Math.max(
      -5,
      Math.min(5, Math.round(toCelsiusDelta(displayValue, this.hass) * 100) / 100),
    );
    this._fireDeviceChanged(
      this.devices.map((d) => (d.entity_id === entityId ? { ...d, setpoint_offset: celsius } : d)),
    );
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

  /** Valve number entities of the TRV's own device (opening/closing degree live there). */
  private _deviceNumberEntities(entityId: string): string[] {
    const deviceId = this.hass.entities?.[entityId]?.device_id;
    if (!deviceId) return [];
    const numbers = Object.values(this.hass.entities)
      .filter((e) => e.device_id === deviceId && e.entity_id.startsWith("number."))
      .map((e) => e.entity_id);
    // Not every number of a TRV is a valve degree (calibration, external temperature input);
    // renamed or translated entity ids fall back to all numbers of the device
    const valve = numbers.filter((eid) => /valve|opening|closing|ventil|vanne/.test(eid));
    return valve.length ? valve : numbers;
  }

  /** Opening and closing degree of the device, recognised by name (Zigbee2MQTT: *_valve_opening_degree). */
  private _detectValvePair(numbers: string[]): [string, string] | null {
    for (const opening of numbers) {
      if (!opening.includes("opening")) continue;
      const closing = opening.replace(/opening/g, "closing");
      if (numbers.includes(closing)) return [opening, closing];
    }
    return null;
  }

  private _onValveToggle(entityId: string, pair: [string, string] | null): void {
    this._fireDeviceChanged(
      this.devices.map((d) => {
        if (d.entity_id !== entityId) return d;
        const updated = { ...d };
        delete updated.valve_opening_entity;
        delete updated.valve_closing_entity;
        delete updated.valve_closing_mode;
        if (pair) [updated.valve_opening_entity, updated.valve_closing_entity] = pair;
        return updated;
      }),
    );
  }

  private _onValveOpeningChange(entityId: string, value: string, deviceNumbers: string[]): void {
    // The closing degree sits next to the opening degree (Zigbee2MQTT: *_valve_closing_degree)
    const sibling = value.replace(/opening/g, "closing");
    const closing = sibling !== value && deviceNumbers.includes(sibling) ? sibling : "";
    this._fireDeviceChanged(
      this.devices.map((d) => {
        if (d.entity_id !== entityId) return d;
        const updated = { ...d };
        if (!value) {
          delete updated.valve_opening_entity;
          delete updated.valve_closing_entity;
          delete updated.valve_closing_mode;
          return updated;
        }
        updated.valve_opening_entity = value;
        if (!updated.valve_closing_entity && closing) updated.valve_closing_entity = closing;
        return updated;
      }),
    );
  }

  private _onValveClosingChange(entityId: string, value: string): void {
    this._fireDeviceChanged(
      this.devices.map((d) => {
        if (d.entity_id !== entityId) return d;
        const updated = { ...d };
        if (value) updated.valve_closing_entity = value;
        else delete updated.valve_closing_entity;
        return updated;
      }),
    );
  }

  private _onValveClosingModeChange(entityId: string, value: string): void {
    const current = this.devices.find((d) => d.entity_id === entityId)?.valve_closing_mode;
    if (value !== "closing_degree" && value !== "idle_opening") return;
    if (value === (current ?? "closing_degree")) return;
    this._fireDeviceChanged(
      this.devices.map((d) => {
        if (d.entity_id !== entityId) return d;
        const updated = { ...d };
        // The default stays unstored, so devices of everyone else keep their saved form
        if (value === "idle_opening") updated.valve_closing_mode = "idle_opening";
        else delete updated.valve_closing_mode;
        return updated;
      }),
    );
  }

  private _onHeatingSystemTypeChange(value: string) {
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
    this._addDevice(entityId);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-device-section": RsDeviceSection;
  }
}

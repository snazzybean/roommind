import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, HassArea } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { openEntityInfo } from "../utils/events";

@customElement("rs-window-section")
export class RsWindowSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public windowSensors: Set<string> = new Set();
  @property({ type: Number }) public windowOpenDelay = 0;
  @property({ type: Number }) public windowCloseDelay = 0;
  @property({ type: String }) public heatingSystemType = "";
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

    .device-row ha-checkbox {
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
    if (this.windowSensors.size === 0) {
      return nothing;
    }

    return html`
      <div class="device-group">
        <div class="section-subtitle">
          ${localize("devices.window_sensors", this.hass.language)}
        </div>
        ${[...this.windowSensors].map((id) => this._renderWindowViewRow(id))}
        ${this.windowOpenDelay || this.windowCloseDelay
          ? html`
              <div class="delay-view">
                ${this.windowOpenDelay
                  ? html`${localize("devices.window_open_delay", this.hass.language)}:
                    ${this.windowOpenDelay}s`
                  : nothing}
                ${this.windowOpenDelay && this.windowCloseDelay ? " · " : nothing}
                ${this.windowCloseDelay
                  ? html`${localize("devices.window_close_delay", this.hass.language)}:
                    ${this.windowCloseDelay}s`
                  : nothing}
              </div>
            `
          : nothing}
      </div>
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
        <span
          class="view-value"
          style="color: ${isOpen ? "var(--warning-color, #ff9800)" : "var(--secondary-text-color)"}"
        >
          ${isOpen ? "\u25CF" : "\u25CB"}
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

    return html`
      <div class="device-group">
        <div class="section-subtitle">
          ${localize("devices.window_sensors", this.hass.language)}
        </div>
        <div class="device-list-scroll">
          ${areaWindowSensors.length > 0
            ? areaWindowSensors.map((entity) => this._renderWindowRow(entity.entity_id, false))
            : html`<div class="no-devices">
                ${localize("devices.no_window_sensors", this.hass.language)}
              </div>`}
          ${externalWindowSensors.map((id) => this._renderWindowRow(id, true))}
        </div>
        ${this.windowSensors.size > 0
          ? html`
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
              ${this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300
                ? html`
                    <div class="delay-hint">
                      <ha-icon icon="mdi:information-outline"></ha-icon>
                      ${localize("devices.underfloor_delay_hint", this.hass.language)}
                    </div>
                  `
                : nothing}
            `
          : nothing}
      </div>
    `;
  }

  private _renderWindowRow(entityId: string, external: boolean) {
    const isSelected = this.windowSensors.has(entityId);
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
              ? html`<span class="external-badge"
                  >${localize("devices.other_area", this.hass.language)}</span
                >`
              : nothing}
          </div>
          <div class="device-entity">${entityId}</div>
        </div>
        <span
          class="device-value"
          style="color: ${isOpen ? "var(--warning-color, #ff9800)" : "var(--secondary-text-color)"}"
        >
          ${isOpen ? "\u25CF" : "\u25CB"}
        </span>
      </div>
    `;
  }

  private _onWindowSensorToggle(entityId: string, checked: boolean) {
    const next = new Set(this.windowSensors);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this.dispatchEvent(
      new CustomEvent("window-config-changed", {
        detail: { key: "window_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindowOpenDelayChange(e: Event) {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("window-config-changed", {
        detail: { key: "window_open_delay", value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindowCloseDelayChange(e: Event) {
    const value = Math.max(0, parseInt((e.target as HTMLInputElement).value) || 0);
    this.dispatchEvent(
      new CustomEvent("window-config-changed", {
        detail: { key: "window_close_delay", value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-window-section": RsWindowSection;
  }
}

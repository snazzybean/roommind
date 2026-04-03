/**
 * rs-settings-reset – Reset thermal data.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { fireSaveStatus, getSelectValue } from "../../utils/events";

@customElement("rs-settings-reset")
export class RsSettingsReset extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _resetSelectedRoom = "";

  render() {
    const l = this.hass.language;
    const configuredRooms = Object.entries(this.rooms)
      .map(([areaId]) => ({
        areaId,
        name: this.hass.areas?.[areaId]?.name ?? areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    return html`
      <div class="settings-section first">
        <div class="reset-row">
          <div class="reset-text">
            <span class="toggle-label">${localize("settings.reset_all_label", l)}</span>
            <span class="toggle-hint">${localize("settings.reset_all_hint", l)}</span>
          </div>
          <button class="reset-btn" @click=${this._resetAllModels}>
            <ha-icon icon="mdi:restart-alert"></ha-icon>
            ${localize("settings.reset_all_btn", l)}
          </button>
        </div>
      </div>

      <div class="settings-section">
        <div class="reset-text" style="margin-bottom: 12px">
          <span class="toggle-label">${localize("settings.reset_room_label", l)}</span>
          <span class="toggle-hint">${localize("settings.reset_room_hint", l)}</span>
        </div>
        ${configuredRooms.length > 0
          ? html`
              <div class="reset-room-row">
                <ha-select
                  .value=${this._resetSelectedRoom}
                  .label=${localize("settings.reset_room_select", l)}
                  .options=${configuredRooms.map((room) => ({
                    value: room.areaId,
                    label: room.name,
                  }))}
                  fixedMenuPosition
                  @selected=${(e: Event) => {
                    this._resetSelectedRoom = getSelectValue(e);
                  }}
                  @closed=${(e: Event) => e.stopPropagation()}
                >
                  ${configuredRooms.map(
                    (room) => html`<ha-list-item value=${room.areaId}>${room.name}</ha-list-item>`,
                  )}
                </ha-select>
                ${this._resetSelectedRoom
                  ? html`<ha-icon-button
                      .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                      @click=${() => {
                        this._resetSelectedRoom = "";
                      }}
                    ></ha-icon-button>`
                  : nothing}
                <button
                  class="reset-btn"
                  ?disabled=${!this._resetSelectedRoom}
                  @click=${() =>
                    this._resetSelectedRoom && this._resetRoomModel(this._resetSelectedRoom)}
                >
                  <ha-icon icon="mdi:restart"></ha-icon>
                  ${localize("settings.reset_btn", l)}
                </button>
              </div>
            `
          : html`<p class="hint">${localize("settings.reset_no_rooms", l)}</p>`}
      </div>
    `;
  }

  private async _resetRoomModel(areaId: string) {
    const l = this.hass.language;
    if (!confirm(localize("settings.reset_room_confirm", l))) return;
    try {
      fireSaveStatus(this, "saving");
      await this.hass.callWS({ type: "roommind/thermal/reset", area_id: areaId });
      fireSaveStatus(this, "saved");
    } catch {
      fireSaveStatus(this, "error");
    }
  }

  private async _resetAllModels() {
    const l = this.hass.language;
    if (!confirm(localize("settings.reset_all_confirm", l))) return;
    try {
      fireSaveStatus(this, "saving");
      await this.hass.callWS({ type: "roommind/thermal/reset_all" });
      fireSaveStatus(this, "saved");
    } catch {
      fireSaveStatus(this, "error");
    }
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        margin: 0;
      }

      .reset-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
      }
      .reset-text {
        display: flex;
        flex-direction: column;
        gap: 4px;
        flex: 1;
      }

      .reset-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 14px;
        border: 1px solid var(--error-color, #d32f2f);
        border-radius: 8px;
        background: transparent;
        color: var(--error-color, #d32f2f);
        font-size: 13px;
        font-family: inherit;
        cursor: pointer;
        transition: background 0.15s;
        --mdc-icon-size: 16px;
        white-space: nowrap;
      }
      .reset-btn:hover {
        background: rgba(211, 47, 47, 0.08);
      }
      .reset-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
      .reset-btn:disabled:hover {
        background: transparent;
      }

      .reset-room-row {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .reset-room-row ha-select {
        flex: 1;
      }

      @media (max-width: 600px) {
        .reset-row {
          flex-direction: column;
          align-items: flex-start;
          gap: 12px;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-reset": RsSettingsReset;
  }
}

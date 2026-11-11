/**
 * rs-settings-reset – Reset thermal data.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { errorText } from "../../utils/errors";
import { alertStyles } from "../../styles/tokens";
import "../shared/rs-icon-button";
import "../shared/rs-confirm-button";
import { fireSaveStatus, getSelectValue } from "../../utils/events";

@customElement("rs-settings-reset")
export class RsSettingsReset extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _resetSelectedRoom = "";
  @state() private _error = "";

  render() {
    const l = this.hass.language;
    const configuredRooms = Object.entries(this.rooms)
      .map(([areaId]) => ({
        areaId,
        name: this.hass.areas?.[areaId]?.name ?? areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    return html`
      ${this._error ? html`<p class="rs-alert" role="alert">${this._error}</p>` : nothing}
      <div class="settings-section first">
        <div class="reset-row">
          <div class="reset-text">
            <span class="label">${localize("settings.reset_all_label", l)}</span>
            <span class="note">${localize("settings.reset_all_hint", l)}</span>
          </div>
          <rs-confirm-button
            destructive
            icon="mdi:restart-alert"
            .label=${localize("settings.reset_all_btn", l)}
            .confirmMessage=${localize("settings.reset_all_confirm", l)}
            @confirmed=${this._resetAllModels}
          ></rs-confirm-button>
        </div>
      </div>

      <div class="settings-section">
        <div class="reset-text" style="margin-bottom: 12px">
          <span class="label">${localize("settings.reset_room_label", l)}</span>
          <span class="note">${localize("settings.reset_room_hint", l)}</span>
        </div>
        ${
          configuredRooms.length > 0
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
                      (room) =>
                        html`<ha-list-item value=${room.areaId}>${room.name}</ha-list-item>`,
                    )}
                  </ha-select>
                  ${
                    this._resetSelectedRoom
                      ? html`<rs-icon-button
                          size="sm"
                          icon="mdi:close"
                          .label=${localize("common.clear_selection", l)}
                          @click=${() => {
                            this._resetSelectedRoom = "";
                          }}
                        ></rs-icon-button>`
                      : nothing
                  }
                  <rs-confirm-button
                    destructive
                    icon="mdi:restart"
                    .label=${localize("settings.reset_btn", l)}
                    .confirmMessage=${localize("settings.reset_room_confirm", l)}
                    .disabled=${!this._resetSelectedRoom}
                    @confirmed=${() =>
                      this._resetSelectedRoom && this._resetRoomModel(this._resetSelectedRoom)}
                  ></rs-confirm-button>
                </div>
              `
            : html`<p class="hint">${localize("settings.reset_no_rooms", l)}</p>`
        }
      </div>
    `;
  }

  private async _resetRoomModel(areaId: string) {
    this._error = "";
    try {
      fireSaveStatus(this, "saving");
      await this.hass.callWS({ type: "roommind/thermal/reset", area_id: areaId });
      fireSaveStatus(this, "saved");
    } catch (err) {
      const l = this.hass.language;
      this._error = errorText(err, localize("error.unknown", l), l);
      fireSaveStatus(this, "error");
    }
  }

  private _resetAllModels = async () => {
    this._error = "";
    try {
      fireSaveStatus(this, "saving");
      await this.hass.callWS({ type: "roommind/thermal/reset_all" });
      fireSaveStatus(this, "saved");
    } catch (err) {
      const l = this.hass.language;
      this._error = errorText(err, localize("error.unknown", l), l);
      fireSaveStatus(this, "error");
    }
  };

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    alertStyles,
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
        min-width: 0;
      }
      .label {
        font-size: var(--rs-font-md);
        font-weight: 500;
      }

      .reset-room-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 12px;
      }
      .reset-room-row ha-select {
        flex: 1 1 200px;
        min-width: 0;
      }

      @container (max-width: 520px) {
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

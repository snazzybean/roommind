/**
 * rs-settings-orphans – Rooms whose Home Assistant area was deleted (#494).
 */
import { html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { RsSettingsBase } from "./rs-settings-base";
import type { HomeAssistant, RoomWithoutArea } from "../../types";
import { localize } from "../../utils/localize";
import { fireSaveStatus } from "../../utils/events";
import "../shared/rs-confirm-button";

@customElement("rs-settings-orphans")
export class RsSettingsOrphans extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: RoomWithoutArea[] = [];
  @state() private _deleting: ReadonlySet<string> = new Set();

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .orphan-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        min-height: 48px;
      }
      .orphan-text {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .orphan-name {
        overflow-wrap: anywhere;
        font-weight: 500;
      }
      .orphan-id {
        overflow-wrap: anywhere;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      rs-confirm-button {
        flex-shrink: 0;
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    return html`
      ${this.rooms.map(
        (room, idx) => html`
          <div class="settings-section ${idx === 0 ? "first" : ""}">
            <div class="orphan-row">
              <div class="orphan-text">
                <span class="orphan-name">${room.display_name || room.area_id}</span>
                ${room.display_name ? html`<span class="orphan-id">${room.area_id}</span>` : ""}
              </div>
              <rs-confirm-button
                .label=${localize(
                  this._deleting.has(room.area_id)
                    ? "settings.orphans_deleting"
                    : "settings.orphans_delete",
                  l,
                )}
                .accessibleLabel=${`${localize("settings.orphans_delete", l)}: ${room.display_name || room.area_id}`}
                .confirmMessage=${localize("settings.orphans_delete_confirm", l).replace(
                  "{name}",
                  room.display_name || room.area_id,
                )}
                .disabled=${this._deleting.has(room.area_id)}
                destructive
                @confirmed=${() => this._delete(room.area_id)}
              ></rs-confirm-button>
            </div>
          </div>
        `,
      )}
      <div class="settings-section">
        <p class="note">${localize("settings.orphans_restore_hint", l)}</p>
      </div>
    `;
  }

  private async _delete(areaId: string) {
    if (this._deleting.has(areaId)) return;
    this._deleting = new Set([...this._deleting, areaId]);
    fireSaveStatus(this, "saving");
    try {
      await this.hass.callWS({ type: "roommind/rooms/delete", area_id: areaId });
      this._deleted(areaId);
    } catch (err) {
      if ((err as { code?: string })?.code === "not_found") {
        // Already gone, e.g. deleted from another browser
        this._deleted(areaId);
        return;
      }
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] delete room without area:", err);
      fireSaveStatus(this, "error");
    } finally {
      const rest = new Set(this._deleting);
      rest.delete(areaId);
      this._deleting = rest;
    }
  }

  private _deleted(areaId: string) {
    fireSaveStatus(this, "saved");
    this.dispatchEvent(
      new CustomEvent("orphan-deleted", { detail: areaId, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-orphans": RsSettingsOrphans;
  }
}

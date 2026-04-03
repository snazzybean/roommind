/**
 * rs-settings-learning – Model training + boost learning (combined).
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { fireSaveStatus, getSelectValue } from "../../utils/events";

const BOOST_COOLDOWN = 250;

@customElement("rs-settings-learning")
export class RsSettingsLearning extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: Array }) public learningDisabledRooms: string[] = [];
  @property({ attribute: false }) public boostAppliedAt: Record<string, number> = {};
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- HA live state is untyped
  @property({ attribute: false }) public roomsLive: Record<string, any> = {};

  @state() private _showLearningExceptions = false;
  @state() private _boostSelectedRoom = "";

  render() {
    const l = this.hass.language;
    const configuredRooms = Object.entries(this.rooms)
      .map(([areaId]) => ({
        areaId,
        name: this.hass.areas?.[areaId]?.name ?? areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    const allRoomIds = Object.keys(this.rooms);
    const learningActive =
      allRoomIds.length === 0 || this.learningDisabledRooms.length < allRoomIds.length;
    const disabledCount = this.learningDisabledRooms.filter((id) => allRoomIds.includes(id)).length;

    return html`
      <!-- Learning toggle -->
      <div class="settings-section first">
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-label">${localize("settings.learning_title", l)}</span>
            <span class="toggle-hint">${localize("settings.learning_hint", l)}</span>
          </div>
          <ha-switch
            .checked=${learningActive}
            @change=${(e: Event) => {
              const active = (e.target as HTMLInputElement).checked;
              this._fire("learningDisabledRooms", active ? [] : Object.keys(this.rooms));
              if (!active) this._showLearningExceptions = false;
            }}
          ></ha-switch>
        </div>
        ${learningActive && configuredRooms.length > 0
          ? html`
              <button
                class="exceptions-link"
                @click=${() => {
                  this._showLearningExceptions = !this._showLearningExceptions;
                }}
              >
                <span
                  >${disabledCount > 0
                    ? `${disabledCount} ${localize(disabledCount === 1 ? "settings.learning_room_paused" : "settings.learning_rooms_paused", l)}`
                    : localize("settings.learning_exceptions", l)}</span
                >
                <ha-icon
                  icon=${this._showLearningExceptions ? "mdi:chevron-up" : "mdi:chevron-down"}
                  style="--mdc-icon-size: 16px"
                ></ha-icon>
              </button>
              ${this._showLearningExceptions
                ? html`
                    <div class="room-toggles">
                      ${configuredRooms.map(
                        (room) => html`
                          <div class="room-toggle-row">
                            <span class="room-toggle-name">${room.name}</span>
                            <ha-switch
                              .checked=${!this.learningDisabledRooms.includes(room.areaId)}
                              @change=${(e: Event) => {
                                const disabled = !(e.target as HTMLInputElement).checked;
                                const set = new Set(this.learningDisabledRooms);
                                if (disabled) set.add(room.areaId);
                                else set.delete(room.areaId);
                                this._fire("learningDisabledRooms", [...set]);
                              }}
                            ></ha-switch>
                          </div>
                        `,
                      )}
                    </div>
                  `
                : nothing}
            `
          : nothing}
      </div>

      <!-- Boost learning -->
      <div class="settings-section">
        <span class="toggle-label">${localize("settings.boost_title", l)}</span>
        <p class="hint">${localize("settings.boost_hint", l)}</p>

        ${configuredRooms.length > 0
          ? html`
              <div class="room-select-row">
                <ha-select
                  .value=${this._boostSelectedRoom}
                  .label=${localize("settings.boost_room_select", l)}
                  .options=${configuredRooms.map((room) => ({
                    value: room.areaId,
                    label: room.name,
                  }))}
                  fixedMenuPosition
                  @selected=${(e: Event) => {
                    this._boostSelectedRoom = getSelectValue(e);
                  }}
                  @closed=${(e: Event) => e.stopPropagation()}
                >
                  ${configuredRooms.map(
                    (room) => html`<ha-list-item value=${room.areaId}>${room.name}</ha-list-item>`,
                  )}
                </ha-select>
                ${this._boostSelectedRoom
                  ? html`<ha-icon-button
                      .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                      @click=${() => {
                        this._boostSelectedRoom = "";
                      }}
                    ></ha-icon-button>`
                  : nothing}
                ${this._boostSelectedRoom && this._isCooldown(this._boostSelectedRoom)
                  ? html`<span class="boost-status">
                      <ha-icon icon="mdi:check-circle-outline"></ha-icon>
                      ${localize("settings.boost_cooldown", l)}
                    </span>`
                  : html`<button
                      class="boost-btn"
                      ?disabled=${!this._boostSelectedRoom ||
                      this._isCooldown(this._boostSelectedRoom)}
                      @click=${() =>
                        this._boostSelectedRoom && this._boostLearning(this._boostSelectedRoom)}
                    >
                      <ha-icon icon="mdi:lightning-bolt"></ha-icon>
                      ${localize("settings.boost_btn", l)}
                    </button>`}
              </div>
            `
          : html`<p class="hint">${localize("settings.boost_no_rooms", l)}</p>`}
      </div>
    `;
  }

  private _isCooldown(areaId: string): boolean {
    const nObs = this.roomsLive?.[areaId]?.n_observations ?? 0;
    const appliedAt = this.boostAppliedAt[areaId];
    return appliedAt !== undefined && nObs - appliedAt < BOOST_COOLDOWN;
  }

  private async _boostLearning(areaId: string) {
    try {
      fireSaveStatus(this, "saving");
      const result = await this.hass.callWS<{ n_observations: number }>({
        type: "roommind/model/boost_learning",
        area_id: areaId,
      });
      fireSaveStatus(this, "saved");
      this.dispatchEvent(
        new CustomEvent("boost-applied", {
          detail: { area_id: areaId, n_observations: result.n_observations },
          bubbles: true,
          composed: true,
        }),
      );
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
        margin: 4px 0 12px;
        line-height: 1.4;
      }

      .exceptions-link {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: none;
        border: none;
        padding: 8px 0 0;
        margin: 0;
        cursor: pointer;
        font-size: 13px;
        color: var(--primary-color);
        font-family: inherit;
      }
      .exceptions-link:hover {
        text-decoration: underline;
      }

      .room-toggles {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin-top: 12px;
      }
      .room-toggle-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 4px 0;
      }
      .room-toggle-name {
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .room-select-row {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .room-select-row ha-select {
        flex: 1;
      }

      .boost-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 14px;
        border: 1px solid var(--primary-color);
        border-radius: 8px;
        background: transparent;
        color: var(--primary-color);
        font-size: 13px;
        font-family: inherit;
        cursor: pointer;
        transition: background 0.15s;
        --mdc-icon-size: 16px;
        white-space: nowrap;
      }
      .boost-btn:hover {
        background: rgba(var(--rgb-primary-color), 0.08);
      }
      .boost-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
      .boost-btn:disabled:hover {
        background: transparent;
      }

      .boost-status {
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--success-color, #4caf50);
        font-size: 13px;
        --mdc-icon-size: 16px;
        white-space: nowrap;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-learning": RsSettingsLearning;
  }
}

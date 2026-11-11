/**
 * rs-settings-learning – Model training on/off (all rooms and per room), the model state of
 * every room and "learn faster" per room.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { fireSaveStatus } from "../../utils/events";
import { formatMinutes, formatPercent } from "../../utils/format";
import { boostHoursLeft, learningState, type LearningState } from "../../utils/learning";
import "../shared/rs-icon-button";

const STATE_KEYS: Record<LearningState, TranslationKey> = {
  not_learning: "settings.learning_state.not_learning",
  paused: "settings.learning_state.paused",
  waiting: "settings.learning_state.waiting",
  no_data: "settings.learning_state.no_data",
  learning: "settings.learning_state.learning",
  ready: "settings.learning_state.ready",
};

@customElement("rs-settings-learning")
export class RsSettingsLearning extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: Array }) public learningDisabledRooms: string[] = [];
  /** Anchors of boosts started on this page, until the polled room data carries them. */
  @state() private _boosted: Record<string, number> = {};

  render() {
    const l = this.hass.language;
    const rooms = Object.entries(this.rooms)
      .map(([areaId, config]) => ({
        areaId,
        config,
        name: config.display_name || this.hass.areas?.[areaId]?.name || areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    const allRoomIds = Object.keys(this.rooms);
    const learningActive =
      allRoomIds.length === 0 || this.learningDisabledRooms.length < allRoomIds.length;
    const disabledCount = this.learningDisabledRooms.filter((id) => allRoomIds.includes(id)).length;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.learning_title", l)}
          .secondary=${localize("settings.learning_hint", l)}
          .checked=${learningActive}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("learningDisabledRooms", e.detail ? [] : allRoomIds)}
        ></rs-list-row>
      </div>

      <div class="settings-section">
        <h3 class="section-title">
          ${localize("settings.learning_rooms", l)}${
            disabledCount > 0
              ? ` · ${disabledCount} ${localize(disabledCount === 1 ? "settings.learning_room_paused" : "settings.learning_rooms_paused", l)}`
              : nothing
          }
        </h3>
        ${
          rooms.length
            ? rooms.map((room) => this._renderRoom(room.areaId, room.name, room.config))
            : html`<p class="note">${localize("settings.summary.learning_no_rooms", l)}</p>`
        }
      </div>

      <div class="settings-section">
        <span class="field-label">${localize("settings.boost_title", l)}</span>
        <p class="note">
          ${localize("settings.boost_hint", l)}
          <a href="/roommind/settings/reset">${localize("settings.reset_title", l)}</a>
        </p>
      </div>
    `;
  }

  private _renderRoom(areaId: string, name: string, config: RoomConfig) {
    const l = this.hass.language;
    const paused = this.learningDisabledRooms.includes(areaId);
    const state = learningState(config, paused);
    const confidence = formatPercent(Math.round((config.live?.confidence ?? 0) * 100), this.hass);
    const outdoor = state === "not_learning" && config.is_outdoor;
    const stateText = localize(outdoor ? "settings.learning_state.outdoor" : STATE_KEYS[state], l, {
      confidence,
    });
    const hours = paused
      ? null
      : boostHoursLeft(
          config.live?.boost_applied_at ?? this._boosted[areaId],
          config.live?.n_observations,
        );
    const boostLine =
      hours != null
        ? html`<span slot="secondary" class="boost"
            >${localize("learning.boost_active", l, { time: formatMinutes(hours * 60, l) })}</span
          >`
        : nothing;

    if (state === "not_learning") {
      return html`<rs-list-row .heading=${name} .secondary=${stateText}></rs-list-row>`;
    }
    const canBoost = (state === "learning" || state === "ready") && hours == null;
    return html`<rs-list-row
      switch
      .heading=${name}
      .secondary=${stateText}
      .checked=${!paused}
      @toggle-changed=${(e: CustomEvent<boolean>) => {
        const set = new Set(this.learningDisabledRooms);
        if (e.detail) set.delete(areaId);
        else set.add(areaId);
        this._fire("learningDisabledRooms", [...set]);
      }}
    >
      ${boostLine}
      <rs-icon-button
        slot="end"
        size="sm"
        icon="mdi:school-outline"
        .label=${localize("settings.boost_room", l, { room: name })}
        .disabled=${!canBoost}
        @click=${() => {
          if (canBoost) this._boostLearning(areaId, name);
        }}
      ></rs-icon-button>
    </rs-list-row>`;
  }

  private async _boostLearning(areaId: string, name: string) {
    if (!confirm(localize("settings.boost_confirm", this.hass.language, { room: name }))) return;
    try {
      fireSaveStatus(this, "saving");
      const result = await this.hass.callWS<{ n_observations: number }>({
        type: "roommind/model/boost_learning",
        area_id: areaId,
      });
      fireSaveStatus(this, "saved");
      this._boosted = { ...this._boosted, [areaId]: result.n_observations };
    } catch {
      fireSaveStatus(this, "error");
    }
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .boost {
        display: block;
        color: var(--primary-color);
      }

      .note a {
        color: var(--primary-color);
      }

      .note a:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
        border-radius: 2px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-learning": RsSettingsLearning;
  }
}

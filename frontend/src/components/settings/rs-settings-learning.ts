/**
 * rs-settings-learning – Model training on/off (all rooms and per room), the model state of
 * every room and "learn faster" per room.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { formatMinutes, formatPercent } from "../../utils/format";
import { errorText } from "../../utils/errors";
import { showToast } from "../../utils/toast";
import {
  boostHoursLeft,
  learningRoomIds,
  learningState,
  type LearningState,
} from "../../utils/learning";
import "../shared/rs-icon-button";
import "../shared/rs-confirm-dialog";

const STATE_KEYS: Record<LearningState, TranslationKey> = {
  outdoor: "settings.learning_state.outdoor",
  paused: "settings.learning_state.paused",
  waiting: "settings.learning_state.waiting",
  no_data: "settings.learning_state.no_data",
  learning: "settings.learning_state.learning",
  ready: "settings.learning_state.ready",
  managed: "settings.learning_state.managed",
  simple: "settings.learning_state.simple",
};

@customElement("rs-settings-learning")
export class RsSettingsLearning extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: Array }) public learningDisabledRooms: string[] = [];
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  /** Anchors of boosts started on this page, until the polled room data carries them. */
  @state() private _boosted: Record<string, number> = {};
  /** Room the "learn faster" confirmation is open for. */
  @state() private _boostTarget: { areaId: string; name: string } | null = null;
  @state() private _boostBusy = false;
  @state() private _boostError = "";

  render() {
    const l = this.hass.language;
    const rooms = Object.entries(this.rooms)
      .map(([areaId, config]) => ({
        areaId,
        config,
        name: config.display_name || this.hass.areas?.[areaId]?.name || areaId,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    const learnIds = learningRoomIds(this.rooms);
    const disabledCount = this.learningDisabledRooms.filter((id) => learnIds.includes(id)).length;
    const learningActive = learnIds.length === 0 || disabledCount < learnIds.length;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.learning_switch", l)}
          .secondary=${localize("settings.learning_hint", l)}
          .checked=${learningActive}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("learningDisabledRooms", e.detail ? [] : learnIds)}
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

      <rs-confirm-dialog
        .open=${this._boostTarget !== null}
        icon="mdi:school-outline"
        .heading=${
          this._boostTarget
            ? localize("settings.boost_room", l, { room: this._boostTarget.name })
            : ""
        }
        .message=${localize("settings.boost_confirm", l)}
        .confirmLabel=${localize("settings.boost_title", l)}
        .destructive=${false}
        .busy=${this._boostBusy}
        .error=${this._boostError}
        @cancel=${() => {
          this._boostTarget = null;
          this._boostError = "";
        }}
        @confirm=${this._boostLearning}
      ></rs-confirm-dialog>
    `;
  }

  private _renderRoom(areaId: string, name: string, config: RoomConfig) {
    const l = this.hass.language;
    const paused = this.learningDisabledRooms.includes(areaId);
    const state = learningState(config, paused, this.controlMode);
    const confidence = formatPercent(Math.round((config.live?.confidence ?? 0) * 100), this.hass);
    const stateText = localize(STATE_KEYS[state], l, { confidence });
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

    if (state === "outdoor") {
      return html`<rs-list-row .heading=${name} .secondary=${stateText}></rs-list-row>`;
    }
    const canBoost =
      (state === "learning" || state === "ready" || state === "managed" || state === "simple") &&
      hours == null;
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
          if (!canBoost) return;
          this._boostError = "";
          this._boostTarget = { areaId, name };
        }}
      ></rs-icon-button>
    </rs-list-row>`;
  }

  private _boostLearning = async () => {
    const target = this._boostTarget;
    if (!target) return;
    const l = this.hass.language;
    this._boostBusy = true;
    this._boostError = "";
    try {
      const result = await this.hass.callWS<{ n_observations: number }>({
        type: "roommind/model/boost_learning",
        area_id: target.areaId,
      });
      this._boosted = { ...this._boosted, [target.areaId]: result.n_observations };
      this._boostTarget = null;
      showToast(this, localize("settings.boost_done", l, { room: target.name }), l);
    } catch (err) {
      this._boostError = errorText(err, localize("error.unknown", l), l);
    } finally {
      this._boostBusy = false;
    }
  };

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

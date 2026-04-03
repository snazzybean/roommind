/**
 * rs-settings-presence – Presence detection settings.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";

@customElement("rs-settings-presence")
export class RsSettingsPresence extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ type: Array }) public presencePersons: string[] = [];
  @property({ type: String }) public presenceAwayAction: "eco" | "off" = "eco";

  render() {
    const l = this.hass.language;

    return html`
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${localize("presence.title", l)}</span>
          <span class="toggle-hint">${localize("presence.hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.presenceEnabled}
          @change=${(e: Event) =>
            this._fire("presenceEnabled", (e.target as HTMLInputElement).checked)}
        ></ha-switch>
      </div>

      ${this.presenceEnabled
        ? html`
            <div class="detail-section">
              <span class="field-hint">${localize("presence.hint_detail", l)}</span>
              ${this.presencePersons.length > 0
                ? html`
                    <div class="person-list">
                      ${this.presencePersons.map((pid) => {
                        const name =
                          this.hass.states[pid]?.attributes?.friendly_name ??
                          pid.split(".").slice(1).join(".");
                        return html`
                          <div class="person-row">
                            <ha-icon
                              icon="mdi:account"
                              style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"
                            ></ha-icon>
                            <span class="person-name">${name}</span>
                            <ha-icon-button
                              .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                              @click=${() =>
                                this._fire(
                                  "presencePersons",
                                  this.presencePersons.filter((p) => p !== pid),
                                )}
                            ></ha-icon-button>
                          </div>
                        `;
                      })}
                    </div>
                  `
                : nothing}
              <ha-entity-picker
                .hass=${this.hass}
                .includeDomains=${["person", "device_tracker", "binary_sensor", "input_boolean"]}
                .entityFilter=${(entity: { entity_id: string }) =>
                  !this.presencePersons.includes(entity.entity_id)}
                .label=${localize("presence.add_entity", l)}
                @value-changed=${(e: CustomEvent) => {
                  const val = e.detail?.value;
                  if (val && !this.presencePersons.includes(val)) {
                    this._fire("presencePersons", [...this.presencePersons, val]);
                  }
                  const picker = e.target as HTMLElement & { value: string };
                  picker.value = "";
                }}
              ></ha-entity-picker>
              <ha-select
                .label=${localize("presence.away_action_label", l)}
                .value=${this.presenceAwayAction}
                .options=${[
                  { value: "eco", label: localize("presence.away_action_eco", l) },
                  { value: "off", label: localize("presence.away_action_off", l) },
                ]}
                fixedMenuPosition
                @selected=${(e: Event) => {
                  const val = getSelectValue(e) as "eco" | "off";
                  if (val && val !== this.presenceAwayAction) this._fire("presenceAwayAction", val);
                }}
                @closed=${(e: Event) => e.stopPropagation()}
                style="margin-top: 8px"
              >
                <ha-list-item value="eco">${localize("presence.away_action_eco", l)}</ha-list-item>
                <ha-list-item value="off">${localize("presence.away_action_off", l)}</ha-list-item>
              </ha-select>
            </div>
          `
        : nothing}
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .detail-section {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 12px;
      }

      .person-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .person-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 4px 8px 4px 12px;
        border-radius: 8px;
        background: rgba(0, 0, 0, 0.04);
      }
      .person-name {
        flex: 1;
        font-size: 14px;
        font-weight: 500;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-presence": RsSettingsPresence;
  }
}

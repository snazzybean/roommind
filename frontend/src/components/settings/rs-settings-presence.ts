/**
 * rs-settings-presence – Presence detection settings.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-segmented";
import "../shared/rs-icon-button";

@customElement("rs-settings-presence")
export class RsSettingsPresence extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ type: Array }) public presencePersons: string[] = [];
  @property({ type: String }) public presenceAwayAction: "eco" | "off" = "eco";
  @property({ type: Boolean }) public presenceClearsOverride = false;

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("presence.switch", l)}
          .checked=${this.presenceEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("presenceEnabled", e.detail)}
        ></rs-list-row>
      </div>

      ${
        this.presenceEnabled
          ? html`
              <div class="settings-section stack">
                <p class="note">${localize("presence.hint_detail", l)}</p>
                ${
                  this.presencePersons.length > 0
                    ? html`
                        <div class="person-list">
                          ${this.presencePersons.map((pid) => {
                            const name =
                              this.hass.states[pid]?.attributes?.friendly_name ??
                              pid.split(".").slice(1).join(".");
                            return html`
                              <div class="person-row">
                                <ha-icon icon="mdi:account" aria-hidden="true"></ha-icon>
                                <span class="person-name">${name}</span>
                                <rs-icon-button
                                  size="sm"
                                  icon="mdi:close"
                                  .label=${localize("common.remove_named", l, { name: String(name) })}
                                  @click=${() =>
                                    this._fire(
                                      "presencePersons",
                                      this.presencePersons.filter((p) => p !== pid),
                                    )}
                                ></rs-icon-button>
                              </div>
                            `;
                          })}
                        </div>
                      `
                    : nothing
                }
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
              </div>
              <div class="settings-section">
                <span class="field-label">${localize("presence.away_action_label", l)}</span>
                <rs-segmented
                  wrap
                  .label=${localize("presence.away_action_label", l)}
                  .options=${[
                    {
                      value: "eco",
                      label: localize("presence.away_action_eco", l),
                      icon: "mdi:leaf",
                    },
                    {
                      value: "off",
                      label: localize("presence.away_action_off", l),
                      icon: "mdi:power",
                    },
                  ]}
                  .value=${this.presenceAwayAction}
                  @value-changed=${(e: CustomEvent<{ value: string }>) => {
                    const val = e.detail.value as "eco" | "off";
                    if (val && val !== this.presenceAwayAction)
                      this._fire("presenceAwayAction", val);
                  }}
                ></rs-segmented>
              </div>
              <div class="settings-section">
                <rs-list-row
                  switch
                  wrap
                  .heading=${localize("presence.clears_override_label", l)}
                  .secondary=${localize("presence.clears_override_hint", l)}
                  .checked=${this.presenceClearsOverride}
                  @toggle-changed=${(e: CustomEvent<boolean>) =>
                    this._fire("presenceClearsOverride", e.detail)}
                ></rs-list-row>
              </div>
            `
          : nothing
      }
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .person-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .person-row {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
        padding: 2px 4px 2px 12px;
        border-radius: var(--rs-radius-sm);
        background: var(--rs-fill);
        --mdc-icon-size: 18px;
      }
      .person-row ha-icon {
        color: var(--secondary-text-color);
      }
      .person-name {
        flex: 1;
        min-width: 0;
        font-size: var(--rs-font-md);
        font-weight: 500;
        overflow-wrap: anywhere;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-presence": RsSettingsPresence;
  }
}

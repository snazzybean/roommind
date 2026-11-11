/**
 * rs-settings-notifications – Feature-agnostic notification settings.
 * Fires setting-changed events with mold-prefixed keys for backend compatibility.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, NotificationTarget } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-icon-button";
import { getSelectValue } from "../../utils/events";

@customElement("rs-settings-notifications")
export class RsSettingsNotifications extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public notificationsEnabled = true;
  @property({ type: Array }) public notificationTargets: NotificationTarget[] = [];
  @property({ type: Number }) public notificationCooldown = 60;
  @property({ type: Boolean }) public moldPreventionEnabled = false;
  @property({ type: Boolean }) public moldPreventionNotify = false;

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("notifications.enabled", l)}
          .secondary=${localize("notifications.enabled_hint", l)}
          .checked=${this.notificationsEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("moldNotificationsEnabled", e.detail)}
        ></rs-list-row>
      </div>

      ${
        this.notificationsEnabled
          ? html`
              <div class="settings-section">
                <p class="hint">${localize("notifications.desc", l)}</p>

                <div class="target-list">
                  ${this.notificationTargets.map((t, idx) => {
                    const name = t.entity_id
                      ? (this.hass.states[t.entity_id]?.attributes?.friendly_name ??
                        t.entity_id.replace("notify.", ""))
                      : localize("notifications.target_unnamed", l);
                    return html`
                      <div class="target-card">
                        <div class="target-header">
                          <ha-icon icon="mdi:bell" aria-hidden="true"></ha-icon>
                          <span>${name}</span>
                          <rs-icon-button
                            size="sm"
                            icon="mdi:close"
                            .label=${localize("common.remove_named", l, { name: String(name) })}
                            @click=${() => {
                              this._fire(
                                "moldNotificationTargets",
                                this.notificationTargets.filter((_, i) => i !== idx),
                              );
                            }}
                          ></rs-icon-button>
                        </div>
                        <div class="target-detail">
                          <ha-entity-picker
                            .hass=${this.hass}
                            .value=${t.person_entity}
                            .includeDomains=${["person"]}
                            .label=${localize("notifications.target_person", l)}
                            allow-custom-entity
                            @value-changed=${(e: CustomEvent) => {
                              const targets = [...this.notificationTargets];
                              targets[idx] = {
                                ...targets[idx],
                                person_entity: (e.detail?.value as string) ?? "",
                              };
                              this._fire("moldNotificationTargets", targets);
                            }}
                          ></ha-entity-picker>
                          <ha-select
                            .value=${t.notify_when}
                            .options=${[
                              {
                                value: "always",
                                label: localize("notifications.target_when_always", l),
                              },
                              {
                                value: "home_only",
                                label: localize("notifications.target_when_home", l),
                              },
                            ]}
                            fixedMenuPosition
                            @selected=${(e: Event) => {
                              const v = getSelectValue(e) as "always" | "home_only";
                              if (!v) return;
                              const targets = [...this.notificationTargets];
                              targets[idx] = { ...targets[idx], notify_when: v };
                              this._fire("moldNotificationTargets", targets);
                            }}
                            @closed=${(e: Event) => e.stopPropagation()}
                          >
                            <ha-list-item value="always"
                              >${localize("notifications.target_when_always", l)}</ha-list-item
                            >
                            <ha-list-item value="home_only"
                              >${localize("notifications.target_when_home", l)}</ha-list-item
                            >
                          </ha-select>
                        </div>
                      </div>
                    `;
                  })}
                </div>

                <div class="add-target">
                  <ha-entity-picker
                    .hass=${this.hass}
                    .value=${""}
                    .includeDomains=${["notify"]}
                    .label=${localize("notifications.add_target_label", l)}
                    allow-custom-entity
                    @value-changed=${(e: CustomEvent) => {
                      const v = (e.detail?.value as string) ?? "";
                      if (!v) return;
                      this._fire("moldNotificationTargets", [
                        ...this.notificationTargets,
                        { entity_id: v, person_entity: "", notify_when: "always" as const },
                      ]);
                      const picker = e.target as HTMLElement & { value?: string };
                      if (picker) picker.value = "";
                    }}
                  ></ha-entity-picker>
                  <span class="field-hint">${localize("notifications.add_target_hint", l)}</span>
                </div>
              </div>

              <div class="settings-section">
                <div class="threshold-grid">
                  <div class="threshold-field">
                    <ha-textfield
                      .value=${String(this.notificationCooldown)}
                      .label=${localize("notifications.cooldown", l)}
                      .suffix=${"min"}
                      type="number"
                      step="5"
                      min="10"
                      max="1440"
                      @change=${(e: Event) => {
                        const v = parseInt((e.target as HTMLInputElement).value, 10);
                        if (!isNaN(v) && v >= 10 && v <= 1440)
                          this._fire("moldNotificationCooldown", v);
                      }}
                    ></ha-textfield>
                    <span class="field-hint">${localize("notifications.cooldown_hint", l)}</span>
                  </div>
                </div>

                ${
                  this.moldPreventionEnabled
                    ? html`
                        <rs-list-row
                          class="prevention-row"
                          switch
                          wrap
                          .heading=${localize("notifications.mold_prevention_notify", l)}
                          .secondary=${localize("notifications.mold_prevention_notify_hint", l)}
                          .checked=${this.moldPreventionNotify}
                          @toggle-changed=${(e: CustomEvent<boolean>) =>
                            this._fire("moldPreventionNotify", e.detail)}
                        ></rs-list-row>
                      `
                    : nothing
                }
              </div>
            `
          : nothing
      }
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        margin: 0 0 var(--rs-space-3);
        line-height: 1.5;
      }
      .prevention-row {
        margin-top: var(--rs-space-2);
      }

      .target-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .target-card {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 8px 8px 8px 12px;
        border-radius: var(--rs-radius-sm);
        background: var(--rs-fill);
      }
      .target-header {
        display: flex;
        align-items: center;
        gap: 8px;
        --mdc-icon-size: 18px;
      }
      .target-header ha-icon {
        color: var(--secondary-text-color);
      }
      .add-target {
        margin-top: var(--rs-space-2);
      }
      .target-header span {
        flex: 1;
        min-width: 0;
        overflow-wrap: anywhere;
        font-size: 14px;
        font-weight: 500;
      }
      .target-detail {
        display: flex;
        gap: 8px;
        align-items: center;
        padding-left: 26px;
      }
      .target-detail ha-entity-picker {
        flex: 1;
      }
      .target-detail ha-select {
        min-width: 120px;
      }

      @container (max-width: 520px) {
        .target-detail {
          flex-direction: column;
          padding-left: 0;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-notifications": RsSettingsNotifications;
  }
}

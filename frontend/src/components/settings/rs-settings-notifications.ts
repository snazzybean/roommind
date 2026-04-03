/**
 * rs-settings-notifications – Feature-agnostic notification settings.
 * Fires setting-changed events with mold-prefixed keys for backend compatibility.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, NotificationTarget } from "../../types";
import { localize } from "../../utils/localize";
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
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${localize("notifications.enabled", l)}</span>
          <span class="toggle-hint">${localize("notifications.enabled_hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.notificationsEnabled}
          @change=${(e: Event) =>
            this._fire("moldNotificationsEnabled", (e.target as HTMLInputElement).checked)}
        ></ha-switch>
      </div>

      ${this.notificationsEnabled
        ? html`
            <div class="detail-section">
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
                        <ha-icon
                          icon="mdi:bell"
                          style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"
                        ></ha-icon>
                        <span>${name}</span>
                        <ha-icon-button
                          .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                          @click=${() => {
                            this._fire(
                              "moldNotificationTargets",
                              this.notificationTargets.filter((_, i) => i !== idx),
                            );
                          }}
                        ></ha-icon-button>
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

              <div style="margin-top: 8px">
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

              <div class="threshold-grid" style="margin-top: 12px">
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

              ${this.moldPreventionEnabled
                ? html`
                    <div class="toggle-row" style="margin-top: 12px">
                      <div class="toggle-text">
                        <span class="toggle-label"
                          >${localize("notifications.mold_prevention_notify", l)}</span
                        >
                        <span class="toggle-hint"
                          >${localize("notifications.mold_prevention_notify_hint", l)}</span
                        >
                      </div>
                      <ha-switch
                        .checked=${this.moldPreventionNotify}
                        @change=${(e: Event) =>
                          this._fire(
                            "moldPreventionNotify",
                            (e.target as HTMLInputElement).checked,
                          )}
                      ></ha-switch>
                    </div>
                  `
                : nothing}
            </div>
          `
        : nothing}
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        margin: 12px 0;
        line-height: 1.4;
      }
      .detail-section {
        margin-top: 4px;
      }
      .field-hint {
        color: var(--secondary-text-color);
        font-size: 12px;
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
        border-radius: 8px;
        background: rgba(0, 0, 0, 0.04);
      }
      .target-header {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .target-header span {
        flex: 1;
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

      @media (max-width: 600px) {
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

/**
 * rs-settings-notifications – Feature-agnostic notification settings.
 * Fires setting-changed events with mold-prefixed keys for backend compatibility.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-number-field";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, NotificationTarget } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-icon-button";
import "../shared/rs-list-row";
import "../shared/rs-segmented";
import { notifyTargetIcon, notifyTargetName } from "../../utils/notify-target";

@customElement("rs-settings-notifications")
export class RsSettingsNotifications extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public notificationsEnabled = true;
  @property({ type: Array }) public notificationTargets: NotificationTarget[] = [];
  @property({ type: Number }) public notificationCooldown = 60;
  @property({ type: Boolean }) public moldDetectionEnabled = false;
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
        ${this.notificationsEnabled && !this.moldDetectionEnabled ? this._renderMoldOff() : nothing}
      </div>

      ${
        this.notificationsEnabled
          ? html`
              <div class="settings-section stack">
                <div>
                  <h3 class="section-title">${localize("notifications.recipients", l)}</h3>
                  <p class="note">${localize("notifications.desc", l)}</p>
                </div>
                ${
                  this.notificationTargets.length
                    ? html`<div class="target-list">
                        ${this.notificationTargets.map((t, idx) => this._renderTarget(t, idx))}
                      </div>`
                    : nothing
                }
                <div>
                  <ha-entity-picker
                    .hass=${this.hass}
                    .value=${""}
                    .includeDomains=${["notify"]}
                    .entityFilter=${(entity: { entity_id: string }) =>
                      !this.notificationTargets.some((t) => t.entity_id === entity.entity_id)}
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
                  <rs-number-field
                    .label=${localize("notifications.cooldown", l)}
                    suffix="min"
                    .hint=${localize("notifications.cooldown_hint", l)}
                    .min=${10}
                    .max=${1440}
                    .value=${this.notificationCooldown}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._fire("moldNotificationCooldown", e.detail.value)}
                  ></rs-number-field>
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

  private _renderTarget(t: NotificationTarget, idx: number) {
    const l = this.hass.language;
    const name = t.entity_id
      ? notifyTargetName(this.hass, t.entity_id)
      : localize("notifications.target_unnamed", l);
    const homeOnly = t.notify_when === "home_only";
    const update = (changes: Partial<NotificationTarget>) => {
      const targets = [...this.notificationTargets];
      targets[idx] = { ...targets[idx], ...changes };
      this._fire("moldNotificationTargets", targets);
    };
    return html`<div class="target">
      <div class="target-head">
        <ha-icon .icon=${notifyTargetIcon(t.entity_id)} aria-hidden="true"></ha-icon>
        <div class="target-name">
          <span>${name}</span>
          ${
            t.entity_id && name !== t.entity_id.replace(/^notify\./, "")
              ? html`<small>${t.entity_id}</small>`
              : nothing
          }
        </div>
        <rs-icon-button
          size="sm"
          icon="mdi:close"
          .label=${localize("common.remove_named", l, { name })}
          @click=${() =>
            this._fire(
              "moldNotificationTargets",
              this.notificationTargets.filter((_, i) => i !== idx),
            )}
        ></rs-icon-button>
      </div>
      <rs-segmented
        wrap
        size="sm"
        .label=${localize("notifications.target_when_label", l, { name })}
        .options=${[
          { value: "always", label: localize("notifications.target_when_always", l) },
          { value: "home_only", label: localize("notifications.target_when_home", l) },
        ]}
        .value=${homeOnly ? "home_only" : "always"}
        @value-changed=${(e: CustomEvent<{ value: string }>) => {
          const v = e.detail.value as NotificationTarget["notify_when"];
          if (v && v !== t.notify_when) update({ notify_when: v });
        }}
      ></rs-segmented>
      ${
        homeOnly
          ? html`<div>
              <ha-entity-picker
                .hass=${this.hass}
                .value=${t.person_entity}
                .includeDomains=${["person"]}
                .label=${localize("notifications.target_person", l)}
                @value-changed=${(e: CustomEvent) =>
                  update({ person_entity: (e.detail?.value as string) ?? "" })}
              ></ha-entity-picker>
              ${
                t.person_entity
                  ? nothing
                  : html`<span class="field-hint"
                      >${localize("notifications.target_person_missing", l)}</span
                    >`
              }
            </div>`
          : nothing
      }
    </div>`;
  }

  /** Only mold detection and the prevention notice send anything from this page. */
  private _renderMoldOff() {
    const l = this.hass.language;
    return html`<div class="mold-off">
      <p class="hint">
        ${localize(
          this.moldPreventionEnabled && this.moldPreventionNotify
            ? "notifications.mold_off_prevention"
            : "notifications.mold_off",
          l,
        )}
      </p>
      <rs-list-row
        href="/roommind/settings/mold"
        chevron
        icon="mdi:water-alert"
        .heading=${localize("mold.title", l)}
        @click=${this._onMoldClick}
      ></rs-list-row>
    </div>`;
  }

  private _onMoldClick(e: MouseEvent) {
    // Ctrl/Cmd/Shift/middle click keep the browser's "open in new tab".
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    this.dispatchEvent(
      new CustomEvent("settings-category-changed", {
        detail: { category: "mold" },
        bubbles: true,
        composed: true,
      }),
    );
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
      .mold-off {
        margin-top: var(--rs-space-3);
      }
      .mold-off .hint {
        margin-bottom: var(--rs-space-1);
      }
      .prevention-row {
        margin-top: var(--rs-space-2);
      }

      .target-list {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-2);
      }
      .target {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-3);
        padding: var(--rs-space-2) var(--rs-space-2) var(--rs-space-3) var(--rs-space-3);
        border-radius: var(--rs-radius);
        background: var(--rs-fill);
      }
      .target-head {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
        --mdc-icon-size: 20px;
      }
      .target-head ha-icon {
        color: var(--secondary-text-color);
        flex: none;
      }
      .target-name {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
      }
      .target-name span {
        font-size: var(--rs-font-md);
        font-weight: 500;
        overflow-wrap: anywhere;
      }
      .target-name small {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        overflow-wrap: anywhere;
      }
      .target > rs-segmented,
      .target > div:last-child:not(.target-head) {
        margin-right: var(--rs-space-1);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-notifications": RsSettingsNotifications;
  }
}

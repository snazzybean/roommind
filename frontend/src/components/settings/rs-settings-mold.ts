/**
 * rs-settings-mold – Mold risk detection & prevention card.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, NotificationTarget } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";

@customElement("rs-settings-mold")
export class RsSettingsMold extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public moldDetectionEnabled = false;
  @property({ type: Number }) public moldHumidityThreshold = 70;
  @property({ type: Number }) public moldSustainedMinutes = 30;
  @property({ type: Number }) public moldNotificationCooldown = 60;
  @property({ type: Boolean }) public moldNotificationsEnabled = true;
  @property({ type: Array }) public moldNotificationTargets: NotificationTarget[] = [];
  @property({ type: Boolean }) public moldPreventionEnabled = false;
  @property({ type: String }) public moldPreventionIntensity: "light" | "medium" | "strong" = "medium";
  @property({ type: Boolean }) public moldPreventionNotify = false;

  private _fire(key: string, value: unknown) {
    this.dispatchEvent(new CustomEvent("setting-changed", {
      detail: { key, value },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    const l = this.hass.language;

    return html`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:water-alert"></ha-icon>
            <span>${localize("mold.title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <!-- Detection section -->
          <div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:bell-alert" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("mold.detection", l)}
                </span>
                <span class="toggle-hint">${localize("mold.detection_desc", l)}</span>
              </div>
              <ha-switch
                .checked=${this.moldDetectionEnabled}
                @change=${(e: Event) => this._fire("moldDetectionEnabled", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
            ${this.moldDetectionEnabled
              ? html`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldHumidityThreshold)}
                        .label=${localize("mold.threshold", l)}
                        .suffix=${"%"}
                        type="number" step="1" min="50" max="90"
                        @change=${(e: Event) => {
                          const v = parseFloat((e.target as HTMLInputElement).value);
                          if (!isNaN(v) && v >= 50 && v <= 90) this._fire("moldHumidityThreshold", v);
                        }}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.threshold_hint", l)}</span>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldSustainedMinutes)}
                        .label=${localize("mold.sustained", l)}
                        .suffix=${"min"}
                        type="number" step="5" min="5" max="120"
                        @change=${(e: Event) => {
                          const v = parseInt((e.target as HTMLInputElement).value, 10);
                          if (!isNaN(v) && v >= 5 && v <= 120) this._fire("moldSustainedMinutes", v);
                        }}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.sustained_hint", l)}</span>
                    </div>
                  </div>
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldNotificationCooldown)}
                        .label=${localize("mold.cooldown", l)}
                        .suffix=${"min"}
                        type="number" step="5" min="10" max="1440"
                        @change=${(e: Event) => {
                          const v = parseInt((e.target as HTMLInputElement).value, 10);
                          if (!isNaN(v) && v >= 10 && v <= 1440) this._fire("moldNotificationCooldown", v);
                        }}
                      ></ha-textfield>
                      <span class="field-hint">${localize("mold.cooldown_hint", l)}</span>
                    </div>
                  </div>
                `
              : nothing}
          </div>

          <!-- Prevention section -->
          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-check" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${localize("mold.prevention", l)}
                </span>
                <span class="toggle-hint">${localize("mold.prevention_desc", l)}</span>
              </div>
              <ha-switch
                .checked=${this.moldPreventionEnabled}
                @change=${(e: Event) => this._fire("moldPreventionEnabled", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
            ${this.moldPreventionEnabled
              ? html`
                  <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 4px;">
                    <ha-select
                      style="width: 100%;"
                      .value=${this.moldPreventionIntensity}
                      .label=${localize("mold.intensity", l)}
                      @selected=${(e: Event) => {
                        const v = getSelectValue(e) as "light" | "medium" | "strong";
                        if (v && v !== this.moldPreventionIntensity) this._fire("moldPreventionIntensity", v);
                      }}
                      @closed=${(e: Event) => e.stopPropagation()}
                    >
                      <ha-list-item value="light">${localize("mold.intensity_light", l, { delta: String(toDisplayDelta(1, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                      <ha-list-item value="medium">${localize("mold.intensity_medium", l, { delta: String(toDisplayDelta(2, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                      <ha-list-item value="strong">${localize("mold.intensity_strong", l, { delta: String(toDisplayDelta(3, this.hass)), unit: tempUnit(this.hass) })}</ha-list-item>
                    </ha-select>
                    <span class="field-hint">${localize("mold.intensity_hint", l)}</span>
                  </div>
                `
              : nothing}
          </div>

          <!-- Notifications section -->
          ${this.moldDetectionEnabled || this.moldPreventionEnabled
            ? html`
                <div class="settings-section">
                  <div class="toggle-row">
                    <div class="toggle-text">
                      <span class="toggle-label">
                        <ha-icon icon="mdi:bell-outline" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                        ${localize("mold.notifications_enabled", l)}
                        <ha-icon
                          icon="mdi:alert-circle-outline"
                          style="--mdc-icon-size: 14px; vertical-align: middle; margin-left: 4px; color: var(--warning-color, #ffa600)"
                          title="${localize("mold.notifications_beta_hint", l)}"
                        ></ha-icon>
                      </span>
                      <span class="toggle-hint">${localize("mold.notifications_enabled_hint", l)}</span>
                    </div>
                    <ha-switch
                      .checked=${this.moldNotificationsEnabled}
                      @change=${(e: Event) => this._fire("moldNotificationsEnabled", (e.target as HTMLInputElement).checked)}
                    ></ha-switch>
                  </div>
                  ${this.moldNotificationsEnabled
                    ? html`
                  <p class="hint" style="margin-top: 12px">${localize("mold.notifications_desc", l)}</p>

                  <div class="presence-person-list">
                    ${this.moldNotificationTargets.map((t, idx) => {
                      const name = t.entity_id
                        ? (this.hass.states[t.entity_id]?.attributes?.friendly_name
                          ?? t.entity_id.replace("notify.", ""))
                        : localize("mold.target_unnamed", l);
                      return html`
                        <div class="mold-target-card">
                          <div class="mold-target-header">
                            <ha-icon icon="mdi:bell" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                            <span>${name}</span>
                            <ha-icon-button
                              .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                              @click=${() => {
                                this._fire("moldNotificationTargets", this.moldNotificationTargets.filter((_, i) => i !== idx));
                              }}
                            ></ha-icon-button>
                          </div>
                          <div class="mold-target-detail">
                            <ha-entity-picker
                              .hass=${this.hass}
                              .value=${t.person_entity}
                              .includeDomains=${["person"]}
                              .label=${localize("mold.target_person", l)}
                              allow-custom-entity
                              @value-changed=${(e: CustomEvent) => {
                                const targets = [...this.moldNotificationTargets];
                                targets[idx] = { ...targets[idx], person_entity: (e.detail?.value as string) ?? "" };
                                this._fire("moldNotificationTargets", targets);
                              }}
                            ></ha-entity-picker>
                            <ha-select
                              .value=${t.notify_when}
                              @selected=${(e: Event) => {
                                const v = getSelectValue(e) as "always" | "home_only";
                                if (!v) return;
                                const targets = [...this.moldNotificationTargets];
                                targets[idx] = { ...targets[idx], notify_when: v };
                                this._fire("moldNotificationTargets", targets);
                              }}
                              @closed=${(e: Event) => e.stopPropagation()}
                            >
                              <ha-list-item value="always">${localize("mold.target_when_always", l)}</ha-list-item>
                              <ha-list-item value="home_only">${localize("mold.target_when_home", l)}</ha-list-item>
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
                      .label=${localize("mold.add_target_label", l)}
                      allow-custom-entity
                      @value-changed=${(e: CustomEvent) => {
                        const v = (e.detail?.value as string) ?? "";
                        if (!v) return;
                        this._fire("moldNotificationTargets", [
                          ...this.moldNotificationTargets,
                          { entity_id: v, person_entity: "", notify_when: "always" as const },
                        ]);
                        const picker = e.target as HTMLElement & { value?: string };
                        if (picker) picker.value = "";
                      }}
                    ></ha-entity-picker>
                    <span class="field-hint">${localize("mold.add_target_hint", l)}</span>
                  </div>

                  ${this.moldPreventionEnabled
                    ? html`
                        <div class="toggle-row" style="margin-top: 12px">
                          <div class="toggle-text">
                            <span class="toggle-label">${localize("mold.prevention_notify", l)}</span>
                            <span class="toggle-hint">${localize("mold.prevention_notify_hint", l)}</span>
                          </div>
                          <ha-switch
                            .checked=${this.moldPreventionNotify}
                            @change=${(e: Event) => this._fire("moldPreventionNotify", (e.target as HTMLInputElement).checked)}
                          ></ha-switch>
                        </div>
                      `
                    : nothing}
                    `
                    : nothing}
                </div>
              `
            : nothing}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; }

    .hint { color: var(--secondary-text-color); font-size: 13px; margin: 0 0 12px; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    .presence-person-list { display: flex; flex-direction: column; gap: 2px; }

    .mold-target-card {
      display: flex; flex-direction: column; gap: 4px;
      padding: 8px 8px 8px 12px; border-radius: 8px; background: rgba(0, 0, 0, 0.04);
    }
    .mold-target-header { display: flex; align-items: center; gap: 8px; }
    .mold-target-header span { flex: 1; font-size: 14px; font-weight: 500; }
    .mold-target-detail { display: flex; gap: 8px; align-items: center; padding-left: 26px; }
    .mold-target-detail ha-entity-picker { flex: 1; }
    .mold-target-detail ha-select { min-width: 120px; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
      .mold-target-detail { flex-direction: column; padding-left: 0; }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-mold": RsSettingsMold;
  }
}

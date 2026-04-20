/**
 * rs-analytics-model – Model status card with confidence, stats grid, and info panels.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, AnalyticsData } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { infoIconStyles } from "../../styles/info-icon-styles";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";

@customElement("rs-analytics-model")
export class RsAnalyticsModel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: String }) public language = "en";

  @state() private _expandedStat: string | null = null;

  render() {
    const l = this.language;
    const hasModel = !!this.data?.model?.model;
    const m = this.data?.model;
    const model = m?.model;
    const confidence = m?.confidence ?? 0;
    const n_samples = m?.n_samples ?? 0;
    const n_heating = m?.n_heating ?? 0;
    const n_cooling = m?.n_cooling ?? 0;
    const applicable_modes = m?.applicable_modes ?? [];
    const predStdIdle = m?.prediction_std_idle;
    const predStdHeat = m?.prediction_std_heating;

    const mpcActive = m?.mpc_active ?? false;
    const confidencePct = Math.round(confidence * 100);
    const modes = new Set(applicable_modes);
    const canHeat = modes.has("heating");
    const canCool = modes.has("cooling");
    const hasHeated = n_heating >= 10;
    const hasCooled = n_cooling >= 10;
    const hasIdleData = n_samples - n_heating - n_cooling >= 10;
    const n_observations = m?.n_observations ?? n_samples;
    const ph = "\u2014";

    const statItems: Array<{ id: string; labelKey: TranslationKey; infoKey: TranslationKey }> = [];
    const stat = (
      id: string,
      value: string | number,
      labelKey: TranslationKey,
      unit: string,
      infoKey: TranslationKey,
    ) => {
      statItems.push({ id, labelKey, infoKey });
      const active = this._expandedStat === id;
      return html`
        <div class="model-stat ${active ? "active" : ""}" @click=${() => this._toggleStat(id)}>
          <div class="stat-content">
            <span class="model-value ${value === ph ? "pending" : ""}">${value}</span>
            <span class="model-label">${localize(labelKey, l)}${unit ? ` (${unit})` : ""}</span>
          </div>
          <ha-icon
            class="info-icon ${active ? "info-active" : ""}"
            icon="mdi:information-outline"
          ></ha-icon>
        </div>
      `;
    };

    return html`
      <ha-card>
        <div class="card-header">
          <span>${localize("analytics.model_status", l)}</span>
        </div>
        <div class="card-content">
          <div class="confidence-hero">
            <div class="confidence-top">
              <div class="confidence-main">
                <span class="confidence-value">${hasModel ? confidencePct + "%" : "0%"}</span>
                <span class="confidence-label">
                  ${localize("analytics.confidence", l)}
                  <ha-icon
                    class="info-icon ${this._expandedStat === "confidence" ? "info-active" : ""}"
                    icon="mdi:information-outline"
                    @click=${() => this._toggleStat("confidence")}
                  ></ha-icon>
                </span>
              </div>
              <div class="confidence-meta">
                <span class="meta-value">${hasModel ? n_observations : 0}</span>
                <span class="meta-label">
                  ${localize("analytics.data_points", l)}
                  <ha-icon
                    class="info-icon ${this._expandedStat === "data_points" ? "info-active" : ""}"
                    icon="mdi:information-outline"
                    @click=${() => this._toggleStat("data_points")}
                  ></ha-icon>
                </span>
              </div>
            </div>
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${hasModel ? confidencePct : 0}%"></div>
            </div>
            <div class="control-mode-badge ${mpcActive ? "mpc" : "bangbang"}">
              <ha-icon icon=${mpcActive ? "mdi:brain" : "mdi:school-outline"}></ha-icon>
              ${mpcActive
                ? localize("analytics.control_mode_mpc", l)
                : localize("analytics.control_mode_bangbang", l)}
            </div>
            ${this._expandedStat === "confidence"
              ? html`<div class="info-panel stat-info-panel">
                  <strong>${localize("analytics.confidence", l)}</strong>
                  ${localize("analytics.info.confidence", l)}
                </div>`
              : nothing}
            ${this._expandedStat === "data_points"
              ? html`<div class="info-panel stat-info-panel">
                  <strong>${localize("analytics.data_points", l)}</strong>
                  ${localize("analytics.info.data_points", l)}
                </div>`
              : nothing}
          </div>

          <div class="model-grid">
            ${stat(
              "time_constant",
              hasIdleData && model && model.U > 0 ? (1 / model.U).toFixed(1) + "h" : ph,
              "analytics.time_constant",
              "",
              "analytics.info.time_constant",
            )}
            ${canHeat
              ? stat(
                  "heating_rate",
                  hasHeated && model
                    ? toDisplayDelta(model.Q_heat, this.hass).toFixed(1) +
                        tempUnit(this.hass) +
                        "/h"
                    : ph,
                  "analytics.heating_rate",
                  "",
                  "analytics.info.heating_rate",
                )
              : nothing}
            ${canCool
              ? stat(
                  "cooling_rate",
                  hasCooled && model
                    ? toDisplayDelta(model.Q_cool, this.hass).toFixed(1) +
                        tempUnit(this.hass) +
                        "/h"
                    : ph,
                  "analytics.cooling_rate",
                  "",
                  "analytics.info.cooling_rate",
                )
              : nothing}
            ${model && model.Q_solar > 0.1
              ? stat(
                  "solar_gain",
                  toDisplayDelta(model.Q_solar, this.hass).toFixed(1) + tempUnit(this.hass) + "/h",
                  "analytics.solar_gain",
                  "",
                  "analytics.info.solar_gain",
                )
              : nothing}
            ${model && m?.has_occupancy_sensors && model.Q_occupancy > 0.1
              ? stat(
                  "occupancy_gain",
                  toDisplayDelta(model.Q_occupancy, this.hass).toFixed(1) +
                    tempUnit(this.hass) +
                    "/h",
                  "analytics.occupancy_gain",
                  "",
                  "analytics.info.occupancy_gain",
                )
              : nothing}
            ${stat(
              "accuracy_idle",
              hasIdleData && predStdIdle != null
                ? "\u00B1" + toDisplayDelta(predStdIdle, this.hass).toFixed(2) + tempUnit(this.hass)
                : ph,
              "analytics.accuracy_idle",
              "",
              "analytics.info.accuracy_idle",
            )}
            ${canHeat
              ? stat(
                  "accuracy_heating",
                  hasHeated && predStdHeat != null
                    ? "\u00B1" +
                        toDisplayDelta(predStdHeat, this.hass).toFixed(2) +
                        tempUnit(this.hass)
                    : ph,
                  "analytics.accuracy_heating",
                  "",
                  "analytics.info.accuracy_heating",
                )
              : nothing}
          </div>
          ${this._expandedStat && statItems.find((s) => s.id === this._expandedStat)
            ? html`<div class="info-panel stat-info-panel">
                <strong
                  >${localize(
                    statItems.find((s) => s.id === this._expandedStat)!.labelKey,
                    l,
                  )}</strong
                >
                ${localize(statItems.find((s) => s.id === this._expandedStat)!.infoKey, l)}
              </div>`
            : nothing}
        </div>
      </ha-card>
    `;
  }

  private _toggleStat(id: string) {
    this._expandedStat = this._expandedStat === id ? null : id;
  }

  static styles = [
    infoIconStyles,
    css`
      :host {
        display: block;
      }

      ha-card {
        margin-bottom: 16px;
      }

      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 16px 0;
        font-size: 16px;
        font-weight: 500;
      }

      .card-content {
        padding: 16px;
      }

      .confidence-hero {
        margin-bottom: 16px;
      }

      .confidence-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        margin-bottom: 8px;
      }

      .confidence-main {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .confidence-value {
        font-size: 28px;
        font-weight: 600;
        color: var(--primary-text-color);
      }

      .confidence-label {
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .confidence-meta {
        display: flex;
        align-items: baseline;
        gap: 6px;
      }

      .meta-value {
        font-size: 16px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .meta-label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .control-mode-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-top: 8px;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        --mdc-icon-size: 14px;
      }

      .control-mode-badge.mpc {
        background: rgba(76, 175, 80, 0.12);
        color: var(--success-color, #4caf50);
      }

      .control-mode-badge.bangbang {
        background: rgba(158, 158, 158, 0.12);
        color: var(--secondary-text-color);
      }

      .confidence-bar {
        height: 4px;
        border-radius: 2px;
        background: var(--divider-color);
        overflow: hidden;
      }

      .confidence-fill {
        height: 100%;
        border-radius: 2px;
        background: var(--primary-color);
        transition: width 0.6s ease;
      }

      .model-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 12px;
      }

      .model-stat {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--divider-color);
        cursor: pointer;
        transition: border-color 0.2s;
      }

      .model-stat.active {
        border-color: var(--primary-color);
      }

      .stat-content {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .model-value {
        font-size: 18px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .model-value.pending {
        opacity: 0.2;
      }

      .model-label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .info-panel.stat-info-panel {
        margin-top: 12px;
      }

      @media (max-width: 600px) {
        .model-grid {
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-model": RsAnalyticsModel;
  }
}

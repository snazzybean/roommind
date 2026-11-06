/**
 * rs-analytics-summary – What happened in the selected time range, read from the history.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AnalyticsStats, HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { infoIconStyles } from "../../styles/info-icon-styles";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";

@customElement("rs-analytics-summary")
export class RsAnalyticsSummary extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public stats: AnalyticsStats | null = null;
  @property({ type: Boolean }) public canHeat = true;
  @property({ type: Boolean }) public canCool = false;
  @property({ type: Boolean }) public hasWindowSensor = false;
  @property({ type: String }) public language = "en";

  @state() private _infoExpanded = false;

  render() {
    const s = this.stats;
    if (!s || s.hours <= 0) return nothing;
    const l = this.language;
    return html`
      <ha-card>
        <div class="header">
          <span>${localize("analytics.summary", l)}</span>
          <ha-icon
            class="info-icon ${this._infoExpanded ? "info-active" : ""}"
            icon="mdi:information-outline"
            @click=${() => {
              this._infoExpanded = !this._infoExpanded;
            }}
          ></ha-icon>
        </div>
        <div class="body">
          ${this._renderComfort(s)}
          <div class="tiles">
            ${
              this.canHeat || s.heating_hours > 0
                ? this._renderTile(
                    "mdi:fire",
                    "heat",
                    localize("analytics.heating_period", l),
                    s.heating_hours,
                    s.heating_starts,
                  )
                : nothing
            }
            ${
              this.canCool || s.cooling_hours > 0
                ? this._renderTile(
                    "mdi:snowflake",
                    "cool",
                    localize("analytics.cooling_period", l),
                    s.cooling_hours,
                    s.cooling_starts,
                  )
                : nothing
            }
            ${
              this.hasWindowSensor || s.window_hours > 0
                ? this._renderTile(
                    "mdi:window-open-variant",
                    "window",
                    localize("analytics.window_open_period", l),
                    s.window_hours,
                  )
                : nothing
            }
          </div>
        </div>
        ${
          this._infoExpanded
            ? html`<div class="info-panel summary-info">
                ${localize("analytics.info.summary", l)}
              </div>`
            : nothing
        }
      </ha-card>
    `;
  }

  private _renderComfort(s: AnalyticsStats) {
    const l = this.language;
    const c = s.comfort;
    if (!c) {
      return html`<div class="comfort pending">${localize("analytics.comfort_pending", l)}</div>`;
    }
    const pct = (v: number) =>
      new Intl.NumberFormat(l, { maximumFractionDigits: 0 }).format(v) + " %";
    const deviation = new Intl.NumberFormat(l, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(toDisplayDelta(c.mean_deviation, this.hass));
    // 99.6 % must not read as 100 % next to "too cold 1 %"
    const onTarget = Math.floor(c.within_pct);
    return html`
      <div class="comfort">
        <div class="comfort-head">
          <span class="comfort-value">${pct(onTarget)}</span>
          <span class="comfort-label">${localize("analytics.comfort_within", l)}</span>
        </div>
        <div
          class="bar"
          role="img"
          aria-label="${localize("analytics.comfort_below", l)} ${pct(c.below_pct)}, ${localize(
            "analytics.comfort_within",
            l,
          )} ${pct(c.within_pct)}, ${localize("analytics.comfort_above", l)} ${pct(c.above_pct)}"
        >
          ${c.below_pct > 0 ? html`<span class="cold" style="flex: ${c.below_pct}"></span>` : nothing}
          ${
            c.within_pct > 0
              ? html`<span class="within" style="flex: ${c.within_pct}"></span>`
              : nothing
          }
          ${c.above_pct > 0 ? html`<span class="warm" style="flex: ${c.above_pct}"></span>` : nothing}
        </div>
        <div class="comfort-foot">
          ${this._renderShare("cold", localize("analytics.comfort_below", l), c.below_pct, pct)}
          ${this._renderShare("warm", localize("analytics.comfort_above", l), c.above_pct, pct)}
          <span class="deviation"
            >${localize("analytics.mean_deviation", l, {
              value: `${deviation} ${tempUnit(this.hass)}`,
            })}</span
          >
        </div>
      </div>
    `;
  }

  private _renderShare(kind: string, label: string, value: number, pct: (v: number) => string) {
    return Math.round(value) > 0
      ? html`<span><i class="key ${kind}"></i>${label} ${pct(value)}</span>`
      : nothing;
  }

  private _renderTile(icon: string, kind: string, label: string, hours: number, starts?: number) {
    const l = this.language;
    return html`
      <div class="tile">
        <ha-icon class=${kind} icon=${icon}></ha-icon>
        <div class="tile-text">
          <span class="tile-value">${this._formatDuration(hours)}</span>
          <span class="tile-label">${label}</span>
          ${
            starts != null
              ? html`<span class="tile-sub"
                  >${localize(starts === 1 ? "analytics.run" : "analytics.runs", l, {
                    count: new Intl.NumberFormat(l).format(starts),
                  })}</span
                >`
              : nothing
          }
        </div>
      </div>
    `;
  }

  private _formatDuration(hours: number): string {
    const l = this.language;
    if (hours > 0 && hours < 1) {
      return `${new Intl.NumberFormat(l).format(Math.round(hours * 60))} min`;
    }
    return `${new Intl.NumberFormat(l, { maximumFractionDigits: 1 }).format(hours)} h`;
  }

  static styles = [
    infoIconStyles,
    css`
      :host {
        display: block;
        --rs-cold: var(--state-climate-cool-color, #2b9af9);
        --rs-warm: var(--state-climate-heat-color, #ff8100);
        --rs-within: var(--success-color, #43a047);
      }

      ha-card {
        margin-bottom: 16px;
      }

      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 16px 0;
        font-size: 16px;
        font-weight: 500;
      }

      .header .info-icon {
        --mdc-icon-size: 20px;
      }

      .body {
        display: grid;
        grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
        gap: 24px;
        padding: 12px 16px 16px;
        align-items: center;
      }

      .comfort-head {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .comfort-value {
        font-size: 28px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }

      .comfort-label {
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .comfort.pending {
        font-size: 13px;
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .bar {
        display: flex;
        gap: 2px;
        height: 8px;
        margin: 8px 0;
      }

      .bar span {
        min-width: 4px;
        border-radius: 2px;
      }

      .bar span:first-child {
        border-radius: 4px 2px 2px 4px;
      }

      .bar span:last-child {
        border-radius: 2px 4px 4px 2px;
      }

      .bar span:only-child {
        border-radius: 4px;
      }

      .bar .cold,
      .key.cold {
        background: var(--rs-cold);
      }

      .bar .within {
        background: var(--rs-within);
      }

      .bar .warm,
      .key.warm {
        background: var(--rs-warm);
      }

      .comfort-foot {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 14px;
        font-size: 12px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .comfort-foot span {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }

      .deviation {
        margin-left: auto;
      }

      .key {
        width: 8px;
        height: 8px;
        border-radius: 2px;
      }

      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
        gap: 12px;
      }

      .tile {
        display: flex;
        gap: 8px;
        min-width: 0;
      }

      .tile ha-icon {
        --mdc-icon-size: 18px;
        margin-top: 2px;
        flex-shrink: 0;
        color: var(--secondary-text-color);
      }

      .tile ha-icon.heat {
        color: var(--rs-warm);
      }

      .tile ha-icon.cool {
        color: var(--rs-cold);
      }

      .tile-text {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }

      .tile-value {
        font-size: 18px;
        font-weight: 500;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      .tile-label,
      .tile-sub {
        font-size: 12px;
        line-height: 1.35;
        color: var(--secondary-text-color);
        overflow-wrap: anywhere;
      }

      .tile-sub {
        opacity: 0.75;
      }

      .summary-info {
        margin: 0 16px 16px;
      }

      @media (max-width: 600px) {
        .body {
          grid-template-columns: minmax(0, 1fr);
          gap: 16px;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-summary": RsAnalyticsSummary;
  }
}

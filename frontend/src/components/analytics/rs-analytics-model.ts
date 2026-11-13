/**
 * rs-analytics-model – Model status: confidence, the stages towards predictive control and the
 * learned figures as tiles.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, AnalyticsData, BacktestFigures } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import {
  formatAgo,
  formatHours,
  formatMinutes,
  formatNumber,
  formatPercent,
} from "../../utils/format";
import {
  formatTempLocale,
  tempUnit,
  toCelsiusDelta,
  toDisplayDelta,
} from "../../utils/temperature";
import {
  MPC_MAX_PREDICTION_STD,
  MPC_MIN_ACTIVE_SAMPLES,
  MPC_MIN_IDLE_SAMPLES,
} from "../../utils/constants";
import { tokens, srOnly } from "../../styles/tokens";
import "../shared/rs-list-card";
import "../shared/rs-stat-tile";
import "../shared/rs-hint-chip";
import "../shared/rs-info-icon";

// Fixed reference so rooms and renovations stay comparable; the model knows no watts (C is unknown)
const HEAT_LOSS_REFERENCE_K = 10;
// Samples a figure needs before the tile shows it
const MIN_TILE_SAMPLES = 10;
const PENDING = "—";
// A systematic lean worth naming: at least this far and half the mean deviation
const BIAS_MIN_K = 0.1;

type StageState = "done" | "current" | "todo" | "off";

interface Stage {
  title: TranslationKey;
  sub: TranslationKey;
  icon: string;
  state: StageState;
  /** The last stage while MPC runs: an ongoing state, not a step still to take. */
  reached?: boolean;
}

interface Tile {
  id: string;
  icon: string;
  tone?: "heat" | "cool";
  value: string | null;
  detail?: string;
  /** Info text key when it is not analytics.info.<id>. */
  info?: TranslationKey;
}

const STAGE_STATE_KEY: Record<StageState, TranslationKey> = {
  done: "analytics.stage_state_done",
  current: "analytics.stage_state_current",
  todo: "analytics.stage_state_todo",
  off: "analytics.stage_state_off",
};

/** Data stage text per side the room has: [still collecting, idle done but runs missing]. */
const DATA_SUB: Record<"both" | "heat" | "cool", [TranslationKey, TranslationKey]> = {
  both: ["analytics.stage_data_sub", "analytics.stage_data_wait"],
  heat: ["analytics.stage_data_sub_heat", "analytics.stage_data_wait_heat"],
  cool: ["analytics.stage_data_sub_cool", "analytics.stage_data_wait_cool"],
};

@customElement("rs-analytics-model")
export class RsAnalyticsModel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: String }) public language = "en";
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Boolean }) public managed = false;
  /** Hours until "learn faster" has faded, null when it is not running. */
  @property({ attribute: false }) public boostHours: number | null = null;
  /** From the room's climate mode (the EKF lists every mode as applicable from the start). */
  @property({ type: Boolean }) public canHeat = true;
  @property({ type: Boolean }) public canCool = false;

  render() {
    const l = this.language;
    const m = this.data?.model;
    const hasModel = !!m?.model;
    const confidence = hasModel ? (m?.confidence ?? 0) : 0;
    const observations = hasModel ? (m?.n_observations ?? m?.n_samples ?? 0) : 0;
    return html`
      <rs-list-card .heading=${localize("analytics.model_status", l)}>
        ${this._controlChip()}
        <div class="wrap">
          <div class="top">
            <div class="status">
              <div class="confidence">
                <span class="confidence-value"
                  >${formatPercent(Math.round(confidence * 100), this.hass)}</span
                >
                <span class="confidence-label"
                  >${localize("analytics.confidence", l)}
                  <rs-info-icon
                    .text=${localize("analytics.info.confidence", l, {
                      threshold: this._delta(MPC_MAX_PREDICTION_STD),
                    })}
                  ></rs-info-icon
                ></span>
              </div>
              <div class="points">
                ${formatNumber(observations, this.hass)} ${localize("analytics.data_points", l)}
                <rs-info-icon .text=${localize("analytics.info.data_points", l)}></rs-info-icon>
              </div>
              ${
                hasModel && m?.last_update_at
                  ? html`<div class="updated">
                      ${localize("analytics.last_learned", l, { time: formatAgo(m.last_update_at, l) })}
                    </div>`
                  : nothing
              }
              ${
                this.boostHours != null
                  ? html`<div class="boost">
                      <ha-icon icon="mdi:school-outline" aria-hidden="true"></ha-icon>
                      ${localize("learning.boost_active", l, {
                        time: formatMinutes(this.boostHours * 60, l),
                      })}
                      <rs-info-icon .text=${localize("learning.boost_info", l)}></rs-info-icon>
                    </div>`
                  : nothing
              }
            </div>
            ${this._mpcRunning() ? this._renderNow() : this._renderStages()}
          </div>
          <div class="tiles">${this._tiles().map((t) => this._renderTile(t))}</div>
        </div>
      </rs-list-card>
    `;
  }

  private _controlChip() {
    const l = this.language;
    // Managed rooms (no external sensor) never run MPC, so "learning" would stay forever
    if (this.managed) return nothing;
    if (this.controlMode === "bangbang") {
      return html`<rs-hint-chip
        slot="header-extras"
        icon="mdi:power"
        .text=${localize("settings.control_mode_simple", l)}
      ></rs-hint-chip>`;
    }
    const active = this.data?.model?.mpc_active ?? false;
    return html`<rs-hint-chip
      slot="header-extras"
      .variant=${active ? "ok" : "default"}
      .icon=${active ? "mdi:brain" : "mdi:school-outline"}
      .text=${localize(active ? "analytics.control_mode_mpc" : "analytics.control_mode_bangbang", l)}
    ></rs-hint-chip>`;
  }

  /**
   * Stages from the real state: MPC running means all of them are reached (its gate also knows
   * the outdoor limits, the sample counts here do not); else the mirrored data gate. A room
   * with one side needs runs of that side; a room with both needs either, since the outdoor
   * limits usually close one of them.
   */
  private _stages(): Stage[] {
    const m = this.data?.model;
    const mpcActive = !!m?.model && !!m.mpc_active;
    const heating = m?.n_heating ?? 0;
    const cooling = m?.n_cooling ?? 0;
    const idle = (m?.n_samples ?? 0) - heating - cooling;
    const both = this.canHeat && this.canCool;
    const coolOnly = this.canCool && !this.canHeat;
    const runs = both ? Math.max(heating, cooling) : coolOnly ? cooling : heating;
    const idleDone = !!m?.model && idle >= MPC_MIN_IDLE_SAMPLES;
    const dataDone = mpcActive || (idleDone && runs >= MPC_MIN_ACTIVE_SAMPLES);
    const dataSub =
      DATA_SUB[both ? "both" : coolOnly ? "cool" : "heat"][!dataDone && idleDone ? 1 : 0];
    const accurate =
      m?.prediction_std_idle != null &&
      m.prediction_std_idle < MPC_MAX_PREDICTION_STD &&
      (heating < MPC_MIN_ACTIVE_SAMPLES ||
        m.prediction_std_heating == null ||
        m.prediction_std_heating < MPC_MAX_PREDICTION_STD);
    const learnDone = mpcActive || (dataDone && accurate);
    let control: Stage;
    if (this.managed) {
      control = {
        title: "analytics.stage_control",
        sub: "analytics.stage_control_managed",
        icon: "mdi:brain",
        state: "off",
      };
    } else if (this.controlMode === "bangbang") {
      control = {
        title: "analytics.stage_control",
        sub: "analytics.stage_control_simple",
        icon: "mdi:power",
        state: "off",
      };
    } else {
      control = {
        title: "analytics.stage_control",
        sub: "analytics.stage_control_sub",
        icon: "mdi:brain",
        state: learnDone ? "current" : "todo",
        reached: mpcActive,
      };
    }
    const stages: Stage[] = [
      {
        title: "analytics.stage_data",
        sub: dataSub,
        icon: "mdi:database-outline",
        state: dataDone ? "done" : "current",
      },
      {
        title: "analytics.stage_learn",
        sub: this.canCool
          ? this.canHeat
            ? "analytics.stage_learn_sub"
            : "analytics.stage_learn_sub_cool"
          : "analytics.stage_learn_sub_heat",
        icon: "mdi:school-outline",
        state: learnDone ? "done" : dataDone ? "current" : "todo",
      },
      control,
    ];
    return stages;
  }

  /** Once MPC runs the stages no longer change; the card then shows what the model says now. */
  private _mpcRunning(): boolean {
    const m = this.data?.model;
    return !this.managed && this.controlMode !== "bangbang" && !!m?.model && !!m.mpc_active;
  }

  /** Newest detail sample with room and outdoor temperature. */
  private _latest(): { room: number; outdoor: number } | null {
    const points = this.data?.detail ?? [];
    for (let i = points.length - 1; i >= 0; i--) {
      const p = points[i];
      if (p.room_temp != null && p.outdoor_temp != null) {
        return { room: p.room_temp, outdoor: p.outdoor_temp };
      }
    }
    return null;
  }

  /**
   * The learned model at the current room and outdoor temperature and sun: how long one degree
   * up (down) takes at full power and where the room drifts without heating or cooling. This is
   * what the planner works with, so it explains when RoomMind starts.
   */
  private _nowFacts(): { icon: string; label: string; value: string }[] {
    const m = this.data?.model;
    const model = m?.model;
    const now = this._latest();
    if (!m || !model || !now) return [];
    const l = this.language;
    const unit = tempUnit(this.hass);
    const oneDegree = toCelsiusDelta(1, this.hass);
    const loss = model.U * (now.room - now.outdoor);
    const sun = m.solar_learned ? (m.solar_gain_now ?? 0) : 0;
    const minutes = (net: number) =>
      net > 0.05
        ? localize("analytics.now_minutes", l, { time: formatMinutes((60 * oneDegree) / net, l) })
        : localize("analytics.now_not_enough", l);
    const facts: { icon: string; label: string; value: string }[] = [];
    if (this.canHeat && (m.n_heating ?? 0) >= MIN_TILE_SAMPLES) {
      facts.push({
        icon: "mdi:fire",
        label: localize("analytics.now_heat", l, { delta: `1 ${unit}` }),
        value: minutes(model.Q_heat - loss + sun),
      });
    }
    if (this.canCool && (m.n_cooling ?? 0) >= MIN_TILE_SAMPLES) {
      facts.push({
        icon: "mdi:snowflake",
        label: localize("analytics.now_cool", l, { delta: `1 ${unit}` }),
        value: minutes(model.Q_cool + loss - sun),
      });
    }
    if (model.U > 0) {
      const drift = toDisplayDelta(sun - loss, this.hass);
      const sign = drift >= 0.05 ? "+" : drift <= -0.05 ? "\u2212" : "";
      facts.push({
        icon: "mdi:home-thermometer-outline",
        label: localize(
          this.canHeat
            ? this.canCool
              ? "analytics.now_drift"
              : "analytics.now_drift_heat"
            : "analytics.now_drift_cool",
          l,
        ),
        value: `${sign}${formatNumber(Math.abs(drift), this.hass, 1)} ${unit}/h`,
      });
    }
    return facts;
  }

  private _renderNow() {
    const l = this.language;
    const now = this._latest();
    const facts = this._nowFacts();
    return html`<div class="now">
      <div class="step current reached">
        <span class="dot" aria-hidden="true"><ha-icon icon="mdi:brain"></ha-icon></span>
        <div class="step-text">
          <span class="step-title"
            >${localize("analytics.now_title", l)}
            ${
              facts.length
                ? html`<rs-info-icon .text=${localize("analytics.info.now", l)}></rs-info-icon>`
                : nothing
            }</span
          >
          <small
            >${
              now && facts.length
                ? localize("analytics.now_sub", l, {
                    room: `${formatTempLocale(now.room, this.hass, 1, 1)} ${tempUnit(this.hass)}`,
                    outdoor: `${formatTempLocale(now.outdoor, this.hass, 1, 1)} ${tempUnit(this.hass)}`,
                  })
                : localize("analytics.stage_control_sub", l)
            }</small
          >
        </div>
      </div>
      ${
        facts.length
          ? html`<dl class="facts">
              ${facts.map(
                (f) =>
                  html`<div class="fact">
                    <dt><ha-icon .icon=${f.icon} aria-hidden="true"></ha-icon>${f.label}</dt>
                    <dd>${f.value}</dd>
                  </div>`,
              )}
            </dl>`
          : nothing
      }
    </div>`;
  }

  private _renderStages() {
    const l = this.language;
    const stages = this._stages();
    return html`<ol class="steps">
      ${stages.map(
        (s, i) =>
          html`<li
            class="step ${s.state} ${s.reached ? "reached" : ""}"
            aria-current=${s.state === "current" ? "step" : "false"}
          >
            <span class="dot" aria-hidden="true">
              ${
                s.state === "done"
                  ? html`<ha-icon icon="mdi:check"></ha-icon>`
                  : s.state === "current"
                    ? html`<ha-icon .icon=${s.icon}></ha-icon>`
                    : s.state === "off"
                      ? html`<ha-icon icon="mdi:minus"></ha-icon>`
                      : formatNumber(i + 1, this.hass)
              }
            </span>
            <div class="step-text">
              <span class="step-title">${localize(s.title, l)}</span>
              <span class="sr-only">${localize(STAGE_STATE_KEY[s.state], l)}</span>
              <small>${localize(s.sub, l)}</small>
            </div>
          </li>`,
      )}
    </ol>`;
  }

  private _tiles(): Tile[] {
    const l = this.language;
    const m = this.data?.model;
    const model = m?.model;
    const heating = m?.n_heating ?? 0;
    const cooling = m?.n_cooling ?? 0;
    const modes = new Set(m?.applicable_modes ?? []);
    const canHeat = modes.has("heating");
    const canCool = modes.has("cooling");
    const hasHeated = heating >= MIN_TILE_SAMPLES;
    const hasCooled = cooling >= MIN_TILE_SAMPLES;
    const hasIdle = (m?.n_samples ?? 0) - heating - cooling >= MIN_TILE_SAMPLES;
    const unit = tempUnit(this.hass);
    const delta = (k: number, decimals: number) =>
      formatNumber(toDisplayDelta(k, this.hass), this.hass, decimals);
    const rate = (k: number) => `${delta(k, 1)} ${unit}/h`;
    const tiles: Tile[] = [
      {
        id: "time_constant",
        icon: "mdi:timer-sand",
        value: hasIdle && model && model.U > 0 ? formatHours(1 / model.U, l) : null,
      },
      {
        id: "heat_loss",
        icon: "mdi:home-thermometer-outline",
        value:
          hasIdle && model && model.U > 0
            ? `${delta(model.U * HEAT_LOSS_REFERENCE_K, 2)} ${unit}/h`
            : null,
        detail: localize("analytics.heat_loss_sub", l, {
          delta: `${formatNumber(toDisplayDelta(HEAT_LOSS_REFERENCE_K, this.hass), this.hass)} ${unit}`,
        }),
      },
    ];
    if (canHeat) {
      tiles.push({
        id: "heating_rate",
        icon: "mdi:fire",
        tone: "heat",
        value: hasHeated && model ? rate(model.Q_heat) : null,
      });
    }
    if (canHeat && hasHeated && m?.afterglow_k != null) {
      tiles.push({
        id: "afterglow",
        icon: "mdi:radiator",
        value: m.afterglow_learned ? this._afterglowValue(m.afterglow_k) : null,
        detail: m.afterglow_learned
          ? localize("analytics.afterglow_sub", l, {
              time: formatMinutes(m.afterglow_minutes ?? 0, l),
            })
          : localize("analytics.afterglow_unmeasured", l),
      });
    }
    if (canCool) {
      tiles.push({
        id: "cooling_rate",
        icon: "mdi:snowflake",
        tone: "cool",
        value: hasCooled && model ? rate(model.Q_cool) : null,
      });
    }
    // Shown once the data contained sun or occupancy: before that the value is the start guess
    if (model && m?.solar_learned && model.Q_solar > 0.1) {
      tiles.push({
        id: "solar_gain",
        icon: "mdi:white-balance-sunny",
        value: rate(model.Q_solar),
        detail:
          m?.solar_gain_now != null && m.solar_gain_today_max != null
            ? localize("analytics.solar_gain_sub", l, {
                now: rate(m.solar_gain_now),
                today: rate(m.solar_gain_today_max),
              })
            : undefined,
      });
    }
    if (model && m?.has_occupancy_sensors) {
      tiles.push({
        id: "occupancy_gain",
        icon: "mdi:account-group-outline",
        value: m.occupancy_learned ? rate(model.Q_occupancy) : null,
      });
    }
    const bt = m?.backtest;
    if (bt) {
      tiles.push(this._deviationTile("deviation_idle", "mdi:bullseye-arrow", bt.idle));
      if (canHeat || canCool) {
        tiles.push(
          this._deviationTile(
            canHeat ? (canCool ? "deviation_active" : "deviation_heat") : "deviation_cool",
            "mdi:bullseye",
            bt.active,
          ),
        );
      }
    }
    return tiles;
  }

  /** Mean deviation of the model one hour ahead, and which way it leans if it clearly does. */
  private _deviationTile(id: string, icon: string, f: BacktestFigures): Tile {
    const l = this.language;
    const unit = tempUnit(this.hass);
    const delta = (k: number) => formatNumber(toDisplayDelta(k, this.hass), this.hass, 2);
    let detail: string | undefined;
    if (f.mae == null) {
      detail = localize("analytics.deviation_collecting", l);
    } else if (f.bias != null && Math.abs(f.bias) >= Math.max(BIAS_MIN_K, f.mae / 2)) {
      detail = localize(
        f.bias < 0 ? "analytics.deviation_warmer" : "analytics.deviation_cooler",
        l,
        {
          delta: `${delta(Math.abs(f.bias))} ${unit}`,
        },
      );
    }
    return {
      id,
      icon,
      value: f.mae != null ? `±${delta(f.mae)} ${unit}` : null,
      detail,
      info: "analytics.info.deviation",
    };
  }

  private _renderTile(t: Tile) {
    const l = this.language;
    return html`<rs-stat-tile
      .icon=${t.icon}
      .tone=${t.tone ?? "default"}
      .label=${localize(`analytics.${t.id}` as TranslationKey, l)}
      .value=${t.value ?? PENDING}
      ?pending=${t.value == null}
      .info=${localize(t.info ?? (`analytics.info.${t.id}` as TranslationKey), l, {
        threshold: this._delta(MPC_MAX_PREDICTION_STD),
      })}
    >
      ${t.detail ? html`<span slot="info">${t.detail}</span>` : nothing}
    </rs-stat-tile>`;
  }

  /** A temperature difference in the user's unit ("0,5 °C", "0.9 °F"). */
  private _delta(kelvin: number): string {
    return `${formatNumber(toDisplayDelta(kelvin, this.hass), this.hass, 1)} ${tempUnit(this.hass)}`;
  }

  private _afterglowValue(kelvin: number): string {
    const value = toDisplayDelta(kelvin, this.hass);
    const unit = tempUnit(this.hass);
    // Rounded to "+0.0" it read like a broken value: light radiators store almost nothing
    return value < 0.05
      ? `< ${formatNumber(0.1, this.hass, 1)} ${unit}`
      : `+${formatNumber(value, this.hass, 1)} ${unit}`;
  }

  static styles = [
    tokens,
    srOnly,
    css`
      :host {
        display: block;
        margin-bottom: var(--rs-space-4);
      }

      .wrap {
        container-type: inline-size;
        padding: var(--rs-space-2) var(--rs-space-4) var(--rs-space-2);
      }

      .top {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: var(--rs-space-5);
        margin-bottom: var(--rs-space-4);
      }

      @container (min-width: 760px) {
        .top {
          grid-template-columns: minmax(200px, 260px) minmax(0, 1fr);
          gap: var(--rs-space-6);
          align-items: start;
        }
      }

      .confidence {
        display: flex;
        align-items: baseline;
        gap: var(--rs-space-2);
        flex-wrap: wrap;
      }

      .confidence-value {
        font-size: 44px;
        font-weight: 300;
        line-height: 1;
        font-variant-numeric: tabular-nums;
      }

      .confidence-label,
      .points {
        display: inline-flex;
        align-items: center;
        gap: 2px;
        font-size: var(--rs-font-md);
        color: var(--secondary-text-color);
      }

      .boost {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 6px;
        font-size: var(--rs-font-sm);
        color: var(--primary-text-color);
        --mdc-icon-size: 16px;
      }

      .boost ha-icon {
        color: var(--primary-color);
      }

      .points {
        margin-top: 6px;
        font-size: var(--rs-font-sm);
        font-variant-numeric: tabular-nums;
      }

      .updated {
        margin-top: 2px;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .steps {
        list-style: none;
        margin: 0;
        padding: 0;
      }

      .step {
        position: relative;
        display: flex;
        gap: var(--rs-space-3);
        align-items: flex-start;
        padding-bottom: 14px;
        font-size: 13px;
      }

      .step:last-child {
        padding-bottom: 0;
      }

      .step:not(:last-child)::before {
        content: "";
        position: absolute;
        left: 11px;
        top: 26px;
        bottom: 2px;
        width: 2px;
        background: var(--rs-border);
      }

      .step.done:not(:last-child)::before {
        background: color-mix(in srgb, var(--rs-ok) 50%, transparent);
      }

      .dot {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        flex: none;
        background: var(--rs-fill);
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
        font-variant-numeric: tabular-nums;
        --mdc-icon-size: 15px;
      }

      .step.done .dot {
        background: color-mix(in srgb, var(--rs-ok) 18%, transparent);
        color: var(--rs-ok);
      }

      .step.current .dot {
        background: var(--primary-color);
        color: var(--text-primary-color);
      }

      .step.current.reached .dot {
        background: var(--rs-ok);
      }

      .step-text {
        display: flex;
        flex-direction: column;
        min-width: 0;
        padding-top: 3px;
      }

      .step.todo .step-title,
      .step.off .step-title {
        color: var(--secondary-text-color);
      }

      .step small {
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }

      .now .step::before {
        display: none;
      }

      .now .step-title {
        display: inline-flex;
        align-items: center;
        gap: 2px;
      }

      .facts {
        margin: var(--rs-space-3) 0 0;
        padding: 0 0 0 36px;
        max-width: 420px;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .fact {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: var(--rs-space-3);
        font-size: 13px;
      }

      .fact dt {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
        color: var(--secondary-text-color);
        --mdc-icon-size: 16px;
      }

      .fact dd {
        margin: 0;
        font-weight: 500;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      .tiles {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }

      @container (min-width: 560px) {
        .tiles {
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }
      }

      @container (min-width: 900px) {
        .tiles {
          grid-template-columns: repeat(4, minmax(0, 1fr));
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

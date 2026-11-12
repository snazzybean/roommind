import { LitElement, html, css, nothing, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomConfig, RoomLiveData } from "../../types";
import {
  hintText,
  isRoomControlled,
  minutesLeft,
  mpcStatus,
  roomHints,
  roomStateInfo,
  targetReason,
  type RoomHint,
  priceShiftInfo,
} from "../../utils/room-state";
import { localize } from "../../utils/localize";
import { formatTempLocale, tempUnit, toDisplayDelta } from "../../utils/temperature";
import { formatMinutes, formatNumber, formatPercent } from "../../utils/format";
import { buildSparkline, type RecentTemp, type SparklinePaths } from "../../utils/sparkline";
import { NO_OVERRIDE, type EffectiveOverride } from "../../utils/override";
import { boostHoursLeft } from "../../utils/learning";
import { tokens } from "../../styles/tokens";
import "../shared/rs-hint-chip";
import "../shared/rs-icon-button";
import "../shared/rs-info-icon";

const CURVE_W = 400;
const CURVE_H = 72;

interface HeroChip {
  icon: string;
  text: string;
  variant: "default" | "warn" | "error";
  info?: string;
}

/**
 * Head of the room page: name (renamable), state, current temperature over the curve of the
 * last hours, everything noteworthy as hint chips, the target and why it applies. The
 * override control goes into the `control` slot.
 */
@customElement("rs-room-hero")
export class RsRoomHero extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ type: Boolean }) public isOutdoor = false;
  /** Global and room switch together (the room's switch from the unsaved local state). */
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ attribute: false }) public overrideInfo: EffectiveOverride = NO_OVERRIDE;
  @property({ attribute: false }) public outdoorTemp: number | null = null;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ attribute: false }) public vacationUntil: number | null = null;

  @state() private _editingName = false;
  @state() private _nameInput = "";
  @state() private _tick = 0;

  private _sparkFor?: readonly RecentTemp[];
  private _spark: SparklinePaths | null = null;
  private _timer?: ReturnType<typeof setInterval>;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      ha-card {
        position: relative;
        overflow: hidden;
        isolation: isolate;
        padding: 18px 20px 20px;
      }

      /* own band below the temperature, edge to edge: the curve never sits behind text */
      .band {
        position: relative;
        height: 72px;
        margin: var(--rs-space-3) -20px 0;
      }

      @media (max-width: 600px) {
        .band {
          height: 56px;
        }
      }

      .band svg {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
      }

      /* a backing keeps the dashed target line from striking the label through */
      .curve-label {
        position: absolute;
        right: 12px;
        top: 2px;
        padding: 0 4px;
        border-radius: 4px;
        background: var(--ha-card-background, var(--card-background-color));
        font-size: 11px;
        color: var(--secondary-text-color);
      }

      .top {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
        min-width: 0;
      }

      .chip {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        flex: none;
        display: grid;
        place-items: center;
        background: var(--rs-fill);
        color: var(--secondary-text-color);
        --mdc-icon-size: 22px;
      }

      .chip.heat {
        background: color-mix(in srgb, var(--rs-heat) 16%, transparent);
        color: var(--rs-heat);
      }

      .chip.cool {
        background: color-mix(in srgb, var(--rs-cool) 16%, transparent);
        color: var(--rs-cool);
      }

      .who {
        flex: 1;
        min-width: 0;
      }

      .name-row {
        display: flex;
        align-items: center;
        gap: 2px;
        min-width: 0;
      }

      h2 {
        margin: 0;
        font-size: var(--rs-font-lg);
        font-weight: 500;
        line-height: 24px;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .name-row rs-icon-button {
        color: var(--secondary-text-color);
        margin: -8px 0;
        /* above the enlarged touch area of the info icon in the line below */
        position: relative;
        z-index: 1;
      }

      .name-edit {
        display: flex;
        align-items: center;
        gap: 4px;
        min-width: 0;
      }

      .name-input {
        flex: 1;
        min-width: 0;
        font: inherit;
        font-size: var(--rs-font-lg);
        color: var(--primary-text-color);
        background: transparent;
        border: none;
        border-bottom: 2px solid var(--primary-color);
        outline: none;
        padding: 2px 0;
      }

      .name-clear {
        background: none;
        border: none;
        padding: 6px 0;
        font: inherit;
        font-size: var(--rs-font-sm);
        color: var(--primary-color);
        cursor: pointer;
      }

      .name-clear:focus-visible {
        outline: 2px solid var(--primary-color);
        border-radius: 4px;
      }

      .state {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0 4px;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .state .heat {
        color: var(--rs-heat-text);
      }

      .state .cool {
        color: var(--rs-cool-text);
      }

      .now {
        margin-top: 14px;
        font-size: 64px;
        font-weight: 300;
        letter-spacing: -1.5px;
        line-height: 1;
        font-variant-numeric: tabular-nums;
        display: flex;
        align-items: flex-start;
      }

      .now small {
        font-size: 22px;
        color: var(--secondary-text-color);
        letter-spacing: 0;
        margin: 6px 0 0 4px;
      }

      .now.none {
        color: var(--secondary-text-color);
      }

      .facts {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 14px;
        margin-top: 10px;
        font-size: 13px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .facts span {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        --mdc-icon-size: 16px;
      }

      .facts .warn {
        color: var(--rs-warn-text);
      }

      .facts .error {
        color: var(--rs-err-text);
      }

      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: var(--rs-space-3);
      }

      .chips rs-hint-chip {
        max-width: 100%;
      }

      .nodata {
        margin-top: var(--rs-space-4);
        color: var(--secondary-text-color);
        font-size: var(--rs-font-md);
      }

      .target {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
        margin-top: 20px;
        padding-top: 14px;
        border-top: 1px solid var(--divider-color);
      }

      .target .lbl {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .target .v {
        font-size: 28px;
        line-height: 1.2;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
      }

      .target .v.inactive {
        color: var(--secondary-text-color);
      }

      .why {
        margin-left: auto;
        text-align: end;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        min-width: 0;
        max-width: 60%;
      }

      .why b {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 4px;
        color: var(--primary-text-color);
        font-weight: 500;
        font-size: 13px;
        --mdc-icon-size: 15px;
      }

      .why b span {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .why .adj {
        display: block;
        margin-top: 2px;
      }

      ::slotted([slot="control"]) {
        display: block;
        margin-top: var(--rs-space-4);
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    // Countdowns ("1 h 20 min left") and minute hints stay current between polls.
    this._timer = setInterval(() => this._tick++, 30_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    clearInterval(this._timer);
  }

  private get _lang(): string {
    return this.hass?.language ?? "en";
  }

  private get _controlled(): boolean {
    return !!this.config?.live && !this.isOutdoor && this.climateControlActive;
  }

  render() {
    if (!this.hass || !this.area) return nothing;
    const live = this.config?.live;
    const st = this._controlled ? roomStateInfo(this.config!, true) : null;
    const tone =
      st && !live?.window_open && (st.tone === "heat" || st.tone === "cool") ? st.tone : null;
    const color = tone === "heat" ? "var(--rs-heat)" : tone === "cool" ? "var(--rs-cool)" : "";

    return html`<ha-card style=${color ? `--c: ${color}` : "--c: var(--secondary-text-color)"}>
      <div class="top">
        <span class="chip ${tone ?? ""}" aria-hidden="true"
          ><ha-icon .icon=${this.area.icon || "mdi:texture-box"}></ha-icon
        ></span>
        <div class="who">
          ${this._editingName ? this._renderNameEdit() : this._renderName()}
          <div class="state">${this._renderState()}</div>
        </div>
      </div>
      ${
        live
          ? html`${this._renderTemps(live, !!color)} ${this._renderChips(live)}
            ${this.config && !this.isOutdoor ? this._renderTarget(live) : nothing}`
          : html`<div class="nodata">
              ${localize(this.config ? "hero.waiting" : "hero.not_configured", this._lang)}
            </div>`
      }
      <slot name="control"></slot>
    </ha-card>`;
  }

  private _renderCurve(active: boolean) {
    const points = this.config?.live?.recent_temps;
    if (points !== this._sparkFor) {
      this._sparkFor = points;
      this._spark = buildSparkline(points, { width: CURVE_W, height: CURVE_H, padK: 1.4 });
    }
    const s = this._spark;
    if (!s) return nothing;
    return html`<div class="band">
      <svg viewBox="0 0 ${CURVE_W} ${CURVE_H}" preserveAspectRatio="none" aria-hidden="true">
        ${svg`<defs>
          <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="var(--c)" stop-opacity=${active ? 0.2 : 0.12}></stop>
            <stop offset="1" stop-color="var(--c)" stop-opacity="0"></stop>
          </linearGradient>
        </defs>
        <path d=${s.area} fill="url(#fade)"></path>
        ${
          s.target
            ? svg`<path d=${s.target} fill="none" stroke="var(--secondary-text-color)"
                stroke-width="1" stroke-dasharray="3 3" opacity="0.45"
                vector-effect="non-scaling-stroke"></path>`
            : nothing
        }
        <path d=${s.line} fill="none" stroke="var(--c)" stroke-width="1.5" stroke-opacity="0.6"
          stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>`}
      </svg>
      <span class="curve-label" aria-hidden="true"
        >${localize("detail.hero.last_hours", this._lang)}</span
      >
    </div>`;
  }

  private _renderName() {
    return html`<div class="name-row">
      <h2>${this.config?.display_name || this.area.name}</h2>
      <rs-icon-button
        size="sm"
        icon="mdi:pencil-outline"
        .label=${localize("detail.rename", this._lang)}
        @click=${this._onEditName}
      ></rs-icon-button>
    </div>`;
  }

  private _renderNameEdit() {
    const l = this._lang;
    return html`<div class="name-edit">
        <input
          class="name-input"
          type="text"
          aria-label=${localize("detail.rename", l)}
          autocomplete="off"
          .value=${this._nameInput}
          placeholder=${localize("room.alias.placeholder", l)}
          @input=${(e: Event) => (this._nameInput = (e.target as HTMLInputElement).value)}
          @keydown=${this._onNameKeydown}
        />
        <rs-icon-button
          size="sm"
          icon="mdi:check"
          .label=${localize("detail.rename_done", l)}
          @click=${this._onNameDone}
        ></rs-icon-button>
      </div>
      ${
        this.config?.display_name
          ? html`<button type="button" class="name-clear" @click=${this._onNameClear}>
              ${localize("room.alias.clear", l)}
            </button>`
          : nothing
      }`;
  }

  private _renderState() {
    const l = this._lang;
    if (this.isOutdoor) {
      return html`<span
        >${localize("card.outdoor", l)} · ${localize("card.measure_only", l)}</span
      >`;
    }
    if (!this.config) return html`<span>${localize("card.not_set_up", l)}</span>`;
    const managed = !this.config.temperature_sensor;
    const modeLabel = localize(
      managed ? "room.control_mode.managed" : "room.control_mode.full_control",
      l,
    );
    const modeInfo = html`<span>${modeLabel}</span>
      <rs-info-icon
        .text=${localize(
          managed ? "room.control_mode.managed_info" : "room.control_mode.full_control_info",
          l,
        )}
      ></rs-info-icon>`;
    if (!this.config.live) return modeInfo;
    if (!isRoomControlled(this.config, this.climateControlActive)) {
      return html`<span>${localize("card.state.off", l)} ·</span>${modeInfo}`;
    }
    const st = roomStateInfo(this.config, true);
    const tone = st.tone === "heat" || st.tone === "cool" ? st.tone : "";
    return html`<span class=${tone}
        >${localize(st.key, l)}${st.power != null ? ` · ${formatPercent(st.power, this.hass)}` : ""}</span
      ><span>·</span>${modeInfo}`;
  }

  private _renderTemps(live: RoomLiveData, curveActive: boolean) {
    const l = this._lang;
    const unit = tempUnit(this.hass);
    const facts = [];
    if (live.current_humidity != null) {
      facts.push(
        html`<span
          ><ha-icon icon="mdi:water-percent" aria-hidden="true"></ha-icon>${localize(
            "detail.hero.humidity",
            l,
            { value: formatPercent(live.current_humidity, this.hass) },
          )}</span
        >`,
      );
    }
    if (this.outdoorTemp != null && !this.isOutdoor) {
      facts.push(
        html`<span
          ><ha-icon icon="mdi:thermometer-lines" aria-hidden="true"></ha-icon>${localize(
            "detail.hero.outdoor",
            l,
            { value: `${formatTempLocale(this.outdoorTemp, this.hass)} ${unit}` },
          )}</span
        >`,
      );
    }
    if (!this.isOutdoor) {
      if (live.device_setpoint != null) {
        facts.push(
          html`<span
            ><ha-icon
              icon=${live.mode === "cooling" ? "mdi:snowflake" : "mdi:radiator"}
              aria-hidden="true"
            ></ha-icon
            >${localize("detail.hero.device_setpoint", l, {
              value: `${formatTempLocale(live.device_setpoint, this.hass)} ${unit}`,
            })}</span
          >`,
        );
      }
      if (live.active_heat_sources && live.active_heat_sources !== "none") {
        facts.push(
          html`<span
            ><ha-icon icon="mdi:swap-horizontal" aria-hidden="true"></ha-icon>${localize(
              live.active_heat_sources === "primary"
                ? "hero.heat_source_primary"
                : live.active_heat_sources === "secondary"
                  ? "hero.heat_source_secondary"
                  : "hero.heat_source_both",
              l,
            )}</span
          >`,
        );
      }
      if (live.mold_surface_rh != null) {
        const cls =
          live.mold_risk_level === "critical"
            ? "error"
            : live.mold_risk_level === "warning"
              ? "warn"
              : "";
        facts.push(
          html`<span class=${cls}
            ><ha-icon icon="mdi:water-alert" aria-hidden="true"></ha-icon>${localize(
              "room.mold_surface_rh",
              l,
              { value: formatPercent(live.mold_surface_rh, this.hass) },
            )}${
              live.mold_surface_temp != null
                ? ` · ${localize("room.mold_surface_temp", l, {
                    value: `${formatTempLocale(live.mold_surface_temp, this.hass)} ${unit}`,
                  })}`
                : ""
            }</span
          >`,
        );
      }
      if (this._controlled && mpcStatus(this.config, this.controlMode) === "active") {
        facts.push(
          html`<span
            ><ha-icon icon="mdi:brain" aria-hidden="true"></ha-icon>${localize(
              "card.mpc_active",
              l,
            )}</span
          >`,
        );
      }
    }
    return html`
      ${
        live.current_temp != null
          ? html`<div class="now">
              ${formatTempLocale(live.current_temp, this.hass)}<small>${unit}</small>
            </div>`
          : html`<div class="now none">--</div>`
      }
      ${this._renderCurve(curveActive)}
      ${facts.length ? html`<div class="facts">${facts}</div>` : nothing}
    `;
  }

  /** Hints the target block does not already explain, plus the hero-only details. */
  private _chips(live: RoomLiveData): HeroChip[] {
    const l = this._lang;
    if (this.isOutdoor || !this.config) return [];
    const withTarget = !!this.config;
    const inReason = new Set([
      "override",
      "presence_away",
      "room_vacant",
      "mold_prevention",
      "price_shift",
      "not_controlled",
    ]);
    const hints: RoomHint[] = roomHints(this.config, "controlled", {
      climateControlActive: this.climateControlActive,
      controlMode: this.controlMode,
      language: l,
      displayDelta: (d) => toDisplayDelta(d, this.hass),
      formatTemp: (c) => formatTempLocale(c, this.hass, 0, 1),
      unit: tempUnit(this.hass),
    }).filter((h) => !(withTarget && inReason.has(h.id)));
    const boostHours = boostHoursLeft(live.boost_applied_at, live.n_observations);
    const chips: HeroChip[] = hints
      // The boost chip says it more precisely
      .filter((h) => !(boostHours != null && h.id === "mpc_learning"))
      .map((h) => ({
        icon: h.icon,
        text: hintText(h, l),
        variant: h.severity === "info" ? "default" : h.severity,
        info:
          h.id === "compressor"
            ? localize("hero.compressor_protection_info", l)
            : h.id === "learning_paused" && live.learning_paused_reason === "outdoor_unavailable"
              ? localize("hero.mpc_learning_paused.outdoor_unavailable", l)
              : undefined,
      }));
    // Compressor protection without a known end has no card hint; the hero names it anyway.
    if (live.compressor_protection_active && live.compressor_protection_until == null) {
      chips.push({
        icon: "mdi:timer-sand",
        text: localize(
          live.compressor_protection_reason === "min_run"
            ? "hero.compressor_protection_min_run"
            : "hero.compressor_protection_min_off",
          l,
        ),
        variant: "default",
        info: localize("hero.compressor_protection_info", l),
      });
    }
    if (boostHours != null) {
      chips.push({
        icon: "mdi:school-outline",
        text: localize("learning.boost_active", l, { time: formatMinutes(boostHours * 60, l) }),
        variant: "default",
        info: localize("learning.boost_info", l),
      });
    }
    if (live.coil_dry_active) {
      chips.push({
        icon: "mdi:air-filter",
        text: localize(
          live.coil_dry_phase === "drain" ? "hero.coil_dry_drain" : "hero.coil_dry",
          l,
          {
            time: formatMinutes(minutesLeft(live.coil_dry_until), l),
          },
        ),
        variant: "default",
        info: localize("hero.coil_dry_info", l),
      });
    }
    return chips;
  }

  private _renderChips(live: RoomLiveData) {
    const chips = this._chips(live);
    if (!chips.length) return nothing;
    return html`<div class="chips">
      ${chips.map(
        (c) =>
          html`<rs-hint-chip
            .icon=${c.icon}
            .text=${c.text}
            .variant=${c.variant}
            .info=${c.info ?? ""}
          ></rs-hint-chip>`,
      )}
    </div>`;
  }

  private _renderTarget(live: RoomLiveData) {
    const l = this._lang;
    const ov = this.overrideInfo;
    const suppressed = live.override_suppressed && live.override_active;
    const useOv = ov.active && !suppressed;
    const heat = useOv ? ov.heat : live.heat_target;
    const cool = useOv ? ov.cool : live.cool_target;
    const mode = this.config?.climate_mode ?? "auto";
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const unit = tempUnit(this.hass);
    let value: string;
    if (mode === "auto" && heat != null && cool != null && heat !== cool) {
      value = `${fmt(heat)}–${fmt(cool)} ${unit}`;
    } else {
      const single = useOv
        ? (heat ?? cool ?? live.target_temp)
        : mode === "cool_only"
          ? (live.target_temp ?? cool)
          : (live.target_temp ?? heat);
      const devicesOff = live.heat_target === null && live.cool_target === null;
      value =
        single != null ? `${fmt(single)} ${unit}` : devicesOff ? localize("detail.off", l) : "--";
    }
    // Climate control off: RoomMind sends nothing, so the target is not in force
    const inactive = !this.climateControlActive;
    const reason = inactive
      ? {
          icon: "mdi:power-off",
          label: localize("hero.control_off", l),
          detail: localize("card.not_controlled", l),
        }
      : targetReason(this.config!, ov, {
          language: l,
          states: this.hass.states,
          vacationActive: this.vacationActive,
          vacationUntil: this.vacationUntil,
        });
    const adjustments: string[] = [];
    const price = inactive ? null : priceShiftInfo(this.config);
    if (price) {
      const shiftValue = `${new Intl.NumberFormat(l, {
        signDisplay: "always",
        maximumFractionDigits: 1,
      }).format(toDisplayDelta(price.delta, this.hass))} ${unit}`;
      const key = !price.charging
        ? "hero.price_coasting"
        : price.side === "cool"
          ? "hero.price_precooling"
          : "hero.price_charging";
      adjustments.push(localize(key, l, { value: shiftValue }));
    }
    if (live.mold_prevention_active && !inactive) {
      adjustments.push(
        localize("card.mold_prevention", l, {
          delta: `${formatNumber(toDisplayDelta(live.mold_prevention_delta, this.hass), this.hass)} ${unit}`,
        }),
      );
    }
    return html`<div class="target">
      <div>
        <div class="lbl">${localize("hero.target", l)}</div>
        <div class="v ${inactive ? "inactive" : ""}">${value}</div>
      </div>
      <div class="why">
        <b
          ><ha-icon .icon=${reason.icon} aria-hidden="true"></ha-icon
          ><span>${reason.label}</span></b
        >
        ${reason.detail} ${adjustments.map((a) => html`<span class="adj">${a}</span>`)}
      </div>
    </div>`;
  }

  private _onEditName(): void {
    this._nameInput = this.config?.display_name || "";
    this._editingName = true;
    this.updateComplete.then(() => {
      const input = this.renderRoot.querySelector<HTMLInputElement>(".name-input");
      input?.focus();
      input?.select();
    });
  }

  private _onNameKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter") this._onNameDone();
    else if (e.key === "Escape") {
      e.stopPropagation();
      this._editingName = false;
    }
  }

  private _fireName(value: string): void {
    this.dispatchEvent(
      new CustomEvent("display-name-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onNameDone(): void {
    this._fireName(this._nameInput.trim());
    this._editingName = false;
  }

  private _onNameClear(): void {
    this._fireName("");
    this._editingName = false;
    this._nameInput = "";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-hero": RsRoomHero;
  }
}

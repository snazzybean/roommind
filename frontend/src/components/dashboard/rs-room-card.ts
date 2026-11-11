import { LitElement, html, css, nothing, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomConfig, RoomLiveData } from "../../types";
import {
  hintText,
  isRoomControlled,
  mpcStatus,
  roomHints,
  roomKind,
  roomStateInfo,
  type RoomHint,
  type RoomKind,
} from "../../utils/room-state";
import { localize, type TranslationKey } from "../../utils/localize";
import { formatTempLocale, tempUnit, toDisplayDelta } from "../../utils/temperature";
import { formatPercent } from "../../utils/format";
import { buildSparkline, type SparklinePaths, type RecentTemp } from "../../utils/sparkline";
import { overrideSetMessage, QUICK_OVERRIDE_FALLBACK_H } from "../../utils/override";
import { tokens, srOnly } from "../../styles/tokens";
import type { RsSegmentOption } from "../shared/rs-segmented";
import "../shared/rs-segmented";
import "../shared/rs-hint-chip";

/** Height of every room card, whatever it shows (design system: the card never grows). */
export const ROOM_CARD_HEIGHT = 272;
const CURVE_W = 300;
const CURVE_H = 120;
/** Icon chips next to the first (text) hint before the rest collapse into "+n". */
const MAX_ICON_HINTS = 4;
/** How long an optimistic quick choice waits for the poll to confirm it. */
const PENDING_TIMEOUT_MS = 15000;
const ERROR_VISIBLE_MS = 6000;

export type QuickValue = "schedule" | "comfort" | "eco";

/** Quick choice the room's live state stands for; null for a custom override. */
export function quickValueOf(live: RoomLiveData | undefined): QuickValue | null {
  if (!live?.override_active) return "schedule";
  if (live.override_type === "boost") return "comfort";
  if (live.override_type === "eco") return "eco";
  return null;
}

/**
 * Dashboard room card: fixed height, temperature curve of the last hours in the background,
 * one row of hints and the quick choice schedule/comfort/eco. The room name is the link to
 * the room; it covers the whole card, controls sit above it.
 */
@customElement("rs-room-card")
export class RsRoomCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ type: Number }) public climateEntityCount = 0;
  @property({ type: Number }) public tempSensorCount = 0;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Boolean }) public climateControlActive = true;
  /** Static look-alike for edit mode: not focusable, no actions. */
  @property({ type: Boolean, reflect: true }) public preview = false;

  @state() private _pending: { value: QuickValue; since: number } | null = null;
  @state() private _error = "";

  private _sparkFor?: readonly RecentTemp[];
  private _spark: SparklinePaths | null = null;
  private _errorTimer?: ReturnType<typeof setTimeout>;

  static styles = [
    tokens,
    srOnly,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      ha-card {
        position: relative;
        height: ${ROOM_CARD_HEIGHT}px;
        overflow: hidden;
        isolation: isolate;
        box-sizing: border-box;
        transition: border-color 0.15s ease;
      }

      :host(:not([preview])) ha-card:hover {
        --ha-card-border-color: var(--rs-border-strong);
      }

      .inner {
        height: 100%;
        box-sizing: border-box;
        padding: 14px 16px;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      svg.bg {
        position: absolute;
        left: 0;
        width: 100%;
        top: 88px;
        height: calc(100% - 88px - 56px);
        z-index: -1;
        pointer-events: none;
        overflow: visible;
      }

      .head {
        display: flex;
        align-items: center;
        gap: 8px;
        height: 24px;
        flex: none;
        min-width: 0;
      }

      .ricon {
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
        flex: none;
        display: inline-flex;
      }

      h3 {
        margin: 0;
        flex: 1;
        min-width: 0;
        font-size: 16px;
        font-weight: 500;
        line-height: 24px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      a.open {
        color: inherit;
        text-decoration: none;
        outline: none;
      }

      /* the name is the link, stretched over the whole card */
      a.open::after {
        content: "";
        position: absolute;
        inset: 0;
        z-index: 0;
        border-radius: var(--rs-radius);
      }

      a.open:focus-visible::after {
        box-shadow: inset 0 0 0 2px var(--primary-color);
      }

      .state {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        font-size: 13px;
        color: var(--secondary-text-color);
        white-space: nowrap;
        flex: none;
        --mdc-icon-size: 17px;
        font-variant-numeric: tabular-nums;
      }

      :host([preview]) .state {
        visibility: hidden;
      }

      .state.heat {
        color: var(--rs-heat);
      }

      .state.cool {
        color: var(--rs-cool);
      }

      .temps {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        flex: none;
        min-width: 0;
      }

      .now {
        font-size: var(--rs-font-display);
        font-weight: 300;
        line-height: 1;
        letter-spacing: -1px;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      .now small {
        font-size: 18px;
        color: var(--secondary-text-color);
        margin-left: 3px;
        letter-spacing: 0;
        vertical-align: top;
        position: relative;
        top: 5px;
      }

      .now.none {
        color: var(--secondary-text-color);
      }

      .hum {
        display: inline-flex;
        align-items: center;
        gap: 2px;
        margin-top: 8px;
        font-size: 13px;
        color: var(--secondary-text-color);
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
        --mdc-icon-size: 16px;
      }

      .target {
        margin-left: auto;
        margin-top: 2px;
        text-align: right;
        display: flex;
        flex-direction: column;
        font-size: 12px;
        color: var(--secondary-text-color);
        min-width: 0;
      }

      .target b {
        font-size: 18px;
        font-weight: 500;
        color: var(--primary-text-color);
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
      }

      .grow {
        flex: 1;
        min-height: 0;
      }

      .slot {
        position: relative;
        z-index: 1;
        height: 28px;
        flex: none;
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
        overflow: hidden;
        /* tap targets of the chips may reach outside the row */
        overflow: clip;
        overflow-clip-margin: 10px;
      }

      .calm {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        min-width: 0;
        font-size: 12px;
        color: var(--secondary-text-color);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        --mdc-icon-size: 15px;
        font-variant-numeric: tabular-nums;
      }

      .calm ha-icon {
        flex: none;
        display: inline-flex;
      }

      .calm span {
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .bottom {
        position: relative;
        z-index: 1;
        flex: none;
        height: 40px;
      }

      @media (pointer: coarse) {
        .bottom {
          height: 44px;
        }
      }

      .ctlrow {
        height: 100%;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 0 12px;
        border-radius: 10px;
        background: var(--rs-fill);
        font-size: 13px;
        color: var(--secondary-text-color);
        --mdc-icon-size: 18px;
        min-width: 0;
      }

      .ctlrow span {
        flex: 1;
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .ctlrow ha-icon {
        flex: none;
        display: inline-flex;
      }

      button.setup {
        flex: none;
        height: 32px;
        padding: 0 14px;
        border-radius: 16px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color, transparent);
        color: var(--primary-color);
        font: inherit;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        position: relative;
        z-index: 1;
      }

      button.setup:hover {
        background: var(--rs-fill-primary);
      }

      button.setup:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      @media (pointer: coarse) {
        button.setup {
          height: 40px;
        }
      }

      .emptybody {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 10px;
        text-align: center;
      }

      .emptychip {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        border: 1.5px dashed var(--disabled-text-color, var(--secondary-text-color));
        color: var(--disabled-text-color, var(--secondary-text-color));
        display: grid;
        place-items: center;
        --mdc-icon-size: 24px;
      }

      .emptytitle {
        font-weight: 500;
      }

      .emptysub {
        font-size: 13px;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }
    `,
  ];

  disconnectedCallback(): void {
    super.disconnectedCallback();
    clearTimeout(this._errorTimer);
  }

  protected willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("config") && this._pending) {
      const actual = quickValueOf(this.config?.live);
      if (actual === this._pending.value || Date.now() - this._pending.since > PENDING_TIMEOUT_MS) {
        this._pending = null;
      }
    }
  }

  private get _lang(): string {
    return this.hass.language;
  }

  private _kind(): RoomKind {
    return roomKind(this.config, this.climateEntityCount);
  }

  render() {
    if (!this.hass || !this.area) return nothing;
    const kind = this._kind();
    const name = this.config?.display_name || this.area.name;
    const icon = this.area.icon || "mdi:texture-box";

    if (kind === "unconfigured" || kind === "empty") {
      return html`<ha-card ?inert=${this.preview}>
        <div class="inner">
          <div class="head">
            <ha-icon class="ricon" .icon=${icon}></ha-icon>
            <h3>${this._link(name)}</h3>
          </div>
          ${this._renderEmpty(kind)}
        </div>
      </ha-card>`;
    }

    const live = this.config?.live;
    const controlled =
      kind === "controlled" && isRoomControlled(this.config, this.climateControlActive);
    const st =
      kind === "controlled" ? roomStateInfo(this.config!, this.climateControlActive) : null;
    const curveColor =
      controlled && live?.mode === "heating" && !live.window_open
        ? "var(--rs-heat)"
        : controlled && live?.mode === "cooling" && !live.window_open
          ? "var(--rs-cool)"
          : "var(--secondary-text-color)";

    return html`<ha-card ?inert=${this.preview} style="--c: ${curveColor}">
      ${this._renderCurve(curveColor !== "var(--secondary-text-color)")}
      <div class="inner">
        <div class="head">
          <ha-icon class="ricon" .icon=${icon}></ha-icon>
          <h3>${this._link(name)}</h3>
          ${
            st
              ? html`<span class="state ${st.tone}">
                  <ha-icon .icon=${st.icon}></ha-icon>${localize(st.key, this._lang)}${
                    st.power != null ? ` · ${formatPercent(st.power, this.hass)}` : ""
                  }
                </span>`
              : kind === "outdoor"
                ? html`<span class="state">
                    <ha-icon icon="mdi:tree"></ha-icon>${localize("card.outdoor", this._lang)}
                  </span>`
                : nothing
          }
        </div>
        ${this._renderTemps(kind)}
        <div class="grow"></div>
        ${this._renderSlot(kind)}
        <div class="bottom">${this._renderBottom(kind, controlled)}</div>
      </div>
      <div class="sr-only" aria-live="polite">${this._error}</div>
    </ha-card>`;
  }

  private _link(name: string) {
    if (this.preview) return html`<span>${name}</span>`;
    return html`<a
      class="open"
      href="/roommind/room/${encodeURIComponent(this.area.area_id)}"
      @click=${this._onOpen}
      >${name}</a
    >`;
  }

  private _renderCurve(active: boolean) {
    const points = this.config?.live?.recent_temps;
    if (points !== this._sparkFor) {
      this._sparkFor = points;
      this._spark = buildSparkline(points, { width: CURVE_W, height: CURVE_H, padK: 1.2 });
    }
    const s = this._spark;
    if (!s) return nothing;
    return html`<svg
      class="bg"
      viewBox="0 0 ${CURVE_W} ${CURVE_H}"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      ${svg`<defs>
        <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--c)" stop-opacity=${active ? 0.2 : 0.12}></stop>
          <stop offset="1" stop-color="var(--c)" stop-opacity="0"></stop>
        </linearGradient>
      </defs>
      <path d=${s.area} fill="url(#fade)"></path>
      ${
        s.target
          ? svg`<path d=${s.target} fill="none" stroke="var(--secondary-text-color)" stroke-width="1"
              stroke-dasharray="3 3" opacity="0.45" vector-effect="non-scaling-stroke"></path>`
          : nothing
      }
      <path d=${s.line} fill="none" stroke="var(--c)" stroke-width="1.5" stroke-opacity="0.55"
        stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>`}
    </svg>`;
  }

  private _renderTemps(kind: RoomKind) {
    const live = this.config?.live;
    const unit = tempUnit(this.hass);
    const temp = live?.current_temp;
    const hum = live?.current_humidity;
    return html`<div class="temps">
      ${
        temp != null
          ? html`<span class="now"
              >${formatTempLocale(temp, this.hass)}<small>${unit}</small></span
            >`
          : html`<span class="now none">--</span>`
      }
      ${
        hum != null
          ? html`<span
              class="hum"
              aria-label=${localize("card.humidity", this._lang, { value: hum.toFixed(0) })}
              ><ha-icon icon="mdi:water-percent" aria-hidden="true"></ha-icon>${formatPercent(
                hum,
                this.hass,
              )}</span
            >`
          : nothing
      }
      ${kind === "controlled" ? this._renderTarget(live!) : nothing}
    </div>`;
  }

  private _renderTarget(live: RoomLiveData) {
    if (live.target_temp == null && live.heat_target == null) return nothing;
    const climateMode = this.config?.climate_mode ?? "auto";
    const unit = tempUnit(this.hass);
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const band =
      climateMode === "auto" &&
      live.heat_target != null &&
      live.cool_target != null &&
      live.heat_target !== live.cool_target;
    const value = band
      ? `${fmt(live.heat_target!)}–${fmt(live.cool_target!)} ${unit}`
      : `${fmt((live.target_temp ?? live.heat_target)!)} ${unit}`;
    return html`<span class="target">
      <span>${localize("card.target", this._lang)}</span><b>${value}</b>
    </span>`;
  }

  private _hints(kind: RoomKind): RoomHint[] {
    const hints = roomHints(this.config, kind, {
      climateControlActive: this.climateControlActive,
      controlMode: this.controlMode,
      language: this._lang,
      displayDelta: (d) => toDisplayDelta(d, this.hass),
      unit: tempUnit(this.hass),
    });
    // The bottom row already says the room is not controlled.
    return hints.filter((h) => h.id !== "not_controlled");
  }

  private _renderSlot(kind: RoomKind) {
    const l = this._lang;
    const items = this._hints(kind).map((h) => ({
      icon: h.icon,
      text: hintText(h, l),
      variant: h.severity === "info" ? "default" : h.severity,
    }));
    if (this._error)
      items.unshift({ icon: "mdi:alert-circle-outline", text: this._error, variant: "error" });

    if (!items.length) return html`<div class="slot">${this._renderCalm(kind)}</div>`;

    const [first, ...rest] = items;
    const shown = rest.length > MAX_ICON_HINTS ? rest.slice(0, MAX_ICON_HINTS - 1) : rest;
    const folded = rest.slice(shown.length);
    return html`<div class="slot">
      <rs-hint-chip
        .icon=${first.icon}
        .text=${first.text}
        .variant=${first.variant}
      ></rs-hint-chip>
      ${shown.map(
        (h) =>
          html`<rs-hint-chip
            icon-only
            .icon=${h.icon}
            .text=${h.text}
            .variant=${h.variant}
          ></rs-hint-chip>`,
      )}
      ${
        folded.length
          ? html`<rs-hint-chip
              icon-only
              .short=${`+${folded.length}`}
              .text=${folded.map((h) => h.text).join(" · ")}
            ></rs-hint-chip>`
          : nothing
      }
    </div>`;
  }

  private _renderCalm(kind: RoomKind) {
    const l = this._lang;
    if (kind === "outdoor" || kind === "sensor") {
      const range = this._range();
      return range
        ? html`<span class="calm"
            ><ha-icon icon="mdi:arrow-expand-vertical"></ha-icon
            ><span>${localize("card.range_recent", l, range)}</span></span
          >`
        : nothing;
    }
    if (mpcStatus(this.config, this.controlMode) === "active") {
      return html`<span class="calm"
        ><ha-icon icon="mdi:brain"></ha-icon><span>${localize("card.mpc_active", l)}</span></span
      >`;
    }
    return nothing;
  }

  /** Min/max of the recent temperatures, formatted; null with fewer than two readings. */
  private _range(): { min: string; max: string } | null {
    const temps = (this.config?.live?.recent_temps ?? [])
      .map((p) => p[1])
      .filter((t): t is number => t != null && Number.isFinite(t));
    if (temps.length < 2) return null;
    const unit = tempUnit(this.hass);
    return {
      min: formatTempLocale(Math.min(...temps), this.hass),
      max: `${formatTempLocale(Math.max(...temps), this.hass)} ${unit}`,
    };
  }

  private _renderBottom(kind: RoomKind, controlled: boolean) {
    const l = this._lang;
    if (kind === "waiting") {
      return this._ctlRow("mdi:timer-sand", localize("card.waiting", l));
    }
    if (kind === "outdoor")
      return this._ctlRow("mdi:eye-outline", localize("card.measure_only", l));
    if (kind === "sensor") {
      return this._ctlRow(
        "mdi:eye-outline",
        localize("card.measure_only", l),
        this.climateEntityCount > 0 ? this._setupButton() : nothing,
      );
    }
    if (!controlled) {
      return this._ctlRow(
        "mdi:power-off",
        localize(
          this.climateControlActive ? "card.control_off_room" : "card.control_off_global",
          l,
        ),
      );
    }
    return html`<rs-segmented
      .label=${localize("card.quick_label", l, { name: this.config?.display_name || this.area.name })}
      .options=${this._quickOptions()}
      .value=${this._pending ? this._pending.value : quickValueOf(this.config?.live)}
      @value-changed=${this._onQuick}
    ></rs-segmented>`;
  }

  private _ctlRow(icon: string, text: string, trailing: unknown = nothing) {
    return html`<div class="ctlrow">
      <ha-icon .icon=${icon} aria-hidden="true"></ha-icon><span>${text}</span>${trailing}
    </div>`;
  }

  private _setupButton() {
    return html`<button type="button" class="setup" @click=${this._onOpen}>
      ${localize("card.set_up", this._lang)}
    </button>`;
  }

  private _quickOptions(): RsSegmentOption[] {
    const l = this._lang;
    const hasSchedule = (this.config?.schedules ?? []).some((s) => !!s.entity_id);
    const first: TranslationKey = hasSchedule ? "card.quick.schedule" : "card.quick.normal";
    return [
      {
        value: "schedule",
        label: localize(first, l),
        icon: hasSchedule ? "mdi:calendar-clock" : "mdi:home-thermometer-outline",
      },
      { value: "comfort", label: localize("override.comfort", l), icon: "mdi:sofa" },
      { value: "eco", label: localize("override.eco", l), icon: "mdi:leaf" },
    ];
  }

  private _renderEmpty(kind: "unconfigured" | "empty") {
    const l = this._lang;
    if (kind === "empty") {
      return html`<div class="emptybody">
        <span class="emptychip" aria-hidden="true"><ha-icon icon="mdi:help"></ha-icon></span>
        <div>
          <div class="emptytitle">${localize("card.no_climate", l)}</div>
          <div class="emptysub">${localize("card.no_climate_hint", l)}</div>
        </div>
      </div>`;
    }
    const ce = this.climateEntityCount;
    const ts = this.tempSensorCount;
    const found =
      `${ce} ${localize(ce !== 1 ? "card.climate_devices" : "card.climate_device", l)}` +
      (ts > 0
        ? ` · ${ts} ${localize(ts !== 1 ? "card.temp_sensors" : "card.temp_sensor", l)}`
        : "");
    return html`<div class="emptybody">
      <span class="emptychip" aria-hidden="true"><ha-icon icon="mdi:plus"></ha-icon></span>
      <div>
        <div class="emptytitle">${localize("card.not_set_up", l)}</div>
        <div class="emptysub">${found}</div>
      </div>
      ${this._setupButton()}
    </div>`;
  }

  private _onOpen(e: MouseEvent) {
    // Ctrl/Cmd/middle click keep the browser's "open in new tab".
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("area-selected", {
        detail: { areaId: this.area.area_id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private async _onQuick(e: CustomEvent<{ value: QuickValue }>) {
    e.stopPropagation();
    const value = e.detail.value;
    const config = this.config;
    if (!config) return;
    this._pending = { value, since: Date.now() };
    this._setError("");
    try {
      if (value === "schedule") {
        await this.hass.callWS({ type: "roommind/override/clear", area_id: config.area_id });
      } else {
        await this.hass.callWS(
          overrideSetMessage(
            config.area_id,
            value === "comfort" ? "boost" : "eco",
            QUICK_OVERRIDE_FALLBACK_H,
            config.climate_mode ?? "auto",
            { heat: 0, cool: 0 },
            true,
          ),
        );
      }
      this.dispatchEvent(new CustomEvent("room-updated", { bubbles: true, composed: true }));
    } catch {
      this._pending = null;
      this._setError(
        localize(value === "schedule" ? "override.error_clear" : "override.error_set", this._lang),
      );
    }
  }

  private _setError(text: string) {
    clearTimeout(this._errorTimer);
    this._error = text;
    if (text) {
      this._errorTimer = setTimeout(() => {
        this._error = "";
      }, ERROR_VISIBLE_MS);
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-card": RsRoomCard;
  }
}

import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import type { ClimateMode, HomeAssistant, OverrideType, RoomConfig } from "../types";
import { localize, uiLanguage, type TranslationKey } from "../utils/localize";
import { errorText } from "../utils/errors";
import { getModeClass, roomKind, roomStateInfo, scheduleNextChange } from "../utils/room-state";
import { formatHours, formatMinutes, formatPercent, formatRemaining } from "../utils/format";
import { modeStyles } from "../styles/shared-mode-styles";
import { tokens } from "../styles/tokens";
import {
  formatTempLocale,
  tempUnit,
  toCelsius,
  toDisplay,
  usesFahrenheit,
} from "../utils/temperature";
import { MAX_TARGET_TEMP_C, MIN_TARGET_TEMP_C } from "../utils/temperature";
import {
  OVERRIDE_DURATIONS_H,
  QUICK_OVERRIDE_FALLBACK_H,
  isInvalidBand,
  overrideBand,
  overrideSetMessage,
  quickMessage,
  quickOptions,
  type QuickValue,
  type RoomTemps,
} from "../utils/override";
import { refreshRooms, setFeedHass, subscribeRooms, type RoomsFeed } from "./rooms-feed";

export interface RoomCardConfig {
  type: string;
  area?: string;
  compact?: boolean;
  hide_override?: boolean;
  hide_mode?: boolean;
  hide_climate_control?: boolean;
  hide_temperatures?: boolean;
}

interface OverrideView {
  type: OverrideType | null;
  until: number | null;
}

const TEMPS_SAVE_DELAY_MS = 800;

const OVERRIDE_KEYS: Record<OverrideType, TranslationKey> = {
  boost: "override.comfort",
  eco: "override.eco",
  custom: "override.custom",
};

/** Quick choice value of an override type; custom is the card's extra option. */
const QUICK_OF: Record<OverrideType, QuickValue | "custom"> = {
  boost: "comfort",
  eco: "eco",
  custom: "custom",
};

const CLIMATE_MODES: { value: ClimateMode; icon: string; key: TranslationKey }[] = [
  { value: "auto", icon: "mdi:autorenew", key: "mode.auto" },
  { value: "heat_only", icon: "mdi:fire", key: "mode.heat_only" },
  { value: "cool_only", icon: "mdi:snowflake", key: "mode.cool_only" },
];

export class RoomMindRoomCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: RoomCardConfig;
  @state() private _feed: RoomsFeed | null = null;
  @state() private _feedError = "";
  @state() private _now = Date.now() / 1000;
  @state() private _pending: OverrideType | null = null;
  @state() private _customHeat = 21;
  @state() private _customCool = 24;
  @state() private _optimisticOverride: OverrideView | null = null;
  @state() private _modeDraft: ClimateMode | null = null;
  @state() private _controlDraft: boolean | null = null;
  @state() private _tempsDraft: RoomTemps | null = null;
  @state() private _error = "";

  private _unsubscribe?: () => void;
  private _clock?: ReturnType<typeof setInterval>;
  private _tempsTimer?: ReturnType<typeof setTimeout>;
  private _tempsEdit = 0;

  public static getConfigForm() {
    return {
      schema: [
        { name: "area", required: true, selector: { area: {} } },
        { name: "compact", selector: { boolean: {} } },
        { name: "hide_override", selector: { boolean: {} } },
        { name: "hide_mode", selector: { boolean: {} } },
        { name: "hide_climate_control", selector: { boolean: {} } },
        { name: "hide_temperatures", selector: { boolean: {} } },
      ],
      computeLabel: (schema: { name: string }) =>
        localize(`roomcard.editor.${schema.name}` as TranslationKey, uiLanguage()),
    };
  }

  public static getStubConfig(hass?: HomeAssistant): RoomCardConfig {
    const own = Object.values(hass?.entities ?? {}).find(
      (e) => e.platform === "roommind" && e.entity_id.startsWith("climate.") && e.area_id,
    );
    return {
      type: "custom:roommind-room-card",
      area: own?.area_id ?? Object.keys(hass?.areas ?? {})[0] ?? "",
    };
  }

  public setConfig(config: RoomCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    if (config.area !== this._config?.area) {
      this._flushTemps();
      this._resetDrafts();
    }
    this._config = config;
  }

  public getCardSize(): number {
    const c = this._config;
    if (c?.compact) {
      const controls =
        this._shown(c.hide_override) ||
        this._shown(c.hide_mode) ||
        this._shown(c.hide_climate_control);
      return 2 + (controls ? 1 : 0) + (this._shown(c.hide_temperatures) ? 2 : 0);
    }
    return (
      3 +
      (this._shown(c?.hide_override) ? 2 : 0) +
      (this._shown(c?.hide_mode) ? 2 : this._shown(c?.hide_climate_control) ? 1 : 0) +
      (this._shown(c?.hide_temperatures) ? 3 : 0)
    );
  }

  public getGridOptions() {
    // Without compact, below 9 columns the labelled buttons and steppers get too narrow.
    return this._config?.compact ? { columns: 6, min_columns: 6 } : { columns: 12, min_columns: 9 };
  }

  connectedCallback(): void {
    super.connectedCallback();
    if (this.hass) setFeedHass(this.hass);
    this._unsubscribe = subscribeRooms((feed, error) => {
      this._feed = feed;
      this._feedError = error;
    });
    this._clock = setInterval(() => (this._now = Date.now() / 1000), 30_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._unsubscribe?.();
    this._unsubscribe = undefined;
    if (this._clock) clearInterval(this._clock);
    this._clock = undefined;
    this._flushTemps();
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("hass") && this.hass) setFeedHass(this.hass);
  }

  private _shown(hidden: boolean | undefined): boolean {
    return hidden !== true;
  }

  private get _lang(): string {
    return this.hass?.language ?? "en";
  }

  private get _room(): RoomConfig | undefined {
    const area = this._config?.area;
    return area ? this._feed?.rooms[area] : undefined;
  }

  private _climateMode(room: RoomConfig): ClimateMode {
    return this._modeDraft ?? room.climate_mode ?? "auto";
  }

  private _temps(room: RoomConfig): RoomTemps {
    return (
      this._tempsDraft ?? {
        comfortHeat: room.comfort_heat ?? room.comfort_temp ?? 21,
        comfortCool: room.comfort_cool ?? 24,
        ecoHeat: room.eco_heat ?? room.eco_temp ?? 17,
        ecoCool: room.eco_cool ?? 27,
      }
    );
  }

  private _override(room: RoomConfig): OverrideView {
    if (this._optimisticOverride) return this._optimisticOverride;
    const live = room.live;
    if (live?.override_active && live.override_type) {
      return { type: live.override_type, until: live.override_until };
    }
    return { type: null, until: null };
  }

  private _resetDrafts(): void {
    this._pending = null;
    this._optimisticOverride = null;
    this._modeDraft = null;
    this._controlDraft = null;
    this._tempsDraft = null;
    this._error = "";
  }

  // ---- Rendering ----

  render() {
    if (!this._config || !this.hass) return nothing;
    const area = this._config.area;
    if (!area) return this._renderMessage(localize("roomcard.no_area", this._lang));
    if (!this._feed) {
      return this._renderMessage(
        this._feedError || localize("roomcard.loading", this._lang),
        this._feedError ? "error" : "",
      );
    }
    const room = this._room;
    const kind = room ? roomKind(room, 0) : "empty";
    if (room && (kind === "outdoor" || kind === "sensor")) return this._renderMonitorOnly(room);
    if (!room || (room.devices?.length ?? 0) === 0) {
      return this._renderMessage(localize("roomcard.unknown_room", this._lang), "", true);
    }
    const live = room.live;
    const mode = live?.mode;
    const controlled =
      (this._controlDraft ?? room.climate_control_enabled !== false) &&
      this._feed.climate_control_active;

    return html`
      <ha-card class=${this._config.compact ? "compact" : ""}>
        <div class="accent ${mode ? getModeClass(mode) : "mode-other"}"></div>
        <div class="content">
          ${this._renderHeader(room)}
          ${
            live
              ? this._renderStatus(room, controlled)
              : html` <div class="hint">${localize("card.waiting", this._lang)}</div> `
          }
          <div class="controls">
            ${this._shown(this._config.hide_override) ? this._renderOverride(room) : nothing}
            ${this._renderMode(room)}
          </div>
          ${this._shown(this._config.hide_temperatures) ? this._renderTemps(room) : nothing}
          <div class="error" role="status" aria-live="polite">${this._error}</div>
        </div>
      </ha-card>
    `;
  }

  /** Outdoor areas are monitored only: readings, no controls. */
  private _renderMonitorOnly(room: RoomConfig) {
    const live = room.live;
    const l = this._lang;
    return html`
      <ha-card class=${this._config?.compact ? "compact" : ""}>
        <div class="content">
          <div class="header">
            ${this._renderName(room.area_id, room)}
            <span class="mode-pill mode-other"
              >${localize(room.is_outdoor ? "card.outdoor" : "card.measure_only", l)}</span
            >
          </div>
          <div class="temps">
            <span class="current">
              ${live?.current_temp != null ? formatTempLocale(live.current_temp, this.hass) : "--"}<span
                class="unit"
                >${tempUnit(this.hass)}</span
              >
            </span>
            ${
              live?.current_humidity != null
                ? html`<div class="target-block">
                    ${localize("card.humidity", l, {
                      value: formatPercent(live.current_humidity, { language: l }),
                    })}
                  </div>`
                : nothing
            }
          </div>
        </div>
      </ha-card>
    `;
  }

  private _renderMessage(text: string, cls = "", link = false) {
    return html`
      <ha-card class=${this._config?.compact ? "compact" : ""}>
        <div class="content">
          ${
            this._config?.area
              ? html`<div class="header">${this._renderName(this._config.area, undefined)}</div>`
              : nothing
          }
          <div class="hint ${cls}">${text}</div>
          ${
            link
              ? html`<a class="open-link" href=${this._roomPath()} @click=${this._openRoom}
                  >${localize("roomcard.open_room", this._lang)}</a
                >`
              : nothing
          }
        </div>
      </ha-card>
    `;
  }

  private _roomPath(): string {
    return `/roommind/room/${encodeURIComponent(this._config?.area ?? "")}`;
  }

  private _renderName(area: string, room: RoomConfig | undefined) {
    const name = room?.display_name || this.hass.areas?.[area]?.name || area;
    return html`<a class="name" href=${this._roomPath()} @click=${this._openRoom}>${name}</a>`;
  }

  private _renderHeader(room: RoomConfig) {
    const live = room.live;
    // Same state words as the panel's room card; a pending switch shows at once
    const st = live
      ? roomStateInfo(
          { ...room, climate_control_enabled: this._controlDraft ?? room.climate_control_enabled },
          this._feed?.climate_control_active ?? true,
        )
      : null;
    const cls =
      st?.tone === "heat" ? "mode-heating" : st?.tone === "cool" ? "mode-cooling" : "mode-idle";
    return html`
      <div class="header">
        ${this._renderName(room.area_id, room)}
        ${
          st
            ? html`<span class="mode-pill ${cls}">
                <span class="mode-dot"></span>
                ${localize(st.key, this._lang)}${
                  st.power != null ? ` · ${formatPercent(st.power, { language: this._lang })}` : ""
                }
              </span>`
            : nothing
        }
      </div>
    `;
  }

  private _renderStatus(room: RoomConfig, controlled: boolean) {
    const live = room.live!;
    const l = this._lang;
    const ov = this._override(room);
    const showRange =
      this._climateMode(room) === "auto" &&
      live.heat_target != null &&
      live.cool_target != null &&
      live.heat_target !== live.cool_target;
    const single = live.target_temp ?? live.heat_target ?? live.cool_target;
    const unit = tempUnit(this.hass);
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const paused = !this._optimisticOverride && !!live.override_suppressed;
    let remaining = "";
    if (paused) {
      remaining = localize("roomcard.paused", l);
    } else if (ov.type) {
      remaining = ov.until
        ? localize("hero.remaining", l, {
            time: formatRemaining(ov.until, l, this._now) || formatMinutes(0, l),
          })
        : localize("hero.permanent", l);
    }
    return html`
      <div class="temps">
        <span class="current">
          ${live.current_temp != null ? formatTempLocale(live.current_temp, this.hass) : "--"}<span
            class="unit"
            >${unit}</span
          >
        </span>
        <div class="target-block">
          ${
            single != null || showRange
              ? html`<span class="target">
                  ${localize("card.target", l)}
                  <strong
                    >${
                      showRange
                        ? `${fmt(live.heat_target!)}–${fmt(live.cool_target!)}`
                        : fmt(single!)
                    }
                    ${unit}</strong
                  >
                </span>`
              : nothing
          }
          <span class="icons">
            ${
              live.window_open
                ? html`<ha-icon
                    icon="mdi:window-open-variant"
                    role="img"
                    title=${localize("card.window_open", l)}
                    aria-label=${localize("card.window_open", l)}
                  ></ha-icon>`
                : nothing
            }
            ${
              live.presence_away
                ? html`<ha-icon
                    icon="mdi:home-off-outline"
                    role="img"
                    title=${localize("card.presence_away", l)}
                    aria-label=${localize("card.presence_away", l)}
                  ></ha-icon>`
                : nothing
            }
            ${
              live.current_humidity != null
                ? html`<span class="humidity"
                    >${localize("card.humidity", l, {
                      value: formatPercent(live.current_humidity, { language: l }),
                    })}</span
                  >`
                : nothing
            }
          </span>
        </div>
      </div>
      ${
        ov.type
          ? html`<div class="override-status ${paused ? "paused" : ov.type}">
              <ha-icon
                icon=${paused ? "mdi:pause-circle-outline" : "mdi:timer-outline"}
                aria-hidden="true"
              ></ha-icon>
              <span>${localize(OVERRIDE_KEYS[ov.type], l)} · ${remaining}</span>
            </div>`
          : nothing
      }
      ${
        controlled
          ? nothing
          : html`<div class="hint">
              ${localize(
                this._feed?.climate_control_active === false
                  ? "card.control_off_global"
                  : "card.control_off_room",
                l,
              )}
            </div>`
      }
    `;
  }

  /**
   * The panel card's quick choice (schedule/normal, comfort, eco until the next schedule
   * change) plus custom with a duration. A running override never locks the other options.
   */
  private _renderOverride(room: RoomConfig) {
    const l = this._lang;
    const active = this._override(room).type;
    const climateMode = this._climateMode(room);
    const selected: QuickValue | "custom" | null = this._pending
      ? "custom"
      : active
        ? QUICK_OF[active]
        : "schedule";
    const options = [
      ...quickOptions(room, l),
      { value: "custom" as const, label: localize("override.custom", l), icon: "mdi:thermometer" },
    ];
    return html`
      <section class="override-section ${this._pending ? "expanded" : ""}">
        <h4 id="ov-label">${localize("detail.override.label", l)}</h4>
        <div class="segments" role="group" aria-labelledby="ov-label">
          ${options.map(
            (o) => html`
              <button
                class="segment ${o.value} ${selected === o.value ? "active" : ""}"
                aria-pressed=${selected === o.value}
                @click=${() => this._onQuickChoice(room, o.value)}
              >
                <ha-icon icon=${o.icon} aria-hidden="true"></ha-icon>
                <span>${o.label}</span>
              </button>
            `,
          )}
        </div>
        ${
          this._pending
            ? html`
                <div class="custom-row">
                  ${
                    climateMode !== "cool_only"
                      ? this._customField(
                          climateMode === "auto" ? "override.heat_to" : "override.target",
                          this._customHeat,
                          (v) => {
                            this._customHeat = v;
                            if (climateMode === "auto" && this._customCool < v)
                              this._customCool = v;
                          },
                        )
                      : nothing
                  }
                  ${
                    climateMode !== "heat_only"
                      ? this._customField(
                          climateMode === "auto" ? "override.cool_above" : "override.target",
                          this._customCool,
                          (v) => {
                            this._customCool = v;
                            if (climateMode === "auto" && this._customHeat > v)
                              this._customHeat = v;
                          },
                        )
                      : nothing
                  }
                </div>
                <div class="duration">
                  <span>${localize("detail.override.duration", l)}</span>
                  ${OVERRIDE_DURATIONS_H.map(
                    (hours) =>
                      html`<button class="chip" @click=${() => this._activate(room, hours)}>
                        ${formatHours(hours, l)}
                      </button>`,
                  )}
                </div>
              `
            : nothing
        }
      </section>
    `;
  }

  private _renderMode(room: RoomConfig) {
    const showModes = this._shown(this._config?.hide_mode);
    const showSwitch = this._shown(this._config?.hide_climate_control);
    if (!showModes && !showSwitch) return nothing;
    const l = this._lang;
    const current = this._climateMode(room);
    const enabled = this._controlDraft ?? room.climate_control_enabled !== false;
    const head = html`<div class="section-head">
      ${showModes ? html`<h4>${localize("roomcard.mode", l)}</h4>` : html`<span></span>`}
      ${
        showSwitch
          ? html`<button
              class="switch"
              role="switch"
              aria-checked=${enabled ? "true" : "false"}
              aria-label=${localize("room.climate_control_toggle", l)}
              @click=${() => this._saveRoom({ climate_control_enabled: !enabled }, "control")}
            >
              <ha-icon class="switch-icon" icon="mdi:power" aria-hidden="true"></ha-icon>
              <span class="switch-label">${localize("room.climate_control_toggle", l)}</span>
              <span class="track"><span class="thumb"></span></span>
            </button>`
          : nothing
      }
    </div>`;
    const segments = showModes
      ? html`<div class="segments">
          ${CLIMATE_MODES.map(
            (m) => html`
              <button
                class="segment ${current === m.value ? "active" : ""}"
                aria-pressed=${current === m.value}
                aria-label=${localize(m.key, l)}
                @click=${() =>
                  current !== m.value && this._saveRoom({ climate_mode: m.value }, "mode")}
              >
                <ha-icon icon=${m.icon}></ha-icon>
                <span>${localize(m.key, l)}</span>
              </button>
            `,
          )}
        </div>`
      : nothing;
    // Compact shows the switch after the mode buttons; keep the tab order the same.
    return html`
      <section class="mode-section">
        ${this._config?.compact ? html`${segments}${head}` : html`${head}${segments}`}
      </section>
    `;
  }

  private _renderTemps(room: RoomConfig) {
    const l = this._lang;
    const mode = this._climateMode(room);
    const t = this._temps(room);
    const auto = mode === "auto";
    const heat = localize("mode.heating", l);
    const cool = localize("mode.cooling", l);
    const row = (labelKey: TranslationKey, heatKey: keyof RoomTemps, coolKey: keyof RoomTemps) => {
      const label = localize(labelKey, l);
      return html`
        <span class="row-label">${label}</span>
        ${
          mode !== "cool_only"
            ? this._stepper(
                auto ? `${label} ${heat}` : label,
                t[heatKey],
                (v) => this._editTemps(room, heatKey, v),
                auto ? "mdi:fire" : undefined,
              )
            : nothing
        }
        ${
          mode !== "heat_only"
            ? this._stepper(
                auto ? `${label} ${cool}` : label,
                t[coolKey],
                (v) => this._editTemps(room, coolKey, v),
                auto ? "mdi:snowflake" : undefined,
              )
            : nothing
        }
      `;
    };
    return html`
      <section class="temps-section">
        <h4>${localize("roomcard.temperatures", l)}</h4>
        <div class="temp-grid ${auto ? "auto" : "single"}">
          ${
            auto
              ? html`
                  <span class="corner"></span>
                  <span class="col-head"><ha-icon icon="mdi:fire"></ha-icon>${heat}</span>
                  <span class="col-head"><ha-icon icon="mdi:snowflake"></ha-icon>${cool}</span>
                `
              : nothing
          }
          ${row("override.comfort", "comfortHeat", "comfortCool")}
          ${row("override.eco", "ecoHeat", "ecoCool")}
        </div>
      </section>
    `;
  }

  private _customField(key: TranslationKey, valueC: number, onChange: (v: number) => void) {
    const label = localize(key, this._lang).replace(/:\s*$/, "");
    return html`
      <div class="custom-field">
        <span class="field-label">${label}</span>
        ${this._stepper(label, valueC, onChange)}
      </div>
    `;
  }

  private _stepper(
    label: string,
    valueC: number,
    onChange: (v: number) => void,
    sideIcon?: string,
  ) {
    const l = this._lang;
    return html`
      <div class="stepper" role="group" aria-label=${label}>
        <button
          class="step"
          aria-label=${localize("roomcard.lower", l, { name: label })}
          ?disabled=${valueC <= MIN_TARGET_TEMP_C}
          @click=${() => onChange(this._step(valueC, -1))}
        >
          <ha-icon icon="mdi:minus"></ha-icon>
        </button>
        <span class="value" aria-live="polite"
          >${
            sideIcon
              ? html`<ha-icon class="side-icon" icon=${sideIcon} aria-hidden="true"></ha-icon>`
              : nothing
          }${formatTempLocale(valueC, this.hass, 0, 1)}
          ${tempUnit(this.hass)}</span
        >
        <button
          class="step"
          aria-label=${localize("roomcard.raise", l, { name: label })}
          ?disabled=${valueC >= MAX_TARGET_TEMP_C}
          @click=${() => onChange(this._step(valueC, 1))}
        >
          <ha-icon icon="mdi:plus"></ha-icon>
        </button>
      </div>
    `;
  }

  /** One display step (0.5 °C / 1 °F) from the value, snapped to the step grid. */
  private _step(valueC: number, dir: 1 | -1): number {
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const grid = toDisplay(valueC, this.hass) / step;
    // A value off the grid (set elsewhere, unit conversion) moves to the next grid point.
    const index = dir > 0 ? Math.floor(grid + 1e-6) + 1 : Math.ceil(grid - 1e-6) - 1;
    const next = toCelsius(index * step, this.hass);
    return Math.min(MAX_TARGET_TEMP_C, Math.max(MIN_TARGET_TEMP_C, next));
  }

  // ---- Actions ----

  private _openRoom(e: MouseEvent): void {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    history.pushState(null, "", this._roomPath());
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  private _onQuickChoice(room: RoomConfig, value: QuickValue | "custom"): void {
    this._error = "";
    if (value === "custom") {
      // A second tap puts the custom form away again
      if (this._pending) {
        this._pending = null;
        return;
      }
      this._pending = "custom";
      const ov = room.live;
      const t = this._temps(room);
      this._customHeat =
        ov?.override_type === "custom" && ov.override_heat != null
          ? ov.override_heat
          : t.comfortHeat;
      this._customCool =
        ov?.override_type === "custom" && ov.override_cool != null
          ? ov.override_cool
          : t.comfortCool;
      return;
    }
    this._pending = null;
    void this._quick(room, value);
  }

  private async _quick(room: RoomConfig, value: QuickValue): Promise<void> {
    const now = Date.now() / 1000;
    const next = scheduleNextChange(room, this.hass.states);
    this._optimisticOverride =
      value === "schedule"
        ? { type: null, until: null }
        : {
            type: value === "comfort" ? "boost" : "eco",
            until: next != null && next > now ? next : now + QUICK_OVERRIDE_FALLBACK_H * 3600,
          };
    try {
      // Comfort/eco take the stored targets on the server: flush a pending stepper edit first
      if (this._tempsTimer) {
        clearTimeout(this._tempsTimer);
        await this._saveTemps();
      }
      await this.hass.callWS(quickMessage(room, value));
      await refreshRooms(true);
    } catch (err) {
      this._error = this._message(
        err,
        value === "schedule" ? "override.error_clear" : "override.error_set",
      );
    }
    this._optimisticOverride = null;
  }

  private async _activate(room: RoomConfig, hours: number): Promise<void> {
    const type = this._pending;
    if (!type) return;
    const mode = this._climateMode(room);
    const custom = { heat: this._customHeat, cool: this._customCool };
    const band = overrideBand(type, mode, this._temps(room), custom);
    if (isInvalidBand(band.heat, band.cool)) {
      this._error = localize("override.invalid_band", this._lang);
      return;
    }
    this._pending = null;
    this._error = "";
    this._optimisticOverride = { type, until: Date.now() / 1000 + hours * 3600 };
    void this._refocusPreset(type);
    try {
      // Comfort/eco take the stored targets on the server: a stepper edit still waiting
      // for its debounce would otherwise not apply to this override.
      if (this._tempsTimer) {
        clearTimeout(this._tempsTimer);
        await this._saveTemps();
      }
      await this.hass.callWS(overrideSetMessage(room.area_id, type, hours, mode, custom));
      await refreshRooms(true);
    } catch (err) {
      this._error = this._message(err, "override.error_set");
    }
    this._optimisticOverride = null;
  }

  /** The duration chip that had the focus is gone after activating; hand it to the preset. */
  private async _refocusPreset(type: OverrideType): Promise<void> {
    const root = this.shadowRoot;
    const hadFocus = !!root?.activeElement;
    await this.updateComplete;
    if (hadFocus && !root?.activeElement) {
      root
        ?.querySelector<HTMLButtonElement>(`.override-section .segment.${QUICK_OF[type]}`)
        ?.focus();
    }
  }

  private async _saveRoom(
    changes: { climate_mode?: ClimateMode; climate_control_enabled?: boolean },
    draft: "mode" | "control",
  ): Promise<void> {
    if (!this._config?.area) return;
    this._error = "";
    if (draft === "mode") this._modeDraft = changes.climate_mode!;
    else this._controlDraft = changes.climate_control_enabled!;
    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: this._config.area,
        ...changes,
      });
      await refreshRooms(true);
    } catch (err) {
      this._error = this._message(err, "roomcard.error_save");
    }
    if (draft === "mode") this._modeDraft = null;
    else this._controlDraft = null;
  }

  private _editTemps(room: RoomConfig, key: keyof RoomTemps, value: number): void {
    const next = { ...this._temps(room), [key]: value };
    // Same rule as the panel, in every mode: a later switch to auto must not find the
    // cooling target below the heating target.
    if (key === "comfortHeat" && next.comfortCool < value) next.comfortCool = value;
    if (key === "comfortCool" && next.comfortHeat > value) next.comfortHeat = value;
    if (key === "ecoHeat" && next.ecoCool < value) next.ecoCool = value;
    if (key === "ecoCool" && next.ecoHeat > value) next.ecoHeat = value;
    this._tempsDraft = next;
    this._tempsEdit += 1;
    if (this._tempsTimer) clearTimeout(this._tempsTimer);
    this._tempsTimer = setTimeout(() => void this._saveTemps(), TEMPS_SAVE_DELAY_MS);
  }

  private _flushTemps(): void {
    if (!this._tempsTimer) return;
    clearTimeout(this._tempsTimer);
    void this._saveTemps();
  }

  private async _saveTemps(): Promise<void> {
    this._tempsTimer = undefined;
    const t = this._tempsDraft;
    const area = this._config?.area;
    if (!t || !area) return;
    const edit = this._tempsEdit;
    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: area,
        comfort_heat: t.comfortHeat,
        comfort_cool: t.comfortCool,
        eco_heat: t.ecoHeat,
        eco_cool: t.ecoCool,
      });
      await refreshRooms(true);
    } catch (err) {
      this._error = this._message(err, "roomcard.error_save");
    }
    if (edit === this._tempsEdit) this._tempsDraft = null;
  }

  private _message(err: unknown, fallback: TranslationKey): string {
    return errorText(err, localize(fallback, this._lang), this._lang);
  }

  static styles = [
    tokens,
    modeStyles,
    css`
      :host {
        display: block;
      }

      ha-card {
        position: relative;
        overflow: hidden;
        height: 100%;
        box-sizing: border-box;
        container-type: inline-size;
      }

      .accent {
        position: absolute;
        inset: 0 auto 0 0;
        width: 4px;
      }

      .accent.mode-heating {
        background: var(--rs-heat);
      }

      .accent.mode-cooling {
        background: var(--rs-cool);
      }

      .accent.mode-idle,
      .accent.mode-other {
        background: var(--disabled-text-color, #bdbdbd);
      }

      .content {
        padding: 16px 16px 12px 20px;
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        min-width: 0;
      }

      .name {
        font-size: 16px;
        font-weight: 500;
        color: var(--primary-text-color);
        text-decoration: none;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        min-width: 0;
        min-height: 44px;
        line-height: 44px;
      }

      .name:hover {
        text-decoration: underline;
      }

      .mode-pill {
        flex-shrink: 0;
        gap: 5px;
        font-size: 12px;
        padding: 3px 10px;
        border-radius: 12px;
      }

      .mode-dot {
        width: 7px;
        height: 7px;
      }

      .temps {
        display: flex;
        align-items: flex-end;
        gap: 12px;
        flex-wrap: wrap;
      }

      .current {
        font-size: 40px;
        font-weight: 300;
        line-height: 1;
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .unit {
        font-size: 18px;
        color: var(--secondary-text-color);
        margin-left: 2px;
      }

      .target-block {
        display: flex;
        flex-direction: column;
        gap: 2px;
        font-size: 13px;
        color: var(--secondary-text-color);
        padding-bottom: 3px;
      }

      .target strong {
        font-weight: 500;
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .icons {
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .icons ha-icon {
        --mdc-icon-size: 16px;
      }

      .override-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-top: 12px;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 13px;
        font-variant-numeric: tabular-nums;
      }

      .override-status ha-icon {
        --mdc-icon-size: 16px;
      }

      .override-status.paused {
        color: var(--secondary-text-color);
        background: rgba(var(--rgb-primary-text-color, 0, 0, 0), 0.06);
      }

      .override-status.boost {
        color: var(--warning-color);
        background: color-mix(in srgb, var(--warning-color) 12%, transparent);
      }

      .override-status.eco {
        color: var(--success-color);
        background: color-mix(in srgb, var(--success-color) 12%, transparent);
      }

      .override-status.custom {
        color: var(--rs-cool);
        background: color-mix(in srgb, var(--rs-cool) 12%, transparent);
      }

      .hint {
        margin-top: 10px;
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .hint.error,
      .error {
        color: var(--error-color);
        font-size: 13px;
      }

      .error:not(:empty) {
        margin-top: 10px;
      }

      .open-link {
        display: inline-flex;
        align-items: center;
        min-height: 44px;
        color: var(--primary-color);
        font-size: 14px;
      }

      section {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }

      h4 {
        margin: 0 0 8px;
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .section-head {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 4px;
      }

      .section-head h4 {
        margin: 0;
      }

      button {
        font: inherit;
        color: inherit;
        touch-action: manipulation;
      }

      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      /* one row, as many equal columns as options (quick choice has 3 or 4) */
      .segments {
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: minmax(0, 1fr);
        gap: 8px;
      }

      .segment {
        min-height: 56px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 2px;
        padding: 6px 4px;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 10px;
        background: transparent;
        color: var(--primary-text-color);
        font-size: 12px;
        line-height: 1.2;
        text-align: center;
        cursor: pointer;
        min-width: 0;
        overflow-wrap: break-word;
        hyphens: auto;
        transition:
          background-color 0.15s,
          border-color 0.15s;
      }

      .segment ha-icon {
        --mdc-icon-size: 18px;
        flex-shrink: 0;
      }

      .segment:hover:not(:disabled) {
        background: rgba(var(--rgb-primary-text-color, 0, 0, 0), 0.04);
      }

      .segment:disabled {
        opacity: 0.4;
        cursor: default;
      }

      .segment.active,
      .segment.pending {
        border-color: var(--primary-color);
        background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
        color: var(--primary-color);
      }

      /* Picked but not running yet: must not look like the active climate mode. */
      .segment.pending {
        border-style: dashed;
        background: transparent;
      }

      .segment.active.boost {
        border-color: var(--warning-color);
        background: color-mix(in srgb, var(--warning-color) 15%, transparent);
        color: var(--warning-color);
      }

      .segment.active.eco {
        border-color: var(--success-color);
        background: color-mix(in srgb, var(--success-color) 15%, transparent);
        color: var(--success-color);
      }

      .segment.active.custom {
        border-color: var(--rs-cool);
        background: color-mix(in srgb, var(--rs-cool) 15%, transparent);
        color: var(--rs-cool);
      }

      .custom-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 8px 12px;
        margin-top: 10px;
      }

      .custom-field {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .field-label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .duration {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .chip {
        min-width: 56px;
        min-height: 44px;
        border-radius: 22px;
        border: 1px solid var(--primary-color);
        background: transparent;
        color: var(--primary-color);
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
      }

      .chip:hover {
        background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
      }

      .switch {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        min-height: 44px;
        padding: 0;
        border: none;
        background: transparent;
        cursor: pointer;
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .track {
        position: relative;
        width: 36px;
        height: 20px;
        border-radius: 10px;
        background: var(--disabled-text-color, #bdbdbd);
        transition: background-color 0.15s;
        flex-shrink: 0;
      }

      .thumb {
        position: absolute;
        top: 2px;
        left: 2px;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: var(--card-background-color, #fff);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
        transition: transform 0.15s;
      }

      .switch[aria-checked="true"] .track {
        background: var(--primary-color);
      }

      .switch[aria-checked="true"] .thumb {
        transform: translateX(16px);
      }

      .temp-grid {
        display: grid;
        align-items: center;
        gap: 8px 12px;
      }

      .temp-grid.single {
        grid-template-columns: 1fr auto;
      }

      .temp-grid.auto {
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      }

      .temp-grid.auto .corner {
        display: none;
      }

      .temp-grid.auto .row-label {
        grid-column: 1 / -1;
        margin-bottom: -4px;
      }

      @container (max-width: 339px) {
        .temp-grid.auto {
          grid-template-columns: minmax(0, 1fr);
        }

        .temp-grid.auto .col-head {
          display: none;
        }

        .temp-grid.auto .side-icon {
          display: inline-block;
        }
      }

      @container (max-width: 259px) {
        .temp-grid.single {
          grid-template-columns: minmax(0, 1fr);
        }
      }

      .col-head {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .col-head ha-icon {
        --mdc-icon-size: 14px;
      }

      @container (min-width: 440px) {
        .temp-grid.auto {
          grid-template-columns: auto 1fr 1fr;
        }

        .temp-grid.auto .corner {
          display: block;
        }

        .temp-grid.auto .row-label {
          grid-column: auto;
          margin-bottom: 0;
        }
      }

      .row-label {
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .stepper {
        min-width: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 22px;
      }

      .step {
        width: 44px;
        height: 44px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: 50%;
        background: transparent;
        color: var(--primary-text-color);
        cursor: pointer;
      }

      .step ha-icon {
        --mdc-icon-size: 18px;
      }

      .step:hover:not(:disabled) {
        background: rgba(var(--rgb-primary-text-color, 0, 0, 0), 0.06);
      }

      .step:disabled {
        opacity: 0.35;
        cursor: default;
      }

      .side-icon {
        display: none;
        --mdc-icon-size: 14px;
        margin-right: 2px;
        color: var(--secondary-text-color);
      }

      .value {
        flex: 1;
        min-width: 48px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        white-space: nowrap;
        text-align: center;
        font-size: 15px;
        font-variant-numeric: tabular-nums;
        color: var(--primary-text-color);
      }

      .switch-icon {
        display: none;
        --mdc-icon-size: 18px;
      }

      /* Compact: one status block, icon-only controls side by side. */
      .compact .content {
        padding: 10px 12px 8px 16px;
      }

      .compact .name {
        font-size: 15px;
        line-height: 1.25;
        white-space: normal;
        overflow-wrap: break-word;
        flex-shrink: 0;
        max-width: 100%;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        padding: 13px 0;
        min-height: 0;
      }

      .compact .header {
        flex-wrap: wrap;
        row-gap: 4px;
      }

      .compact .current {
        font-size: 28px;
      }

      .compact .unit {
        font-size: 14px;
      }

      .compact .override-status {
        margin-top: 6px;
      }

      .compact h4,
      .compact .switch-label,
      .compact .segment span {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
        white-space: nowrap;
      }

      .compact .switch-icon {
        display: inline-block;
      }

      .compact .controls {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0 16px;
      }

      .compact .controls section {
        flex: 0 1 auto;
        margin-top: 8px;
        padding-top: 0;
        border-top: none;
      }

      .compact .controls section.expanded {
        flex-basis: 100%;
      }

      .compact .mode-section {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px 12px;
      }

      .compact .mode-section .section-head {
        margin: 0;
      }

      .compact .segments {
        grid-auto-columns: 44px;
        justify-content: start;
        gap: 6px;
      }

      .compact .segment {
        min-height: 44px;
        padding: 0;
      }

      .compact .chip {
        min-width: 44px;
      }

      .compact .temps-section {
        margin-top: 8px;
        padding-top: 8px;
      }

      @media (prefers-reduced-motion: reduce) {
        .segment,
        .track,
        .thumb {
          transition: none;
        }
      }
    `,
  ];
}

const TAG = "roommind-room-card";

// HA swaps window.customElements for a scoped-registry polyfill while it starts, and extra
// modules load in parallel with it: a define before that lands in the replaced registry and
// the dashboard never finds the card. HA defines <home-assistant> after the swap.
// The get() guard covers a manually added Lovelace resource loading the bundle twice.
void customElements.whenDefined("home-assistant").then(() => {
  if (!window.customElements.get(TAG)) window.customElements.define(TAG, RoomMindRoomCard);
});

declare global {
  interface HTMLElementTagNameMap {
    "roommind-room-card": RoomMindRoomCard;
  }
}

import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import type { ClimateMode, HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { errorText } from "../../utils/errors";
import { showToast } from "../../utils/toast";
import { tokens } from "../../styles/tokens";
import { floatingStyles } from "../../styles/floating-styles";
import { inputStyles } from "../../styles/input-styles";
import { fireSaveStatus } from "../../utils/events";
import { formatNumber } from "../../utils/format";
import { hideFromTopLayer, positionNear, showInTopLayer } from "../../utils/popover";
import { formatTempLocale, tempUnit, toDisplay, usesFahrenheit } from "../../utils/temperature";
import {
  DAY_GROUPS,
  blockTemps,
  clearDay,
  copyDay,
  createBlock,
  emptyWeek,
  hm,
  neededSides,
  nowInZone,
  removeBlock,
  roundToStep,
  serializeWeek,
  setBlockTimes,
  splitOverMidnight,
  suggestBlock,
  usesComfort,
  withTemps,
  type ScheduleBlock,
  type Week,
} from "../../utils/schedule-week";
import {
  deleteSchedule,
  isAdmin,
  loadSchedule,
  saveSchedule,
  type LoadedSchedule,
} from "../../utils/schedule-api";
import type { BlockLook, RsWeekGrid } from "./rs-week-grid";
import type { BlockTempChange } from "./rs-block-form";
import type { RsMenuItem } from "../shared/rs-menu";
import "./rs-week-grid";
import "./rs-block-form";
import "../shared/rs-confirm-dialog";
import "../shared/rs-list-card";
import "../shared/rs-list-row";
import "../shared/rs-menu";
import "../shared/rs-pill";
import "../shared/rs-icon-button";
import "../shared/rs-edit-dialog";

/** Debounce of the auto-save; a drag or a few stepper taps end up in one update. */
const SAVE_DELAY_MS = 800;
const MOBILE_MAX = 600;

interface UsingRoom {
  id: string;
  name: string;
  icon: string;
  mode: ClimateMode;
  config: RoomConfig;
}

type Dialog = { kind: "copy"; day: number; targets: number[] } | { kind: "delete" } | null;

interface OpenBlock {
  day: number;
  index: number;
  /** Changes only when another block is opened, so the form keeps its draft. */
  key: string;
}

/**
 * Full-page editor of one Home Assistant schedule helper. Storage helpers (admin) are edited
 * and saved on every change (debounced, only valid states, one update in flight); YAML
 * helpers and non-admins see the same week read-only. Fires `schedule-closed` (composed) after
 * the helper was deleted or removed from the room, so the panel goes back.
 */
@customElement("rs-schedule-editor")
export class RsScheduleEditor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public entityId = "";
  /** Room the editor was opened from ("" for a deep link without room). */
  @property({ type: String }) public roomId = "";
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: String }) public scheduleOffAction: "eco" | "off" = "eco";

  @state() private _loaded: LoadedSchedule | null = null;
  @state() private _loadError = "";
  /** The helper has no state in Home Assistant (deleted or a stale link). */
  @state() private _missing = false;
  @state() private _week: Week = emptyWeek();
  private _savedName = "";
  @state() private _name = "";
  @state() private _mobile = false;
  @state() private _open: OpenBlock | null = null;
  @state() private _dialog: Dialog = null;
  @state() private _now = { day: -1, minute: -1 };
  @state() private _saveError = "";
  @state() private _busy = false;
  @state() private _dialogError = "";

  @query("rs-week-grid") private _grid?: RsWeekGrid;

  private _savedJson = "";
  private _timer?: ReturnType<typeof setTimeout>;
  private _inFlight = false;
  private _again = false;
  private _loadToken = 0;
  private _openSeq = 0;
  private _clock?: ReturnType<typeof setInterval>;
  private _resize?: ResizeObserver;
  private _returnFocus: HTMLElement | null = null;
  private _focusedKey = "";
  private _popResize?: ResizeObserver;

  static styles = [
    tokens,
    floatingStyles,
    inputStyles,
    css`
      :host {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
      }

      .notice {
        display: flex;
        gap: var(--rs-space-3);
        align-items: flex-start;
        padding: var(--rs-space-3) var(--rs-space-4);
        border-radius: var(--rs-radius);
        background: var(--rs-fill);
        font-size: var(--rs-font-md);
        line-height: 1.45;
      }

      .notice ha-icon {
        --mdc-icon-size: 20px;
        color: var(--primary-color);
        flex: none;
      }

      .notice.warn ha-icon {
        color: var(--rs-warn);
      }

      .notice.error ha-icon {
        color: var(--rs-err);
      }

      ha-card.head {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--rs-space-3) var(--rs-space-4);
        padding: var(--rs-space-4);
      }

      .head-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: var(--rs-fill);
        color: var(--secondary-text-color);
        flex: none;
        --mdc-icon-size: 24px;
      }

      .name {
        flex: 1 1 260px;
        min-width: 0;
      }

      .name-error {
        margin-top: var(--rs-space-1);
        font-size: var(--rs-font-sm);
        color: var(--rs-err);
      }

      .name-text {
        font-size: var(--rs-font-xl);
        overflow-wrap: anywhere;
      }

      .meta {
        flex: 1 1 260px;
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-2);
        min-width: 0;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      code {
        font-size: var(--rs-font-sm);
        overflow-wrap: anywhere;
      }

      .users {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .card-body {
        padding: 0 var(--rs-space-4) var(--rs-space-3);
      }

      .hint {
        margin: 0 0 var(--rs-space-3);
        font-size: var(--rs-font-sm);
        line-height: 1.45;
        color: var(--secondary-text-color);
      }

      .legend {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-2) var(--rs-space-4);
        margin-top: var(--rs-space-4);
        font-size: var(--rs-font-sm);
        line-height: 1.45;
        color: var(--secondary-text-color);
      }

      .legend span {
        display: inline-flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .legend b {
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .swatch {
        width: 22px;
        height: 12px;
        border-radius: 3px;
        flex: none;
        border: 1px solid color-mix(in srgb, var(--swatch) 55%, transparent);
        background: color-mix(in srgb, var(--swatch) var(--swatch-tint), var(--rs-surface));
      }

      .legend .lines {
        flex-basis: 100%;
        display: block;
      }

      .strip {
        position: relative;
        height: 6px;
        border-radius: 3px;
        background: var(--rs-fill);
        overflow: hidden;
      }

      .strip i {
        position: absolute;
        top: 0;
        bottom: 0;
        background: color-mix(in srgb, var(--strip-color, var(--rs-heat)) 55%, transparent);
      }

      .strip .now {
        background: var(--primary-text-color);
        width: 2px;
      }

      .day-strip {
        margin: var(--rs-space-1) var(--rs-space-4) var(--rs-space-2);
        height: 8px;
        border-radius: 4px;
      }

      .today-chip {
        font-size: var(--rs-font-sm);
        color: var(--primary-color);
      }

      .days {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
      }

      .empty-day {
        padding: var(--rs-space-2) var(--rs-space-4);
        font-size: var(--rs-font-md);
        color: var(--secondary-text-color);
      }

      .pop {
        width: min(340px, calc(100vw - 16px));
        max-height: calc(100vh - 16px);
        overflow-y: auto;
        padding: var(--rs-space-3) var(--rs-space-4) var(--rs-space-4);
      }

      .pop:popover-open {
        padding: var(--rs-space-3) var(--rs-space-4) var(--rs-space-4);
        overflow-y: auto;
      }

      .pop-head {
        display: flex;
        align-items: flex-start;
        gap: var(--rs-space-2);
        margin-bottom: var(--rs-space-3);
      }

      .pop-head div {
        flex: 1;
        min-width: 0;
      }

      .pop-head b {
        display: block;
        font-weight: 500;
        font-size: var(--rs-font-lg);
      }

      .pop-head small {
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .confirm p {
        margin: 0 0 var(--rs-space-3);
        line-height: 1.5;
      }

      .confirm .muted {
        color: var(--secondary-text-color);
        font-size: var(--rs-font-md);
      }

      .confirm .error {
        color: var(--rs-err);
      }

      .actions {
        display: flex;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        margin-top: var(--rs-space-4);
      }

      .actions .grow {
        flex: 1;
      }

      .presets {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        margin-bottom: var(--rs-space-3);
      }

      .presets button {
        min-height: 36px;
        padding: 0 var(--rs-space-3);
        border: 1px solid var(--rs-border);
        border-radius: 18px;
        background: none;
        color: var(--primary-text-color);
        font: inherit;
        font-size: var(--rs-font-md);
        cursor: pointer;
      }

      @media (pointer: coarse) {
        .presets button {
          min-height: var(--rs-touch);
          border-radius: calc(var(--rs-touch) / 2);
        }
      }

      .presets button:hover {
        background: var(--rs-fill);
      }

      .presets button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      .day-check {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
        min-height: var(--rs-touch);
        padding: var(--rs-space-1) 0;
        border-top: 1px solid var(--rs-border);
        cursor: pointer;
      }

      .day-check input {
        width: 20px;
        height: 20px;
        margin: 0 2px;
        accent-color: var(--primary-color);
        flex: none;
      }

      .day-check span {
        flex: 1;
        display: flex;
        flex-direction: column;
        min-width: 0;
      }

      .day-check small {
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
      }

      .day-check .strip {
        width: 96px;
        flex: none;
      }

      .day-check.source {
        cursor: default;
      }

      .day-check.source ha-icon {
        --mdc-icon-size: 20px;
        width: 24px;
        color: var(--secondary-text-color);
      }

      @media (max-width: 600px) {
        .day-check .strip {
          display: none;
        }
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    this._tick();
    this._clock = setInterval(() => this._tick(), 30_000);
    this._resize ??= new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) this._mobile = width <= MOBILE_MAX;
    });
    this._resize.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._clock) clearInterval(this._clock);
    this._resize?.disconnect();
    this._removePopListeners();
    // Leaving within the debounce: send the change instead of dropping it.
    if (this._timer) void this._flush();
  }

  /** Sends a pending change now (the panel calls it before navigating away). */
  public flush(): Promise<void> {
    return this._flush();
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("entityId") && this.entityId) void this._load();
    // A helper created a moment ago may get its state after the registry entry
    else if (this._missing && changed.has("hass") && this.hass.states[this.entityId])
      void this._load();
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has("_open") || changed.has("_mobile")) this._placePopover();
  }

  private _tick() {
    this._now = nowInZone(this.hass?.config?.time_zone);
  }

  // ─── Data ───────────────────────────────────────────────────────────

  private async _load() {
    const token = ++this._loadToken;
    this._loaded = null;
    this._loadError = "";
    this._open = null;
    this._missing = !this.hass.states[this.entityId];
    if (this._missing) return;
    try {
      const data = await loadSchedule(this.hass, this.entityId);
      if (token !== this._loadToken) return;
      this._loaded = data;
      this._week = data.week;
      this._name = data.name;
      this._savedName = data.name;
      this._savedJson = this._payloadJson();
    } catch (err) {
      if (token !== this._loadToken) return;
      this._loadError = errorText(
        err,
        localize("error.unknown", this.hass.language),
        this.hass.language,
      );
    }
  }

  private get _canEdit(): boolean {
    return !!this._loaded?.itemId && isAdmin(this.hass);
  }

  /** An emptied name field keeps the last saved name, so block changes are still saved. */
  private get _effectiveName(): string {
    return this._name.trim() || this._savedName;
  }

  private _payloadJson(): string {
    return JSON.stringify({ name: this._effectiveName, week: serializeWeek(this._week) });
  }

  private _change(week: Week) {
    this._week = week;
    if (this._open && !this._week[this._open.day]?.[this._open.index]) this._closeBlock();
    this._scheduleSave();
  }

  private _scheduleSave() {
    if (this._timer) clearTimeout(this._timer);
    this._timer = setTimeout(() => void this._flush(), SAVE_DELAY_MS);
  }

  private async _flush(): Promise<void> {
    if (this._timer) clearTimeout(this._timer);
    this._timer = undefined;
    const loaded = this._loaded;
    if (!loaded?.itemId || !this._canEdit || !this._effectiveName) return;
    if (this._inFlight) {
      this._again = true;
      return;
    }
    const json = this._payloadJson();
    if (json === this._savedJson) return;
    this._inFlight = true;
    fireSaveStatus(this, "saving");
    try {
      const name = this._effectiveName;
      await saveSchedule(this.hass, loaded.itemId, name, loaded.icon, this._week);
      this._savedJson = json;
      this._savedName = name;
      this._saveError = "";
      fireSaveStatus(this, "saved");
    } catch (err) {
      this._saveError = errorText(
        err,
        localize("error.unknown", this.hass.language),
        this.hass.language,
      );
      fireSaveStatus(this, "error");
    } finally {
      this._inFlight = false;
      if (this._again) {
        this._again = false;
        void this._flush();
      }
    }
  }

  // ─── Rooms using the schedule ───────────────────────────────────────

  private _roomName(id: string): string {
    return this.rooms[id]?.display_name || this.hass.areas?.[id]?.name || id;
  }

  private _users(): UsingRoom[] {
    return Object.values(this.rooms)
      .filter((r) => (r.schedules ?? []).some((s) => s.entity_id === this.entityId))
      .map((r) => ({
        id: r.area_id,
        name: this._roomName(r.area_id),
        icon: this.hass.areas?.[r.area_id]?.icon || "mdi:texture-box",
        mode: r.climate_mode ?? "auto",
        config: r,
      }));
  }

  /** Rooms whose climate mode decides the temperature keys: users, else the room it came from. */
  private _modeRooms(users: UsingRoom[]): RoomConfig[] {
    if (users.length) return users.map((u) => u.config);
    const own = this.rooms[this.roomId];
    return own ? [own] : [];
  }

  private _band(room: RoomConfig, level: "comfort" | "eco"): string {
    const heat =
      level === "comfort"
        ? (room.comfort_heat ?? room.comfort_temp ?? 21)
        : (room.eco_heat ?? room.eco_temp ?? 17);
    const cool = level === "comfort" ? (room.comfort_cool ?? 24) : (room.eco_cool ?? 27);
    const fmt = (c: number) => formatTempLocale(c, this.hass, 0, 1);
    const unit = tempUnit(this.hass);
    if (room.climate_mode === "heat_only") return `${fmt(heat)} ${unit}`;
    if (room.climate_mode === "cool_only") return `${fmt(cool)} ${unit}`;
    return `${fmt(heat)}–${fmt(cool)} ${unit}`;
  }

  private _bandList(rooms: RoomConfig[], level: "comfort" | "eco"): string {
    if (rooms.length === 1) return this._band(rooms[0], level);
    return rooms.map((r) => `${this._roomName(r.area_id)} ${this._band(r, level)}`).join(", ");
  }

  // ─── Look ───────────────────────────────────────────────────────────

  private _dayNames(style: "long" | "short"): string[] {
    const fmt = new Intl.DateTimeFormat(this.hass.language, { weekday: style, timeZone: "UTC" });
    // 2024-01-01 was a Monday.
    return [0, 1, 2, 3, 4, 5, 6].map((d) => fmt.format(new Date(Date.UTC(2024, 0, 1 + d))));
  }

  private _temp(v: number): string {
    return formatNumber(v, this.hass, 0, 1);
  }

  /** Text of a block's temperature: "Komfort", "21–24 °C" (long) or "21–24°" (short). */
  private _tempText(block: ScheduleBlock, long: boolean): string {
    const l = this.hass.language;
    if (usesComfort(block)) return localize("override.comfort", l);
    const t = blockTemps(block);
    const unit = long ? ` ${tempUnit(this.hass)}` : "°";
    if (t.heat !== undefined && t.cool !== undefined) {
      return `${this._temp(t.heat)}–${this._temp(t.cool)}${unit}`;
    }
    const v = t.heat ?? t.cool ?? t.single;
    return v === undefined ? localize("override.comfort", l) : `${this._temp(v)}${unit}`;
  }

  private _lookFactory(rooms: RoomConfig[]) {
    const coolOnly = rooms.length > 0 && rooms.every((r) => r.climate_mode === "cool_only");
    const ref = rooms[0];
    const refHeat = toDisplay(ref?.comfort_heat ?? ref?.comfort_temp ?? 21, this.hass);
    const refCool = toDisplay(ref?.comfort_cool ?? 24, this.hass);
    // Tint per kelvin; °F steps are 5/9 K.
    const perUnit = usesFahrenheit(this.hass) ? 7 * (5 / 9) : 7;
    const days = this._dayNames("long");
    return (block: ScheduleBlock, day: number): BlockLook => {
      const t = blockTemps(block);
      const comfort = usesComfort(block);
      let color = coolOnly ? "var(--rs-cool)" : "var(--rs-heat)";
      let tint = 22;
      if (!comfort) {
        if (t.heat !== undefined || t.single !== undefined) {
          const v = (t.heat ?? t.single) as number;
          tint = 22 + (v - refHeat) * perUnit;
        } else if (t.cool !== undefined) {
          color = "var(--rs-cool)";
          tint = 22 + (refCool - t.cool) * perUnit;
        }
      }
      return {
        label: this._tempText(block, false),
        short: comfort ? "" : this._tempText(block, false),
        description: `${days[day]} ${hm(block.start)}–${hm(block.end)}, ${this._tempText(block, true)}`,
        color,
        tint: Math.round(Math.max(10, Math.min(45, tint))),
      };
    };
  }

  // ─── Render ─────────────────────────────────────────────────────────

  render() {
    const l = this.hass.language;
    if (this._missing) {
      return html`<div class="notice" role="status">
        <ha-icon icon="mdi:calendar-remove-outline" aria-hidden="true"></ha-icon>
        <span>${localize("schedule_editor.not_found", l, { entity: this.entityId })}</span>
      </div>`;
    }
    if (this._loadError) {
      return html`<div class="notice error" role="alert">
        <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
        <span>${localize("schedule_editor.load_error", l, { error: this._loadError })}</span>
      </div>`;
    }
    if (!this._loaded) {
      return html`<div class="notice"><span>${localize("panel.loading", l)}</span></div>`;
    }
    const users = this._users();
    const modeRooms = this._modeRooms(users);
    const look = this._lookFactory(modeRooms);
    const editable = this._canEdit;
    return html`
      ${this._renderNotices(users, editable)} ${this._renderHead(users, editable)}
      ${
        this._mobile
          ? html`${this._renderLegendCard(modeRooms)}
              <div class="days">
                ${this._week.map((_, d) => this._renderDayCard(d, look, editable))}
              </div>`
          : this._renderWeekCard(look, modeRooms, editable)
      }
      ${editable ? this._renderDeleteRow(users) : nothing} ${this._renderBlockEditor(modeRooms)}
      ${this._renderDialog(users)}
    `;
  }

  private _renderNotices(users: UsingRoom[], editable: boolean) {
    const l = this.hass.language;
    const others = users.filter((u) => u.id !== this.roomId);
    return html`
      ${
        !this._loaded?.itemId
          ? html`<div class="notice">
              <ha-icon icon="mdi:file-code-outline"></ha-icon>
              <span>${localize("schedule_editor.yaml_notice", l)}</span>
            </div>`
          : !editable
            ? html`<div class="notice">
                <ha-icon icon="mdi:lock-outline"></ha-icon>
                <span>${localize("schedule_editor.admin_notice", l)}</span>
              </div>`
            : nothing
      }
      ${
        editable && others.length > 0
          ? html`<div class="notice warn">
              <ha-icon icon="mdi:account-multiple-outline"></ha-icon>
              <span
                >${localize("schedule_editor.shared_notice", l, {
                  rooms: others.map((u) => u.name).join(", "),
                })}</span
              >
            </div>`
          : nothing
      }
      ${
        this._saveError
          ? html`<div class="notice error" role="alert">
              <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
              <span>${localize("schedule_editor.save_error", l, { error: this._saveError })}</span>
            </div>`
          : nothing
      }
    `;
  }

  private _renderHead(users: UsingRoom[], editable: boolean) {
    const l = this.hass.language;
    const nameMissing = editable && !this._name.trim();
    return html`<ha-card class="head">
      <span class="head-icon" aria-hidden="true"
        ><ha-icon .icon=${this._loaded?.icon || "mdi:calendar-clock"}></ha-icon
      ></span>
      <div class="name">
        ${
          editable
            ? html`<ha-textfield
                  .label=${localize("schedule_editor.name", l)}
                  .value=${this._name}
                  required
                  .invalid=${nameMissing}
                  autocomplete="off"
                  @input=${this._onName}
                ></ha-textfield>
                ${
                  nameMissing
                    ? html`<div class="name-error" role="alert">
                        ${localize("schedule_editor.name_kept", l, { name: this._savedName })}
                      </div>`
                    : nothing
                }`
            : html`<div class="name-text">${this._name}</div>`
        }
      </div>
      <div class="meta">
        <code>${this.entityId}</code>
        <div class="users">
          ${
            users.length
              ? html`<span>${localize("schedule_editor.used_by", l)}</span>
                  ${users.map((u) => html`<rs-pill .icon=${u.icon}>${u.name}</rs-pill>`)}`
              : html`<span>${localize("schedule_editor.unused", l)}</span>`
          }
        </div>
      </div>
    </ha-card>`;
  }

  private _stripBlocks(
    day: ScheduleBlock[],
    nowMinute = -1,
    look?: (b: ScheduleBlock) => BlockLook,
  ) {
    return html`${day.map(
      (b) =>
        html`<i
          style="left:${(b.start / 1440) * 100}%;width:${((b.end - b.start) / 1440) * 100}%${
            look ? `;--strip-color:${look(b).color}` : ""
          }"
        ></i>`,
    )}${
      nowMinute >= 0 ? html`<i class="now" style="left:${(nowMinute / 1440) * 100}%"></i>` : nothing
    }`;
  }

  private _renderWeekCard(
    look: (b: ScheduleBlock, d: number) => BlockLook,
    modeRooms: RoomConfig[],
    editable: boolean,
  ) {
    const l = this.hass.language;
    return html`<rs-list-card
      .heading=${localize("schedule_editor.week", l)}
      .info=${editable ? localize("schedule_editor.keyboard_hint", l) : ""}
      unclipped
    >
      <div class="card-body">
        ${editable ? html`<p class="hint">${localize("schedule_editor.drag_hint", l)}</p>` : nothing}
        <rs-week-grid
          .hass=${this.hass}
          .week=${this._week}
          .editable=${editable}
          .nowDay=${this._now.day}
          .nowMinute=${this._now.minute}
          .look=${look}
          .dayNames=${this._dayNames("long")}
          .dayShort=${this._dayNames("short")}
          .selected=${this._open}
          @week-change=${this._onGridChange}
          @block-open=${this._onBlockOpen}
          @block-delete=${(e: CustomEvent<{ day: number; index: number }>) =>
            this._deleteBlock(e.detail.day, e.detail.index)}
          @day-action=${(e: CustomEvent<{ day: number; action: string }>) =>
            this._onDayAction(e.detail.day, e.detail.action)}
        ></rs-week-grid>
        ${this._renderLegend(modeRooms)}
      </div>
    </rs-list-card>`;
  }

  private _renderLegendCard(modeRooms: RoomConfig[]) {
    return html`<rs-list-card
      ><div class="card-body">${this._renderLegend(modeRooms)}</div></rs-list-card
    >`;
  }

  private _renderLegend(modeRooms: RoomConfig[]) {
    const l = this.hass.language;
    const coolOnly = modeRooms.length > 0 && modeRooms.every((r) => r.climate_mode === "cool_only");
    const color = coolOnly ? "var(--rs-cool)" : "var(--rs-heat)";
    const sides = neededSides(modeRooms.map((r) => r.climate_mode ?? "auto"));
    const keyNote = sides.heat && sides.cool ? "both" : sides.heat ? "heat" : "cool";
    const off = this.scheduleOffAction === "off";
    const own = this._ownTempKinds();
    return html`<div class="legend">
      <span
        ><i class="swatch" style="--swatch:${color};--swatch-tint:22%"></i
        ><b>${localize("override.comfort", l)}</b> ${
          modeRooms.length ? this._bandList(modeRooms, "comfort") : ""
        }</span
      >
      ${
        own.warm
          ? html`<span
              ><i class="swatch" style="--swatch:${color};--swatch-tint:40%"></i
              ><b>${localize("schedule_editor.own_title", l)}</b>
              ${localize("schedule_editor.own_legend", l)}</span
            >`
          : nothing
      }
      ${
        own.cool
          ? html`<span
              ><i class="swatch" style="--swatch:var(--rs-cool);--swatch-tint:40%"></i
              ><b>${localize("schedule_editor.own_title", l)}</b>
              ${localize("schedule_editor.own_legend_cool", l)}</span
            >`
          : nothing
      }
      <span
        ><i class="swatch" style="--swatch:var(--secondary-text-color);--swatch-tint:0%"></i
        ><b
          >${localize(off ? "schedule_editor.no_block_off" : "schedule_editor.no_block_eco", l)}</b
        >
        ${!off && modeRooms.length ? this._bandList(modeRooms, "eco") : ""}</span
      >
      ${
        this._canEdit
          ? html`<span class="lines"
              >${localize(`schedule_editor.keys_${keyNote}` as "schedule_editor.keys_both", l)}</span
            >`
          : nothing
      }
    </div>`;
  }

  /**
   * Which own-temperature tints the week shows (see `_lookFactory`): a heat or single value is
   * the stronger the warmer, a cool-only value the stronger the cooler.
   */
  private _ownTempKinds(): { warm: boolean; cool: boolean } {
    let warm = false;
    let cool = false;
    for (const day of this._week) {
      for (const b of day) {
        if (usesComfort(b)) continue;
        const t = blockTemps(b);
        if (t.heat !== undefined || t.single !== undefined) warm = true;
        else if (t.cool !== undefined) cool = true;
      }
    }
    return { warm, cool };
  }

  private _renderDayCard(
    day: number,
    look: (b: ScheduleBlock, d: number) => BlockLook,
    editable: boolean,
  ) {
    const l = this.hass.language;
    const names = this._dayNames("long");
    const blocks = this._week[day];
    const today = day === this._now.day;
    const items: RsMenuItem[] = [
      { value: "add", label: localize("schedule_editor.add_block", l), icon: "mdi:plus" },
      {
        value: "copy",
        label: localize("schedule_editor.copy_day", l),
        icon: "mdi:content-copy",
        disabled: blocks.length === 0,
      },
      {
        value: "clear",
        label: localize("schedule_editor.clear_day", l),
        icon: "mdi:eraser",
        disabled: blocks.length === 0,
      },
    ];
    return html`<rs-list-card .heading=${names[day]}>
      ${
        today
          ? html`<span slot="header-extras" class="today-chip"
              >${localize("schedule_editor.today", l)}</span
            >`
          : nothing
      }
      ${
        editable
          ? html`<rs-menu
              slot="header-end"
              .items=${items}
              .label=${localize("schedule_editor.day_actions", l, { day: names[day] })}
              @menu-select=${(e: CustomEvent<{ value: string }>) =>
                this._onDayAction(day, e.detail.value)}
            ></rs-menu>`
          : nothing
      }
      <div class="strip day-strip" aria-hidden="true">
        ${this._stripBlocks(blocks, today ? this._now.minute : -1, (b) => look(b, day))}
      </div>
      ${
        blocks.length === 0
          ? html`<div class="empty-day">${localize("schedule_editor.empty_day", l)}</div>`
          : nothing
      }
      ${blocks.map((b, index) => {
        const lk = look(b, day);
        return html`<rs-list-row
          ?clickable=${editable}
          ?chevron=${editable}
          icon=${usesComfort(b) ? "mdi:sofa" : "mdi:thermometer"}
          icon-color=${lk.color}
          .heading=${`${hm(b.start)}–${hm(b.end)}`}
          .value=${this._tempText(b, true)}
          data-day=${day}
          data-index=${index}
          @row-click=${(e: Event) => this._openBlock(day, index, e.currentTarget as HTMLElement)}
        ></rs-list-row>`;
      })}
      ${
        editable
          ? html`<rs-list-row
              clickable
              plain-icon
              variant="primary"
              icon="mdi:plus"
              .heading=${localize("schedule_editor.add_block", l)}
              ?disabled=${!suggestBlock(blocks)}
              @row-click=${(e: Event) => this._addBlock(day, e.currentTarget as HTMLElement)}
            ></rs-list-row>`
          : nothing
      }
    </rs-list-card>`;
  }

  private _renderDeleteRow(users: UsingRoom[]) {
    const l = this.hass.language;
    const others = users.filter((u) => u.id !== this.roomId);
    return html`<rs-list-card>
      <rs-list-row
        clickable
        variant="danger"
        icon="mdi:delete-outline"
        .heading=${localize("schedule_editor.delete", l)}
        .secondary=${
          others.length
            ? localize("schedule_editor.delete_sub_shared", l, {
                rooms: others.map((u) => u.name).join(", "),
              })
            : localize("schedule_editor.delete_sub", l)
        }
        @row-click=${() => {
          this._dialogError = "";
          this._dialog = { kind: "delete" };
        }}
      ></rs-list-row>
    </rs-list-card>`;
  }

  // ─── Block popover / sheet ──────────────────────────────────────────

  private _renderBlockEditor(modeRooms: RoomConfig[]) {
    const open = this._open;
    const block = open ? this._week[open.day]?.[open.index] : undefined;
    if (!open || !block) return nothing;
    const l = this.hass.language;
    const names = this._dayNames("long");
    const sides = neededSides(modeRooms.map((r) => r.climate_mode ?? "auto"));
    const ref = modeRooms[0];
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const defaults = {
      heat: roundToStep(toDisplay(ref?.comfort_heat ?? ref?.comfort_temp ?? 21, this.hass), step),
      cool: roundToStep(toDisplay(ref?.comfort_cool ?? 24, this.hass), step),
    };
    const comfortText = modeRooms.length ? this._bandList(modeRooms, "comfort") : "";
    const form = html`<rs-block-form
      .hass=${this.hass}
      .block=${block}
      .others=${this._week[open.day].filter((_, i) => i !== open.index)}
      .sides=${sides}
      .defaults=${defaults}
      .comfortText=${comfortText}
      .nextDayName=${names[(open.day + 1) % 7]}
      .blockKey=${open.key}
      @block-times=${this._onFormTimes}
      @block-split=${this._onFormSplit}
      @block-temps=${this._onFormTemps}
      @block-delete=${() => this._deleteBlock(open.day, open.index)}
      @block-done=${() => this._closeBlock()}
    ></rs-block-form>`;
    const range = `${hm(block.start)}–${hm(block.end)}`;
    if (this._mobile) {
      return html`<rs-edit-dialog
        open
        sheet
        .heading=${`${names[open.day]} · ${range}`}
        @rs-dialog-closed=${() => this._closeBlock()}
        >${form}</rs-edit-dialog
      >`;
    }
    return html`<div
      class="floating pop"
      role="dialog"
      aria-label=${`${names[open.day]} ${range}`}
      @keydown=${this._onPopKey}
    >
      <div class="pop-head">
        <div>
          <b>${names[open.day]}</b>
          <small>${range}</small>
        </div>
        <rs-icon-button
          size="sm"
          icon="mdi:close"
          .label=${localize("common.close", l)}
          @click=${() => this._closeBlock()}
        ></rs-icon-button>
      </div>
      ${form}
    </div>`;
  }

  private _placePopover() {
    const pop = this.renderRoot.querySelector<HTMLElement>(".pop");
    if (!pop || !this._open) {
      this._removePopListeners();
      return;
    }
    const anchor = this._grid?.blockElement(this._open.day, this._open.index);
    if (!anchor) return;
    pop.style.visibility = "hidden";
    showInTopLayer(pop);
    positionNear(anchor, pop);
    document.addEventListener("pointerdown", this._onDocPointer, true);
    // The form grows (error line, own temperatures): keep it inside the viewport.
    this._popResize ??= new ResizeObserver(() => this._onViewport(new Event("resize")));
    this._popResize.disconnect();
    this._popResize.observe(pop);
    window.addEventListener("resize", this._onViewport);
    document.addEventListener("scroll", this._onViewport, true);
    if (this._focusedKey !== this._open.key) {
      this._focusedKey = this._open.key;
      const form = pop.querySelector("rs-block-form");
      void form?.updateComplete.then(() => form.shadowRoot?.querySelector("select")?.focus());
    }
  }

  private _removePopListeners() {
    document.removeEventListener("pointerdown", this._onDocPointer, true);
    this._popResize?.disconnect();
    window.removeEventListener("resize", this._onViewport);
    document.removeEventListener("scroll", this._onViewport, true);
  }

  private _onDocPointer = (e: Event) => {
    const pop = this.renderRoot.querySelector(".pop");
    const path = e.composedPath();
    if (pop && path.includes(pop)) return;
    // A press on the open block itself is its click (closes and reopens otherwise).
    const anchor = this._open ? this._grid?.blockElement(this._open.day, this._open.index) : null;
    if (anchor && path.includes(anchor)) return;
    this._closeBlock(false);
  };

  private _onViewport = (e: Event) => {
    const pop = this.renderRoot.querySelector<HTMLElement>(".pop");
    if (!pop || !this._open) return;
    if (e.type === "scroll" && e.composedPath().includes(pop)) return;
    const anchor = this._grid?.blockElement(this._open.day, this._open.index);
    if (anchor) positionNear(anchor, pop);
  };

  private _onPopKey(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      this._closeBlock();
    }
  }

  private _openBlock(day: number, index: number, from?: HTMLElement | null) {
    this._returnFocus = from ?? null;
    this._open = { day, index, key: `${day}:${index}:${++this._openSeq}` };
  }

  private _closeBlock(refocus = true) {
    const open = this._open;
    hideFromTopLayer(this.renderRoot.querySelector<HTMLElement>(".pop"));
    this._removePopListeners();
    this._open = null;
    if (!refocus || !open) return;
    const target =
      this._grid?.blockElement(open.day, open.index) ??
      (this._returnFocus?.isConnected ? this._returnFocus : null);
    this._returnFocus = null;
    void this.updateComplete.then(() => target?.focus());
  }

  // ─── Edits ──────────────────────────────────────────────────────────

  private _onName(e: Event) {
    this._name = (e.target as HTMLInputElement).value;
    this._scheduleSave();
  }

  private _onGridChange(
    e: CustomEvent<{ week: Week; day: number; index: number; created: boolean }>,
  ) {
    if (this._open && (this._open.day !== e.detail.day || this._open.index !== e.detail.index)) {
      this._closeBlock(false);
    }
    this._change(e.detail.week);
    if (e.detail.created) {
      void this.updateComplete.then(() =>
        this._grid?.blockElement(e.detail.day, e.detail.index)?.focus(),
      );
    }
  }

  private _onBlockOpen(e: CustomEvent<{ day: number; index: number; anchor: HTMLElement }>) {
    const { day, index, anchor } = e.detail;
    if (this._open?.day === day && this._open.index === index) {
      this._closeBlock();
      return;
    }
    this._openBlock(day, index, anchor);
  }

  private _onFormTimes(e: CustomEvent<{ start: number; end: number }>) {
    const open = this._open;
    if (!open) return;
    const next = setBlockTimes(this._week, open.day, open.index, e.detail.start, e.detail.end);
    if (!next) return;
    const index = next[open.day].findIndex(
      (b) => b.start === e.detail.start && b.end === e.detail.end,
    );
    this._open = { ...open, index };
    this._change(next);
  }

  private _onFormSplit(e: CustomEvent<{ start: number; endNextDay: number }>) {
    const open = this._open;
    if (!open) return;
    const l = this.hass.language;
    const names = this._dayNames("long");
    const next = splitOverMidnight(
      this._week,
      open.day,
      open.index,
      e.detail.start,
      e.detail.endNextDay,
    );
    if (!next) {
      this._toast(localize("schedule_editor.split_blocked", l, { day: names[(open.day + 1) % 7] }));
      return;
    }
    this._closeBlock();
    this._withUndo(
      localize("schedule_editor.split_done", l, {
        day: names[open.day],
        next: names[(open.day + 1) % 7],
      }),
      next,
    );
  }

  private _onFormTemps(e: CustomEvent<{ temps: BlockTempChange | null }>) {
    const open = this._open;
    if (!open) return;
    const block = this._week[open.day][open.index];
    if (!block) return;
    const data = withTemps(block.data, e.detail.temps);
    const nextBlock: ScheduleBlock = { start: block.start, end: block.end };
    if (data) nextBlock.data = data;
    this._change(
      this._week.map((day, d) =>
        d === open.day ? day.map((b, i) => (i === open.index ? nextBlock : b)) : day,
      ),
    );
  }

  private _deleteBlock(day: number, index: number) {
    const block = this._week[day]?.[index];
    if (!block) return;
    const l = this.hass.language;
    const names = this._dayNames("short");
    const wasOpen = !!this._open;
    this._open = null;
    this._removePopListeners();
    this._withUndo(
      localize("schedule_editor.block_deleted", l, {
        day: names[day],
        range: `${hm(block.start)}–${hm(block.end)}`,
      }),
      removeBlock(this._week, day, index),
    );
    // Keep the keyboard in the grid: the neighbour block, else the day's menu.
    void this.updateComplete.then(() => {
      const target =
        this._grid?.blockElement(day, Math.min(index, this._week[day].length - 1)) ?? null;
      if (target) target.focus();
      else if (wasOpen) this._returnFocus?.focus();
    });
  }

  private _addBlock(day: number, from?: HTMLElement | null) {
    const range = suggestBlock(this._week[day]);
    if (!range) {
      this._toast(localize("schedule_editor.day_full", this.hass.language));
      return;
    }
    const created = createBlock(this._week, day, range.start, range.end);
    if (!created) return;
    this._change(created.week);
    void this.updateComplete.then(() => {
      const anchor = this._grid?.blockElement(day, created.index) ?? from ?? null;
      this._openBlock(day, created.index, anchor);
    });
  }

  private _onDayAction(day: number, action: string) {
    const l = this.hass.language;
    const names = this._dayNames("long");
    if (action === "add") this._addBlock(day);
    else if (action === "copy") {
      this._dialog = { kind: "copy", day, targets: [] };
    } else if (action === "clear") {
      this._withUndo(
        localize("schedule_editor.day_cleared", l, { day: names[day] }),
        clearDay(this._week, day),
      );
    }
  }

  private _withUndo(message: string, next: Week) {
    const before = this._week;
    this._change(next);
    this._toast(message, () => this._change(before));
  }

  private _toast(message: string, undo?: () => void) {
    showToast(this, message, this.hass.language, undo);
  }

  // ─── Dialogs ────────────────────────────────────────────────────────

  private _renderDialog(users: UsingRoom[]) {
    const dialog = this._dialog;
    if (!dialog) return nothing;
    return dialog.kind === "copy"
      ? this._renderCopyDialog(dialog)
      : this._renderDeleteDialog(users);
  }

  private _renderCopyDialog(dialog: { kind: "copy"; day: number; targets: number[] }) {
    const l = this.hass.language;
    const names = this._dayNames("long");
    const setTargets = (targets: readonly number[]) => {
      this._dialog = { ...dialog, targets: targets.filter((d) => d !== dialog.day) };
    };
    const toggle = (d: number, on: boolean) =>
      setTargets(on ? [...dialog.targets, d] : dialog.targets.filter((t) => t !== d));
    const count = dialog.targets.length;
    return html`<rs-edit-dialog
      open
      icon="mdi:content-copy"
      .heading=${localize("schedule_editor.copy_title", l, { day: names[dialog.day] })}
      @rs-dialog-closed=${() => (this._dialog = null)}
    >
      <div class="confirm">
        <p class="muted">${localize("schedule_editor.copy_body", l, { day: names[dialog.day] })}</p>
        <div class="presets">
          <button type="button" @click=${() => setTargets(DAY_GROUPS.weekdays)}>
            ${localize("schedule_editor.weekdays", l)}
          </button>
          <button type="button" @click=${() => setTargets(DAY_GROUPS.weekend)}>
            ${localize("schedule_editor.weekend", l)}
          </button>
          <button type="button" @click=${() => setTargets(DAY_GROUPS.all)}>
            ${localize("schedule_editor.all_days", l)}
          </button>
        </div>
        ${names.map((name, d) => {
          const blocks = this._week[d];
          if (d === dialog.day) {
            return html`<div class="day-check source">
              <ha-icon icon="mdi:content-copy" aria-hidden="true"></ha-icon>
              <span>${name}<small>${localize("schedule_editor.copy_source", l)}</small></span>
              <span class="strip" aria-hidden="true">${this._stripBlocks(blocks)}</span>
            </div>`;
          }
          return html`<label class="day-check">
            <input
              type="checkbox"
              .checked=${dialog.targets.includes(d)}
              @change=${(e: Event) => toggle(d, (e.target as HTMLInputElement).checked)}
            />
            <span
              >${name}<small
                >${
                  blocks.length
                    ? localize(
                        blocks.length === 1
                          ? "schedule_editor.copy_replaces_one"
                          : "schedule_editor.copy_replaces",
                        l,
                        { count: blocks.length },
                      )
                    : localize("schedule_editor.empty_day", l)
                }</small
              ></span
            >
            <span class="strip" aria-hidden="true">${this._stripBlocks(blocks)}</span>
          </label>`;
        })}
        <div class="actions">
          <ha-button appearance="plain" @click=${() => (this._dialog = null)}
            >${localize("detail.cancel", l)}</ha-button
          >
          <ha-button ?disabled=${count === 0} @click=${() => this._confirmCopy(dialog)}
            >${localize("schedule_editor.copy_confirm", l)}</ha-button
          >
        </div>
      </div>
    </rs-edit-dialog>`;
  }

  private _confirmCopy(dialog: { day: number; targets: number[] }) {
    const l = this.hass.language;
    const names = this._dayNames("long");
    this._dialog = null;
    this._withUndo(
      localize(
        dialog.targets.length === 1 ? "schedule_editor.copied_one" : "schedule_editor.copied",
        l,
        {
          day: names[dialog.day],
          count: dialog.targets.length,
        },
      ),
      copyDay(this._week, dialog.day, dialog.targets),
    );
  }

  private _renderDeleteDialog(users: UsingRoom[]) {
    const l = this.hass.language;
    const here = users.find((u) => u.id === this.roomId);
    const shifted = users.filter((u) => {
      const list = u.config.schedules ?? [];
      const idx = list.findIndex((s) => s.entity_id === this.entityId);
      return !!u.config.schedule_selector_entity && idx >= 0 && idx < list.length - 1;
    });
    return html`<rs-confirm-dialog
      open
      icon="mdi:delete-outline"
      .heading=${localize("schedule_editor.delete_title", l)}
      .message=${`${localize("schedule_editor.delete_body", l, { name: this._name })}${
        users.length
          ? ` ${localize("schedule_editor.delete_body_rooms", l, {
              rooms: users.map((u) => u.name).join(", "),
            })}`
          : ""
      }`}
      .confirmLabel=${localize("schedule_editor.delete_confirm", l)}
      .busy=${this._busy}
      .error=${this._dialogError}
      @cancel=${() => (this._dialog = null)}
      @confirm=${() => this._delete(users)}
    >
      ${
        shifted.length
          ? html`<p>
              ${localize("schedule_editor.delete_selector_note", l, {
                rooms: shifted.map((u) => u.name).join(", "),
              })}
            </p>`
          : nothing
      }
      ${
        here && users.length > 1
          ? html`<p>
              ${localize("schedule_editor.delete_only_here_hint", l, { room: here.name })}
            </p>`
          : nothing
      }
      ${
        here
          ? html`<ha-button
              slot="extra"
              appearance="plain"
              ?disabled=${this._busy}
              @click=${this._removeFromRoom}
              >${localize("schedule_editor.remove_here", l, { room: here.name })}</ha-button
            >`
          : nothing
      }
    </rs-confirm-dialog>`;
  }

  /** Partial room save: only `schedules` changes, every other field stays as stored. */
  private async _dropFromRoom(room: RoomConfig) {
    await this.hass.callWS({
      type: "roommind/rooms/save",
      area_id: room.area_id,
      schedules: (room.schedules ?? []).filter((s) => s.entity_id !== this.entityId),
    });
  }

  private _removeFromRoom = async () => {
    const room = this.rooms[this.roomId];
    if (!room) return;
    this._busy = true;
    this._dialogError = "";
    try {
      await this._flush();
      await this._dropFromRoom(room);
      this._dialog = null;
      this._closed();
    } catch (err) {
      this._dialogError = errorText(
        err,
        localize("error.unknown", this.hass.language),
        this.hass.language,
      );
    } finally {
      this._busy = false;
    }
  };

  private async _delete(users: UsingRoom[]) {
    const itemId = this._loaded?.itemId;
    if (!itemId) return;
    this._busy = true;
    this._dialogError = "";
    if (this._timer) clearTimeout(this._timer);
    this._timer = undefined;
    try {
      for (const u of users) await this._dropFromRoom(u.config);
      await deleteSchedule(this.hass, itemId);
      this._savedJson = this._payloadJson();
      this._dialog = null;
      this._closed();
    } catch (err) {
      this._dialogError = errorText(
        err,
        localize("error.unknown", this.hass.language),
        this.hass.language,
      );
    } finally {
      this._busy = false;
    }
  }

  private _closed() {
    this.dispatchEvent(new CustomEvent("schedule-closed", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-editor": RsScheduleEditor;
  }
}

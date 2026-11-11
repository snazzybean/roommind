/**
 * rs-analytics – Analytics tab orchestrator.
 * Delegates rendering to rs-analytics-toolbar, -summary, -chart, -rhythm and -model.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, AnalyticsData, AnalyticsDataPoint } from "../types";
import { localize } from "../utils/localize";
import { boostHoursLeft } from "../utils/learning";
import {
  QUICK_RANGE_DAYS,
  haTimeZone,
  isoDateInZone,
  quickRange,
  startOfDayInZone,
} from "../utils/analytics-time";
import "./analytics/rs-analytics-toolbar";
import "./analytics/rs-analytics-summary";
import "./analytics/rs-analytics-chart";
import "./analytics/rs-analytics-rhythm";
import "./analytics/rs-analytics-model";

/** What a room can show: the summary, rhythm, chart and model card use the same flags. */
function roomFlags(room: RoomConfig | undefined) {
  return {
    canHeat: room?.climate_mode !== "cool_only",
    canCool:
      room?.climate_mode !== "heat_only" && (room?.devices ?? []).some((d) => d.type === "ac"),
    hasWindowSensor: (room?.window_sensors?.length ?? 0) > 0,
    // The price only matters where it moves something
    followsPrice:
      !room?.is_outdoor && ((room?.price_shift ?? 0) > 0 || !!room?.heat_source_price_aware),
  };
}

/** Sides a room is judged on, same rule as the summary (one-sided rooms on their own side only). */
function bandSides(mode: string | undefined): "both" | "heat" | "cool" {
  if (mode === "heat_only") return "heat";
  if (mode === "cool_only") return "cool";
  return "both";
}

@customElement("rs-analytics")
export class RsAnalytics extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Object }) public rooms: Record<string, RoomConfig> = {};
  @property() public initialRoom = "";
  @property() public controlMode: "mpc" | "bangbang" = "mpc";

  @state() private _selectedRoom = "";
  // Browser midnight until hass is known, then today in HA's zone (willUpdate)
  @state() private _rangeStart: number = new Date(new Date().setHours(0, 0, 0, 0)).getTime();
  @state() private _rangeEnd: number = Date.now();
  @state() private _data: AnalyticsData | null = null;
  @state() private _chartAnchor: number = Date.now();
  @state() private _loading = false;
  @state() private _activeQuick: string | null = "24h";

  private _refreshInterval?: ReturnType<typeof setInterval>;
  private _dataRoom = "";
  private _pointsOf: AnalyticsData | null = null;
  private _pointsCache: AnalyticsDataPoint[] = [];
  private _fetchId = 0;
  private _zoneApplied = false;

  connectedCallback() {
    super.connectedCallback();
    this._refreshInterval = setInterval(() => this._silentRefresh(), 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = undefined;
    }
  }

  protected willUpdate(changedProps: Map<string, unknown>) {
    if (!this._zoneApplied && this.hass && this._activeQuick) {
      this._zoneApplied = true;
      this._applyQuickRange();
    }
    if (changedProps.has("initialRoom") && this.initialRoom) {
      this._selectedRoom = this.initialRoom;
    }
    let autoSelected = false;
    if (changedProps.has("rooms") && !this._selectedRoom) {
      const configured = Object.keys(this.rooms);
      if (configured.length > 0) {
        this._selectedRoom = configured[0];
        autoSelected = true;
        this.dispatchEvent(
          new CustomEvent("room-selected", {
            detail: { areaId: configured[0] },
            bubbles: true,
            composed: true,
          }),
        );
      }
    }
    if (
      autoSelected ||
      changedProps.has("_selectedRoom") ||
      changedProps.has("_rangeStart") ||
      changedProps.has("_rangeEnd")
    ) {
      if (this._selectedRoom) {
        this._fetchData();
      }
    }
  }

  protected render() {
    const l = this.hass.language;
    const flags = roomFlags(this.rooms[this._selectedRoom]);

    return html`
      <rs-analytics-toolbar
        .hass=${this.hass}
        .rooms=${this.rooms}
        .selectedRoom=${this._selectedRoom}
        .rangeStart=${this._rangeStart}
        .rangeEnd=${this._rangeEnd}
        .activeQuick=${this._activeQuick}
        .data=${this._data}
        .language=${l}
        @room-selected=${this._onRoomSelected}
        @range-changed=${this._onRangeChanged}
      ></rs-analytics-toolbar>
      ${
        this._selectedRoom
          ? this._loading && !this._data
            ? html`<div class="loading">${localize("panel.loading", l)}</div>`
            : html`
                ${this._renderSummary()}
                <rs-analytics-chart
                  .hass=${this.hass}
                  .data=${this._data}
                  .rangeStart=${this._rangeStart}
                  .rangeEnd=${this._rangeEnd}
                  .chartAnchor=${this._chartAnchor}
                  .language=${l}
                  .isOutdoor=${this.rooms[this._selectedRoom]?.is_outdoor ?? false}
                  .targetBand=${bandSides(this.rooms[this._selectedRoom]?.climate_mode)}
                  .showPrice=${flags.followsPrice}
                ></rs-analytics-chart>
                ${
                  !this.rooms[this._selectedRoom]?.is_outdoor
                    ? html`<rs-analytics-rhythm
                        .hass=${this.hass}
                        .rhythm=${this._data?.rhythm ?? null}
                        .rangeStart=${this._rangeStart}
                        .rangeEnd=${this._rangeEnd}
                        .language=${l}
                        .canHeat=${flags.canHeat}
                        .canCool=${flags.canCool}
                        .hasWindowSensor=${flags.hasWindowSensor}
                        @day-selected=${this._onDaySelected}
                      ></rs-analytics-rhythm>`
                    : nothing
                }
                ${
                  !this.rooms[this._selectedRoom]?.is_outdoor
                    ? html` <rs-analytics-model
                        .hass=${this.hass}
                        .data=${this._data}
                        .language=${l}
                        .controlMode=${this.controlMode}
                        .managed=${!this.rooms[this._selectedRoom]?.temperature_sensor}
                        .canHeat=${flags.canHeat}
                        .canCool=${flags.canCool}
                        .boostHours=${boostHoursLeft(
                          this.rooms[this._selectedRoom]?.live?.boost_applied_at,
                          this.rooms[this._selectedRoom]?.live?.n_observations,
                        )}
                      ></rs-analytics-model>`
                    : nothing
                }
              `
          : html`
              <div class="no-data">
                <ha-icon
                  icon="mdi:chart-line"
                  style="--mdc-icon-size: 48px; opacity: 0.4"
                ></ha-icon>
                <p>${localize("analytics.select_room", l)}</p>
              </div>
            `
      }
    `;
  }

  private _renderSummary() {
    const room = this.rooms[this._selectedRoom];
    if (!room || room.is_outdoor) return nothing;
    const flags = roomFlags(room);
    return html`<rs-analytics-summary
      .hass=${this.hass}
      .stats=${this._data?.stats ?? null}
      .points=${this._points()}
      .rangeStart=${this._rangeStart}
      .rangeEnd=${this._rangeEnd}
      .bandSides=${bandSides(room.climate_mode)}
      .canHeat=${flags.canHeat}
      .canCool=${flags.canCool}
      .hasWindowSensor=${flags.hasWindowSensor}
      .showPrice=${flags.followsPrice}
      .language=${this.hass.language}
    ></rs-analytics-summary>`;
  }

  /** History and detail as loaded; one array per answer so the summary does not redraw needlessly. */
  private _points(): AnalyticsDataPoint[] {
    const data = this._data;
    if (!data) return [];
    if (this._pointsOf !== data) {
      this._pointsOf = data;
      this._pointsCache = [...data.history, ...data.detail];
    }
    return this._pointsCache;
  }

  private _onRoomSelected(e: CustomEvent) {
    const areaId = e.detail.areaId;
    if (areaId && areaId !== this._selectedRoom) {
      this._selectedRoom = areaId;
      this.dispatchEvent(
        new CustomEvent("room-selected", {
          detail: { areaId },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onRangeChanged(e: CustomEvent) {
    const { activeQuick, rangeStart, rangeEnd, chartAnchor } = e.detail;
    this._activeQuick = activeQuick;
    this._rangeStart = rangeStart;
    this._rangeEnd = rangeEnd;
    this._chartAnchor = chartAnchor;
  }

  /** Recompute the active quick range up to now (today moves on, a new day starts at midnight). */
  private _applyQuickRange() {
    const days = this._activeQuick ? QUICK_RANGE_DAYS[this._activeQuick] : undefined;
    if (!days) return;
    const { start, end } = quickRange(days, haTimeZone(this.hass));
    this._rangeStart = start;
    this._rangeEnd = end;
  }

  private async _onDaySelected(e: CustomEvent<string>) {
    const now = Date.now();
    const zone = haTimeZone(this.hass);
    const start = startOfDayInZone(e.detail, zone);
    const today = e.detail === isoDateInZone(now, zone);
    this._activeQuick = today ? "24h" : null;
    this._rangeStart = start;
    // The day's last second: midnight of the next day minus one, found via noon (DST)
    const end = startOfDayInZone(isoDateInZone(start + 36 * 3600_000, zone), zone) - 1000;
    this._rangeEnd = today ? now : end;
    this._chartAnchor = this._rangeEnd;
    await this.updateComplete;
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.renderRoot
      .querySelector("rs-analytics-chart")
      ?.scrollIntoView({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
  }

  private _buildWsParams(): Record<string, unknown> {
    return {
      type: "roommind/analytics/get",
      area_id: this._selectedRoom,
      start_ts: this._rangeStart / 1000,
      end_ts: this._rangeEnd / 1000,
    };
  }

  private async _fetchData() {
    if (!this._selectedRoom) return;
    const fetchId = ++this._fetchId;
    this._loading = true;
    // Same room: the old data stays up, so a new range does not reset scroll and open views
    if (this._dataRoom !== this._selectedRoom) this._data = null;
    this._dataRoom = this._selectedRoom;
    this._chartAnchor = this._rangeEnd;

    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      if (fetchId === this._fetchId) this._data = result;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] fetchData:", err);
      if (fetchId === this._fetchId) this._data = null;
    } finally {
      if (fetchId === this._fetchId) this._loading = false;
    }
  }

  private async _silentRefresh() {
    if (!this._selectedRoom || this._loading) return;
    if (this._activeQuick) {
      // A new end (and after midnight a new start) refetches through willUpdate; same room,
      // so the data stays up meanwhile and _fetchId drops answers that come too late
      this._applyQuickRange();
      return;
    }
    const fetchId = this._fetchId;
    const room = this._selectedRoom;
    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      if (fetchId !== this._fetchId || room !== this._selectedRoom) return;
      this._data = result;
      this._chartAnchor = Date.now();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] silentRefresh:", err);
    }
  }

  static styles = css`
    :host {
      display: block;
      min-width: 0;
    }

    rs-analytics-chart {
      scroll-margin-top: 120px;
    }

    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .no-data p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
      margin-top: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics": RsAnalytics;
  }
}

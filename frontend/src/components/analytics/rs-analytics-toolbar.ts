/**
 * rs-analytics-toolbar – Room chips, range choice with custom date range, export and
 * diagnostics menus.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, AnalyticsData } from "../../types";
import { localize } from "../../utils/localize";
import { formatTempLocale } from "../../utils/temperature";
import {
  QUICK_RANGE_DAYS,
  formatClock,
  formatDay,
  formatDayTime,
  haTimeZone,
  isoDateInZone,
  quickRange,
  sameDayInZone,
  startOfDayInZone,
} from "../../utils/analytics-time";
import { buildCsvString, downloadString, buildExportFilename } from "../../utils/analytics-export";
import { copyToClipboard } from "../../utils/clipboard";
import { tokens } from "../../styles/tokens";
import type { ChipItem } from "../shared/rs-chip-group";
import type { RsSegmentOption } from "../shared/rs-segmented";
import type { RsMenuItem } from "../shared/rs-menu";
import "../shared/rs-chip-group";
import "../shared/rs-segmented";
import "../shared/rs-menu";

const QUICK_RANGES = [
  { key: "24h", labelKey: "analytics.range_1d" },
  { key: "2d", labelKey: "analytics.range_2d" },
  { key: "7d", labelKey: "analytics.range_7d" },
  { key: "30d", labelKey: "analytics.range_30d" },
] as const;

@customElement("rs-analytics-toolbar")
export class RsAnalyticsToolbar extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: String }) public selectedRoom = "";
  @property({ type: Number }) public rangeStart = 0;
  @property({ type: Number }) public rangeEnd = 0;
  @property({ type: String }) public activeQuick: string | null = "24h";
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: String }) public language = "en";

  @state() private _diagLoading = false;

  render() {
    const l = this.language;
    return html`
      <rs-chip-group
        scrollable
        .label=${localize("analytics.room", l)}
        .chips=${this._roomChips()}
        @chip-clicked=${this._onRoomChip}
      ></rs-chip-group>
      ${this.selectedRoom ? this._renderControls(l) : nothing}
    `;
  }

  private _roomChips(): ChipItem[] {
    return Object.entries(this.rooms).map(([areaId, config]) => {
      const area = this.hass?.areas?.[areaId];
      const temp = config.live?.current_temp;
      return {
        id: areaId,
        label: config.display_name || area?.name || areaId,
        icon: area?.icon || "mdi:texture-box",
        meta: temp != null ? `${formatTempLocale(temp, this.hass)}°` : undefined,
        active: areaId === this.selectedRoom,
      };
    });
  }

  private _renderControls(l: string) {
    const hasData = !!this.data && (this.data.history.length > 0 || this.data.detail.length > 0);
    const custom = this.activeQuick === null;
    const zone = haTimeZone(this.hass);
    // Within one day the end needs its time only ("11. Nov., 00:00 – 14:20")
    const sameDay = sameDayInZone(this.rangeStart, this.rangeEnd, zone);
    const end = sameDay
      ? formatClock(this.rangeEnd, l, zone)
      : formatDayTime(this.rangeEnd, l, zone);
    // A start at midnight (every quick range) reads as the date alone, keeps the line short
    const midnight =
      startOfDayInZone(isoDateInZone(this.rangeStart, zone), zone) === this.rangeStart;
    const start =
      !sameDay && midnight
        ? formatDay(this.rangeStart, l, zone)
        : formatDayTime(this.rangeStart, l, zone);
    const quick: RsSegmentOption[] = QUICK_RANGES.map((r) => ({
      value: r.key,
      label: localize(r.labelKey, l),
    }));
    const actions = (prefix: string): RsMenuItem[] => [
      {
        value: `${prefix}-download`,
        label: localize("analytics.export_download", l),
        icon: "mdi:download",
      },
      {
        value: `${prefix}-copy`,
        label: localize("analytics.export_clipboard", l),
        icon: "mdi:content-copy",
      },
    ];
    return html`
      <div class="controls">
        <rs-segmented
          class="quick"
          reselect
          .label=${localize("analytics.range", l)}
          .options=${quick}
          .value=${this.activeQuick}
          @value-changed=${this._onQuick}
        ></rs-segmented>
        <div class="custom">
          <div class="picker ${custom ? "active" : ""}">
            <ha-date-range-picker
              .hass=${this.hass}
              .startDate=${new Date(this.rangeStart)}
              .endDate=${new Date(this.rangeEnd)}
              .ranges=${false}
              time-picker
              auto-apply
              minimal
              @value-changed=${this._onDateRangeChanged}
            ></ha-date-range-picker>
          </div>
          <span class="range-text ${custom ? "custom" : ""}">${start} – ${end}</span>
          <span class="grow"></span>
          <rs-menu
            icon="mdi:download"
            .text=${localize("analytics.export", l)}
            .label=${localize("analytics.export", l)}
            .items=${actions("csv")}
            .disabled=${!hasData}
            @menu-select=${this._onMenu}
          ></rs-menu>
          <rs-menu
            .icon=${this._diagLoading ? "mdi:loading" : "mdi:stethoscope"}
            .text=${localize("analytics.copy_diagnostics", l)}
            .label=${localize("analytics.copy_diagnostics", l)}
            .items=${actions("diag")}
            .disabled=${this._diagLoading}
            @menu-select=${this._onMenu}
          ></rs-menu>
        </div>
      </div>
    `;
  }

  private _onRoomChip(e: CustomEvent<string>) {
    e.stopPropagation();
    const areaId = e.detail;
    if (areaId && areaId !== this.selectedRoom) {
      this.dispatchEvent(
        new CustomEvent("room-selected", {
          detail: { areaId },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onQuick(e: CustomEvent<{ value: string }>) {
    e.stopPropagation();
    const days = QUICK_RANGE_DAYS[e.detail.value];
    if (!days) return;
    const { start, end } = quickRange(days, haTimeZone(this.hass));
    this._fireRange(e.detail.value, start, end);
  }

  private _onDateRangeChanged(e: CustomEvent) {
    e.stopPropagation();
    const { startDate, endDate } = e.detail.value as { startDate: Date; endDate: Date };
    if (!startDate || !endDate) return;
    this._fireRange(null, startDate.getTime(), endDate.getTime());
  }

  private _fireRange(activeQuick: string | null, rangeStart: number, rangeEnd: number) {
    this.dispatchEvent(
      new CustomEvent("range-changed", {
        detail: { activeQuick, rangeStart, rangeEnd, chartAnchor: rangeEnd },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onMenu(e: CustomEvent<{ value: string }>) {
    e.stopPropagation();
    switch (e.detail.value) {
      case "csv-download":
        this._exportCsv();
        break;
      case "csv-copy":
        this._copyCsv();
        break;
      case "diag-download":
        this._diagnostics((json) =>
          downloadString(json, "roommind_diagnostics.json", "application/json"),
        );
        break;
      case "diag-copy":
        this._diagnostics((json) => copyToClipboard(json));
        break;
    }
  }

  private _exportCsv() {
    const csv = this.data ? buildCsvString(this.data) : null;
    if (!csv) return;
    const filename = buildExportFilename(
      this.hass,
      this.rooms,
      this.selectedRoom,
      this.rangeStart,
      this.rangeEnd,
      "",
      "csv",
    );
    downloadString(csv, filename, "text/csv");
  }

  private _copyCsv() {
    const csv = this.data ? buildCsvString(this.data) : null;
    if (csv) copyToClipboard(csv);
  }

  /** The whole integration's diagnostics, not the room's; one request at a time. */
  private async _diagnostics(use: (json: string) => void) {
    if (this._diagLoading) return;
    this._diagLoading = true;
    try {
      const result = await this.hass.callWS<Record<string, unknown>>({
        type: "roommind/diagnostics/get",
      });
      use(JSON.stringify(result, null, 2));
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[RoomMind] diagnostics export failed:", err);
    } finally {
      this._diagLoading = false;
    }
  }

  static styles = [
    tokens,
    css`
      :host {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-3);
        margin-bottom: var(--rs-space-4);
        min-width: 0;
      }

      .controls {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--rs-space-2) var(--rs-space-3);
        min-width: 0;
      }

      .quick {
        flex: 0 1 360px;
      }

      .custom {
        flex: 1 1 auto;
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
        min-width: 0;
      }

      .picker {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: none;
        border-radius: 50%;
        color: var(--secondary-text-color);
        --mdc-icon-size: 20px;
      }

      .picker.active {
        background: var(--rs-fill-primary);
        color: var(--primary-color);
      }

      .range-text {
        font-size: 13px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        min-width: 0;
      }

      .range-text.custom {
        color: var(--primary-color);
      }

      .grow {
        flex: 1;
      }

      @media (max-width: 600px) {
        .quick {
          flex: 1 1 100%;
        }
        .range-text {
          font-size: var(--rs-font-sm);
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-toolbar": RsAnalyticsToolbar;
  }
}

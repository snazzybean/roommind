/**
 * rs-analytics-toolbar – Room selector, range buttons, export/diagnostics dropdowns.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, AnalyticsData } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { buildCsvString, downloadString, buildExportFilename } from "../../utils/analytics-export";
import { copyToClipboard } from "../../utils/clipboard";

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

  @state() private _openDropdown: "csv" | "diag" | null = null;
  @state() private _diagLoading = false;

  private _boundCloseDropdowns = this._closeDropdowns.bind(this);

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener("click", this._boundCloseDropdowns);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    document.removeEventListener("click", this._boundCloseDropdowns);
  }

  protected updated(changedProps: Map<string, unknown>) {
    if ((changedProps.has("rooms") || changedProps.has("selectedRoom")) && this.selectedRoom) {
      this.updateComplete.then(() => {
        const select = this.renderRoot?.querySelector("ha-select") as HTMLElement & {
          value?: string;
        };
        if (select && select.value !== this.selectedRoom) {
          select.value = this.selectedRoom;
        }
      });
    }
  }

  render() {
    const l = this.language;
    const configuredRooms = this._getConfiguredRooms();

    return html`
      ${this._renderRoomSelector(configuredRooms, l)}
      ${this.selectedRoom ? this._renderRangeButtons(l) : nothing}
    `;
  }

  private _getConfiguredRooms(): Array<{ area_id: string; name: string }> {
    return Object.entries(this.rooms).map(([area_id, config]) => {
      const area = this.hass?.areas?.[area_id];
      return { area_id, name: config.display_name || area?.name || area_id };
    });
  }

  private _renderRoomSelector(rooms: Array<{ area_id: string; name: string }>, l: string) {
    return html`
      <div class="selector-row">
        <ha-select
          .value=${this.selectedRoom}
          .label=${localize("analytics.select_room", l)}
          .options=${rooms.map((r) => ({ value: r.area_id, label: r.name }))}
          naturalMenuWidth
          fixedMenuPosition
          @selected=${this._onRoomSelected}
          @closed=${(e: Event) => e.stopPropagation()}
        >
          ${rooms.map((r) => html` <ha-list-item value=${r.area_id}>${r.name}</ha-list-item> `)}
        </ha-select>
      </div>
    `;
  }

  private _renderRangeButtons(l: string) {
    const quickRanges = [
      { key: "24h", label: localize("analytics.range_1d", l), days: 1 },
      { key: "2d", label: localize("analytics.range_2d", l), days: 2 },
      { key: "7d", label: localize("analytics.range_7d", l), days: 7 },
      { key: "30d", label: localize("analytics.range_30d", l), days: 30 },
    ];
    const hasData = this.data && (this.data.history.length > 0 || this.data.detail.length > 0);

    const fmt = (ms: number) => {
      return new Date(ms).toLocaleString(this.hass.language, {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    };

    return html`
      <div class="range-row">
        <div class="range-controls">
          <div class="range-bar">
            ${quickRanges.map(
              (r) => html`
                <button
                  class="range-chip"
                  ?active=${this.activeQuick === r.key}
                  @click=${() => this._onQuickRange(r.key, r.days)}
                >
                  ${r.label}
                </button>
              `,
            )}
            <div class="range-chip picker-chip ${this.activeQuick === null ? "picker-active" : ""}">
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
          </div>
          <span class="date-label ${this.activeQuick === null ? "custom-active" : ""}"
            >${fmt(this.rangeStart)} – ${fmt(this.rangeEnd)}</span
          >
        </div>
        <div class="action-buttons">
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!hasData}
              @click=${(e: Event) => {
                e.stopPropagation();
                this._toggleDropdown("csv");
              }}
            >
              <ha-icon icon="mdi:download"></ha-icon>
              ${localize("analytics.export", l)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown === "csv"
              ? html`<div class="export-dropdown" @click=${(e: Event) => e.stopPropagation()}>
                  <button @click=${this._exportCsv}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${localize("analytics.export_download", l)}
                  </button>
                  <button @click=${this._copyCsvToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${localize("analytics.export_clipboard", l)}
                  </button>
                </div>`
              : nothing}
          </div>
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${this._diagLoading}
              @click=${(e: Event) => {
                e.stopPropagation();
                this._toggleDropdown("diag");
              }}
            >
              <ha-icon icon=${this._diagLoading ? "mdi:loading" : "mdi:bug-outline"}></ha-icon>
              ${localize("analytics.copy_diagnostics", l)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown === "diag"
              ? html`<div class="export-dropdown" @click=${(e: Event) => e.stopPropagation()}>
                  <button @click=${this._exportDiagnostics}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${localize("analytics.export_download", l)}
                  </button>
                  <button @click=${this._copyDiagnosticsToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${localize("analytics.export_clipboard", l)}
                  </button>
                </div>`
              : nothing}
          </div>
        </div>
      </div>
    `;
  }

  private _onRoomSelected(e: Event) {
    const value = getSelectValue(e);
    if (value && value !== this.selectedRoom) {
      this.dispatchEvent(
        new CustomEvent("room-selected", {
          detail: { areaId: value },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onQuickRange(key: string, days: number) {
    const now = new Date();
    const start = new Date(now);
    start.setDate(start.getDate() - (days - 1));
    start.setHours(0, 0, 0, 0);
    this.dispatchEvent(
      new CustomEvent("range-changed", {
        detail: {
          activeQuick: key,
          rangeStart: start.getTime(),
          rangeEnd: now.getTime(),
          chartAnchor: now.getTime(),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onDateRangeChanged(e: CustomEvent) {
    const { startDate, endDate } = e.detail.value as { startDate: Date; endDate: Date };
    if (!startDate || !endDate) return;
    this.dispatchEvent(
      new CustomEvent("range-changed", {
        detail: {
          activeQuick: null,
          rangeStart: startDate.getTime(),
          rangeEnd: endDate.getTime(),
          chartAnchor: endDate.getTime(),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _exportCsv() {
    if (!this.data) return;
    const csv = buildCsvString(this.data);
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
    this._openDropdown = null;
  }

  private async _exportDiagnostics() {
    if (this._diagLoading) return;
    this._diagLoading = true;
    this._openDropdown = null;
    try {
      const result = await this.hass.callWS<Record<string, unknown>>({
        type: "roommind/diagnostics/get",
      });
      const json = JSON.stringify(result, null, 2);
      downloadString(json, "roommind_diagnostics.json", "application/json");
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[RoomMind] diagnostics export failed:", err);
    } finally {
      this._diagLoading = false;
    }
  }

  private _copyCsvToClipboard() {
    if (!this.data) return;
    const csv = buildCsvString(this.data);
    if (!csv) return;
    copyToClipboard(csv);
    this._openDropdown = null;
  }

  private async _copyDiagnosticsToClipboard() {
    if (this._diagLoading) return;
    this._diagLoading = true;
    this._openDropdown = null;
    try {
      const result = await this.hass.callWS<Record<string, unknown>>({
        type: "roommind/diagnostics/get",
      });
      const json = JSON.stringify(result, null, 2);
      copyToClipboard(json);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[RoomMind] diagnostics clipboard failed:", err);
    } finally {
      this._diagLoading = false;
    }
  }

  private _toggleDropdown(id: "csv" | "diag") {
    this._openDropdown = this._openDropdown === id ? null : id;
  }

  private _closeDropdowns() {
    if (this._openDropdown) {
      this._openDropdown = null;
    }
  }

  static styles = css`
    :host {
      display: block;
    }

    .selector-row {
      margin-bottom: 16px;
    }

    .selector-row ha-select {
      width: 100%;
    }

    .range-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      gap: 12px;
    }

    .range-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
    }

    .range-bar {
      display: inline-flex;
      border-radius: 12px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
    }

    .range-bar > :first-child {
      border-radius: 12px 0 0 12px;
    }

    .range-bar > :last-child {
      border-radius: 0 12px 12px 0;
    }

    .range-chip {
      padding: 7px 14px;
      border: none;
      border-right: 1px solid var(--divider-color);
      background: transparent;
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition:
        background 0.15s ease,
        color 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
    }

    .range-chip:last-child {
      border-right: none;
    }

    .range-chip:hover:not([active]) {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
      color: var(--primary-text-color);
    }

    .range-chip[active] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .picker-chip {
      display: flex;
      align-items: center;
      padding: 0;
      cursor: pointer;
    }

    .picker-chip ha-date-range-picker {
      --mdc-icon-size: 18px;
      --mdc-icon-button-size: 32px;
    }

    .picker-chip.picker-active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .date-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .date-label.custom-active {
      color: var(--primary-color);
    }

    .action-buttons {
      display: flex;
      gap: 8px;
    }

    .export-split {
      position: relative;
      display: inline-flex;
    }

    .export-btn {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 7px 14px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-btn:hover {
      color: var(--primary-text-color);
      border-color: var(--primary-color);
    }

    .export-btn[disabled] {
      opacity: 0.4;
      cursor: default;
    }

    .arrow-icon {
      --mdc-icon-size: 14px;
      margin-left: 2px;
      margin-right: -4px;
    }

    .export-dropdown {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 4px;
      min-width: 100%;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      z-index: 10;
      overflow: hidden;
    }

    .export-dropdown button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-dropdown button:hover {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
    }

    .export-dropdown button + button {
      border-top: 1px solid var(--divider-color);
    }

    @media (max-width: 600px) {
      .range-row {
        flex-wrap: wrap;
      }
      .range-controls {
        flex-wrap: wrap;
      }
      .range-chip {
        padding: 6px 10px;
        font-size: 11px;
      }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-toolbar": RsAnalyticsToolbar;
  }
}

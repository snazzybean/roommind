import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomConfig } from "./types";
import { getEntitiesForArea } from "./utils/room-state";
import { loadHaElements } from "./load-ha-elements";
import { localize } from "./utils/localize";
import { mdiEyeOff } from "./utils/icons";
import "./components/rs-settings";
import "./components/rs-analytics";

const BACK_PATH = "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z";

const DELETE_PATH =
  "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z";

const CHART_PATH =
  "M16,11.78L20.24,4.45L21.97,5.45L16.74,14.5L10.23,10.75L5.46,19H22V21H2V3H4V17.54L9.5,8L16,11.78Z";

const THERMOMETER_PATH =
  "M15 13V5A3 3 0 0 0 9 5V13A5 5 0 1 0 15 13M12 4A1 1 0 0 1 13 5V8H11V5A1 1 0 0 1 12 4Z";

type TabId = "areas" | "analytics" | "settings";

interface AreaInfo {
  area: HassArea;
  config: RoomConfig | null;
  climateEntityCount: number;
  tempSensorCount: number;
}

@customElement("roommind-panel")
export class RoomMindPanel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) public narrow = false;
  @property({ type: Object }) public route: { path: string } = { path: "" };
  @property({ type: Object }) public panel: Record<string, unknown> = {};

  @state() private _activeTab: TabId = "areas";
  @state() private _rooms: Record<string, RoomConfig> = {};
  @state() private _roomsLoaded = false;
  @state() private _selectedAreaId: string | null = null;
  @state() private _analyticsRoom = "";
  @state() private _vacationActive = false;
  @state() private _vacationTemp: number | null = null;
  @state() private _vacationUntil: number | null = null;
  @state() private _hiddenRooms: string[] = [];
  @state() private _showHiddenRooms = false;
  @state() private _controlMode: "mpc" | "bangbang" = "bangbang";
  @state() private _climateControlActive = true;
  @state() private _presenceEnabled = false;
  @state() private _valveProtectionEnabled = false;
  @state() private _anyoneHome = true;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _saveStatus: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private _roomOrder: string[] = [];
  @state() private _groupByFloor = false;
  @state() private _reorderMode = false;
  @state() private _elementsLoaded = false;

  private _refreshInterval?: ReturnType<typeof setInterval>;
  private _routeApplied = false;
  private _saveStatusTimeout?: ReturnType<typeof setTimeout>;
  private _areaInfosCache: AreaInfo[] = [];

  static styles = css`
    :host {
      display: block;
      font-family: var(--primary-font-family, Roboto, sans-serif);
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100vh;
    }

    .toolbar {
      display: flex;
      align-items: center;
      height: 56px;
      padding: 0 12px;
      font-size: 20px;
      background-color: var(--app-header-background-color, var(--primary-background-color));
      color: var(--app-header-text-color, var(--primary-text-color));
      border-bottom: 1px solid var(--divider-color);
      box-sizing: border-box;
      position: sticky;
      top: 0;
      z-index: 4;
    }

    .toolbar .title {
      margin-left: 4px;
      font-weight: 400;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .toolbar ha-icon-button {
      color: var(--app-header-text-color, var(--primary-text-color));
    }

    .save-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 400;
      margin-right: 8px;
      opacity: 1;
      transition: opacity 0.3s ease;
    }

    .save-indicator.fade-out {
      opacity: 0;
    }

    .save-indicator ha-icon {
      --mdc-icon-size: 18px;
    }

    .save-indicator.saving {
      color: var(--primary-color, #03a9f4);
    }

    .save-indicator.saved {
      color: var(--success-color, #4caf50);
    }

    .save-indicator.error {
      color: var(--error-color, #d32f2f);
    }

    .tabs {
      display: flex;
      gap: 0;
      border-bottom: 1px solid var(--divider-color);
      padding: 0 16px;
      background: var(--primary-background-color);
      position: sticky;
      top: 56px;
      z-index: 3;
    }

    .tab {
      padding: 12px 24px;
      cursor: pointer;
      border: none;
      background: none;
      color: var(--secondary-text-color);
      font-size: 14px;
      font-weight: 500;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
      font-family: inherit;
    }

    .tab:hover {
      color: var(--primary-text-color);
    }

    .tab[active] {
      color: var(--primary-color);
      border-bottom-color: var(--primary-color);
    }

    .content {
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
      box-sizing: border-box;
    }

    @media (max-width: 600px) {
      .content {
        padding: 16px;
      }
    }

    .placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .placeholder ha-icon {
      margin-bottom: 16px;
    }

    .placeholder p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
    }

    .area-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
      gap: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .stats-separator {
      width: 1px;
      height: 28px;
      background: var(--divider-color, #444);
      margin: 0 4px;
      flex-shrink: 0;
    }

    .stats-bar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px 24px;
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .stats-actions {
      display: flex;
      align-items: center;
      margin-left: auto;
      gap: 0;
    }

    .hidden-rooms-toggle {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .hidden-rooms-panel {
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .hidden-rooms-header {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .hidden-room-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 0;
    }

    .hidden-room-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .stat-value {
      font-size: 20px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .stat-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .floor-heading {
      font-size: 14px;
      font-weight: 500;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin: 20px 0 8px 0;
    }

    .floor-heading:first-of-type {
      margin-top: 0;
    }

    .reorder-btn {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .reorder-done {
      font-size: 14px;
      margin-left: auto;
    }
  `;

  connectedCallback() {
    super.connectedCallback();
    loadHaElements().then(() => {
      this._elementsLoaded = true;
    });
    this._loadRooms();
    this._refreshInterval = setInterval(() => this._loadRooms(), 5000);
    this.addEventListener("save-status", this._onSaveStatus as EventListener);
    if (!this._routeApplied) {
      this._applyRoute();
      this._routeApplied = true;
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = undefined;
    }
    if (this._saveStatusTimeout) clearTimeout(this._saveStatusTimeout);
    this.removeEventListener("save-status", this._onSaveStatus as EventListener);
  }

  render() {
    if (!this._elementsLoaded) return html``;

    const l = this.hass.language;
    const inDetail = !!this._selectedAreaId;
    const detailArea = inDetail ? this.hass?.areas?.[this._selectedAreaId!] : null;

    const tabLabels: Record<TabId, string> = {
      areas: localize("panel.tab.rooms", l),
      analytics: localize("tabs.analytics", l),
      settings: localize("panel.tab.settings", l),
    };

    return html`
      <div class="toolbar">
        ${inDetail
          ? html`<ha-icon-button
              .path=${BACK_PATH}
              @click=${this._onBackFromDetail}
            ></ha-icon-button>`
          : html`<ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>`}
        <div class="title">
          ${inDetail
            ? this._rooms[this._selectedAreaId!]?.display_name || detailArea?.name || ""
            : localize("panel.title", l)}
        </div>
        ${this._renderSaveIndicator()}
        ${inDetail && this._rooms[this._selectedAreaId!]
          ? html`<ha-icon-button
                .path=${CHART_PATH}
                @click=${this._onGoToAnalytics}
              ></ha-icon-button
              ><ha-icon-button .path=${DELETE_PATH} @click=${this._onDeleteRoom}></ha-icon-button>`
          : nothing}
        ${!inDetail && this._activeTab === "analytics" && this._analyticsRoom
          ? html`<ha-icon-button
              .path=${THERMOMETER_PATH}
              @click=${this._onGoToRoomFromAnalytics}
            ></ha-icon-button>`
          : nothing}
      </div>

      ${!inDetail
        ? html`
            <div class="tabs">
              ${(Object.keys(tabLabels) as TabId[]).map(
                (tab) => html`
                  <button
                    class="tab"
                    ?active=${this._activeTab === tab}
                    @click=${() => this._onTabClicked(tab)}
                  >
                    ${tabLabels[tab]}
                  </button>
                `,
              )}
            </div>
          `
        : nothing}

      <div class="content">${this._renderTab()}</div>
    `;
  }

  private _renderTab() {
    switch (this._activeTab) {
      case "areas":
        return this._renderAreas();
      case "analytics":
        return html`<rs-analytics
          .hass=${this.hass}
          .rooms=${this._rooms}
          .initialRoom=${this._analyticsRoom}
          .controlMode=${this._controlMode}
          @room-selected=${this._onAnalyticsRoomSelected}
        ></rs-analytics>`;
      case "settings":
        return this._renderSettings();
      default:
        return nothing;
    }
  }

  private _renderAreas() {
    if (this._selectedAreaId) {
      const area = this.hass?.areas?.[this._selectedAreaId];
      if (area) {
        const config = this._rooms[this._selectedAreaId] ?? null;
        return html`
          <rs-room-detail
            .area=${area}
            .config=${config}
            .hass=${this.hass}
            .presenceEnabled=${this._presenceEnabled}
            .presencePersons=${this._presencePersons}
            .climateControlActive=${this._climateControlActive}
            .valveProtectionEnabled=${this._valveProtectionEnabled}
            @back-clicked=${this._onBackFromDetail}
            @room-updated=${this._onRoomUpdated}
          ></rs-room-detail>
        `;
      }
      this._selectedAreaId = null;
    }

    if (!this._roomsLoaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }

    const allAreaInfos = this._areaInfosCache;
    const areaInfos = allAreaInfos.filter((i) => !this._hiddenRooms.includes(i.area.area_id));
    const hiddenAreaInfos = allAreaInfos.filter((i) => this._hiddenRooms.includes(i.area.area_id));

    if (allAreaInfos.length === 0) {
      return html`
        <div class="placeholder">
          <ha-icon icon="mdi:home" style="--mdc-icon-size: 56px; opacity: 0.4"></ha-icon>
          <p>
            ${localize("panel.no_areas", this.hass.language)}<br />${localize(
              "panel.no_areas_hint",
              this.hass.language,
            )}
          </p>
        </div>
      `;
    }

    const configuredCount = areaInfos.filter((i) => i.config).length;
    const heatingCount = areaInfos.filter((i) => i.config?.live?.mode === "heating").length;
    const coolingCount = areaInfos.filter((i) => i.config?.live?.mode === "cooling").length;
    const moldCount = areaInfos.filter(
      (i) =>
        i.config?.live?.mold_risk_level === "warning" ||
        i.config?.live?.mold_risk_level === "critical",
    ).length;
    const hasConditionalStats =
      this._vacationActive || (this._presenceEnabled && !this._anyoneHome) || moldCount > 0;
    const l = this.hass.language;

    return html`
      ${configuredCount > 0 || hiddenAreaInfos.length > 0
        ? html`
            <ha-card class="stats-bar">
              ${configuredCount > 0
                ? html`
                    <div class="stat">
                      <span class="stat-value">${configuredCount}</span>
                      <span class="stat-label">${localize("panel.stat.rooms", l)}</span>
                    </div>
                    <div class="stat">
                      <span class="stat-value" style="color: var(--warning-color, #ff9800)"
                        >${heatingCount}</span
                      >
                      <span class="stat-label">${localize("panel.stat.heating", l)}</span>
                    </div>
                    <div class="stat">
                      <span class="stat-value" style="color: var(--info-color, #2196f3)"
                        >${coolingCount}</span
                      >
                      <span class="stat-label">${localize("panel.stat.cooling", l)}</span>
                    </div>
                  `
                : nothing}
              ${hasConditionalStats ? html`<div class="stats-separator"></div>` : nothing}
              ${this._vacationActive
                ? html`
                    <div class="stat">
                      <span class="stat-value" style="color: var(--success-color, #4caf50)">✈</span>
                      <span class="stat-label">${localize("panel.stat.vacation", l)}</span>
                    </div>
                  `
                : nothing}
              ${this._presenceEnabled && !this._anyoneHome
                ? html`
                    <div class="stat">
                      <span class="stat-value" style="color: var(--secondary-text-color)">⏻</span>
                      <span class="stat-label">${localize("panel.stat.away", l)}</span>
                    </div>
                  `
                : nothing}
              ${moldCount > 0
                ? html`
                    <div class="stat">
                      <span class="stat-value" style="color: var(--error-color, #f44336)"
                        >${moldCount}</span
                      >
                      <span class="stat-label">${localize("panel.stat.mold", l)}</span>
                    </div>
                  `
                : nothing}
              <span class="stats-actions">
                ${hiddenAreaInfos.length > 0
                  ? html`<ha-icon-button
                      class="hidden-rooms-toggle"
                      .path=${mdiEyeOff}
                      @click=${() => {
                        this._showHiddenRooms = !this._showHiddenRooms;
                      }}
                    ></ha-icon-button>`
                  : nothing}
                ${this._reorderMode
                  ? html`<ha-button class="reorder-done" @click=${this._onReorderDone}>
                      ${localize("panel.reorder_done", l)}
                    </ha-button>`
                  : html`<ha-icon-button
                      class="reorder-btn"
                      .path=${"M9,3L5,7H8V14H10V7H13M16,17V10H14V17H11L15,21L19,17H16Z"}
                      @click=${() => {
                        this._reorderMode = true;
                      }}
                      title=${localize("panel.reorder", l)}
                    ></ha-icon-button>`}
              </span>
            </ha-card>
          `
        : nothing}
      ${this._showHiddenRooms && hiddenAreaInfos.length > 0
        ? html`
            <ha-card class="hidden-rooms-panel">
              <div class="hidden-rooms-header">
                <span>${localize("panel.hidden_rooms", l)} (${hiddenAreaInfos.length})</span>
              </div>
              ${hiddenAreaInfos.map(
                (info) => html`
                  <div class="hidden-room-row">
                    <span class="hidden-room-name">${info.area.name}</span>
                    <ha-button @click=${() => this._unhideRoom(info.area.area_id)}>
                      ${localize("panel.unhide", l)}
                    </ha-button>
                  </div>
                `,
              )}
            </ha-card>
          `
        : nothing}
      ${this._getFloorGroups(areaInfos).map(
        (group) => html`
          ${group.name ? html`<h4 class="floor-heading">${group.name}</h4>` : nothing}
          <div class="area-grid">
            ${group.items.map(
              (info, idx) => html`
                <rs-area-card
                  .area=${info.area}
                  .config=${info.config}
                  .climateEntityCount=${info.climateEntityCount}
                  .tempSensorCount=${info.tempSensorCount}
                  .hass=${this.hass}
                  .controlMode=${this._controlMode}
                  .climateControlActive=${this._climateControlActive}
                  .reordering=${this._reorderMode}
                  .canMoveUp=${idx > 0}
                  .canMoveDown=${idx < group.items.length - 1}
                  @area-selected=${this._onAreaSelected}
                  @hide-room=${this._onHideRoom}
                  @move-room-up=${this._onMoveRoomUp}
                  @move-room-down=${this._onMoveRoomDown}
                ></rs-area-card>
              `,
            )}
          </div>
        `,
      )}
    `;
  }

  private _renderSettings() {
    return html`<rs-settings .hass=${this.hass} .rooms=${this._rooms}></rs-settings>`;
  }

  private _computeAreaInfos(): AreaInfo[] {
    if (!this.hass?.areas) return [];

    const areas = Object.values(this.hass.areas);

    const infos: AreaInfo[] = areas.map((area) => {
      const areaEntities = getEntitiesForArea(
        area.area_id,
        this.hass.entities,
        this.hass.devices,
      ).filter((e) => {
        const idAfterDot = e.entity_id.substring(e.entity_id.indexOf(".") + 1);
        return !idAfterDot.startsWith("roommind_");
      });

      const climateEntityCount = areaEntities.filter((e) =>
        e.entity_id.startsWith("climate."),
      ).length;

      const tempSensorCount = areaEntities.filter(
        (e) =>
          e.entity_id.startsWith("sensor.") &&
          this.hass.states[e.entity_id]?.attributes?.device_class === "temperature",
      ).length;

      return {
        area,
        config: this._rooms[area.area_id] ?? null,
        climateEntityCount,
        tempSensorCount,
      };
    });

    // Apply custom room_order, then default sort for unordered rooms
    const orderIndex = new Map(this._roomOrder.map((id, i) => [id, i]));
    infos.sort((a, b) => {
      const aIdx = orderIndex.get(a.area.area_id);
      const bIdx = orderIndex.get(b.area.area_id);
      // Both in custom order: use that order
      if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx;
      // Only one in custom order: it comes first
      if (aIdx !== undefined) return -1;
      if (bIdx !== undefined) return 1;
      // Neither in custom order: configured first, then alphabetical
      const aScore = a.config ? 2 : a.climateEntityCount > 0 ? 1 : 0;
      const bScore = b.config ? 2 : b.climateEntityCount > 0 ? 1 : 0;
      if (aScore !== bScore) return bScore - aScore;
      return a.area.name.localeCompare(b.area.name);
    });

    return infos;
  }

  private _getFloorGroups(areaInfos: AreaInfo[]): { name: string; items: AreaInfo[] }[] {
    if (!this._groupByFloor || !this.hass.floors) return [{ name: "", items: areaInfos }];

    const floors = this.hass.floors;
    const l = this.hass.language;
    const groups = new Map<string | null, AreaInfo[]>();
    const floorOrder: (string | null)[] = [];

    for (const info of areaInfos) {
      const fid = info.area.floor_id ?? null;
      if (!groups.has(fid)) {
        groups.set(fid, []);
        floorOrder.push(fid);
      }
      groups.get(fid)!.push(info);
    }

    // Sort floor keys: by level (if available), then by name, null last
    floorOrder.sort((a, b) => {
      if (a === null) return 1;
      if (b === null) return -1;
      const fa = floors[a];
      const fb = floors[b];
      if (fa?.level != null && fb?.level != null) return fb.level - fa.level;
      if (fa?.level != null) return -1;
      if (fb?.level != null) return 1;
      return (fa?.name ?? "").localeCompare(fb?.name ?? "");
    });

    return floorOrder.map((fid) => ({
      name:
        fid === null
          ? localize("panel.floor_other", l)
          : (floors[fid]?.name ?? localize("panel.floor_other", l)),
      items: groups.get(fid)!,
    }));
  }

  private async _loadRooms() {
    try {
      const result = await this.hass.callWS<{
        rooms: Record<string, RoomConfig>;
        vacation_active: boolean;
        vacation_temp: number | null;
        vacation_until: number | null;
        hidden_rooms: string[];
        room_order: string[];
        group_by_floor: boolean;
        control_mode: "mpc" | "bangbang";
        climate_control_active: boolean;
        presence_enabled: boolean;
        anyone_home: boolean;
        presence_persons: string[];
        presence_away_action: "eco" | "off";
        schedule_off_action: "eco" | "off";
        valve_protection_enabled: boolean;
      }>({
        type: "roommind/rooms/list",
      });
      this._rooms = result.rooms;
      this._vacationActive = result.vacation_active ?? false;
      this._vacationTemp = result.vacation_temp ?? null;
      this._vacationUntil = result.vacation_until ?? null;
      this._hiddenRooms = result.hidden_rooms ?? [];
      this._roomOrder = result.room_order ?? [];
      this._groupByFloor = result.group_by_floor ?? false;
      this._controlMode = result.control_mode ?? "bangbang";
      this._climateControlActive = result.climate_control_active ?? true;
      this._presenceEnabled = result.presence_enabled ?? false;
      this._valveProtectionEnabled = result.valve_protection_enabled ?? false;
      this._anyoneHome = result.anyone_home ?? true;
      this._presencePersons = result.presence_persons ?? [];
      this._presenceAwayAction = result.presence_away_action ?? "eco";
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] loadRooms:", err);
    } finally {
      this._roomsLoaded = true;
    }
  }

  private _onBackFromDetail() {
    this._selectedAreaId = null;
    this._navigate("");
  }

  private async _onDeleteRoom() {
    if (!this._selectedAreaId) return;
    const area = this.hass?.areas?.[this._selectedAreaId];
    if (!area) return;

    if (!confirm(localize("room.confirm_delete", this.hass.language, { name: area.name }))) {
      return;
    }

    try {
      await this.hass.callWS({
        type: "roommind/rooms/delete",
        area_id: this._selectedAreaId,
      });
      this._selectedAreaId = null;
      this._navigate("");
      this._loadRooms();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] deleteRoom:", err);
    }
  }

  private _onTabClicked(tab: TabId) {
    this._activeTab = tab;
    this._selectedAreaId = null;
    if (tab === "areas") {
      this._navigate("");
    } else {
      this._navigate(`/${tab}`);
    }
  }

  private _onAreaSelected(e: CustomEvent<{ areaId: string }>) {
    this._selectedAreaId = e.detail.areaId;
    this._navigate(`/room/${e.detail.areaId}`);
  }

  private async _onHideRoom(e: CustomEvent<{ areaId: string }>) {
    const newHidden = [...new Set([...this._hiddenRooms, e.detail.areaId])];
    this._hiddenRooms = newHidden;
    try {
      await this.hass.callWS({ type: "roommind/settings/save", hidden_rooms: newHidden });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] hideRoom:", err);
    }
  }

  private async _unhideRoom(areaId: string) {
    const newHidden = this._hiddenRooms.filter((id) => id !== areaId);
    this._hiddenRooms = newHidden;
    if (newHidden.length === 0) this._showHiddenRooms = false;
    try {
      await this.hass.callWS({ type: "roommind/settings/save", hidden_rooms: newHidden });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] unhideRoom:", err);
    }
  }

  private _onGoToAnalytics() {
    if (!this._selectedAreaId) return;
    this._analyticsRoom = this._selectedAreaId;
    this._selectedAreaId = null;
    this._activeTab = "analytics";
    this._navigate(`/analytics/${this._analyticsRoom}`);
  }

  private _onGoToRoomFromAnalytics() {
    if (!this._analyticsRoom) return;
    this._selectedAreaId = this._analyticsRoom;
    this._activeTab = "areas";
    this._navigate(`/room/${this._analyticsRoom}`);
  }

  private _onAnalyticsRoomSelected(e: CustomEvent<{ areaId: string }>) {
    this._analyticsRoom = e.detail.areaId;
    this._navigate(`/analytics/${e.detail.areaId}`);
  }

  private async _onMoveRoomUp(e: CustomEvent<{ areaId: string }>) {
    this._moveRoom(e.detail.areaId, -1);
  }

  private async _onMoveRoomDown(e: CustomEvent<{ areaId: string }>) {
    this._moveRoom(e.detail.areaId, 1);
  }

  private async _moveRoom(areaId: string, direction: -1 | 1) {
    // Build full order from current visible (non-hidden) areaInfos
    const visible = this._areaInfosCache.filter((i) => !this._hiddenRooms.includes(i.area.area_id));

    // If grouping by floor, we only reorder within the same floor group
    if (this._groupByFloor && this.hass.floors) {
      const groups = this._getFloorGroups(visible);
      for (const group of groups) {
        const ids = group.items.map((i) => i.area.area_id);
        const idx = ids.indexOf(areaId);
        if (idx === -1) continue;
        const targetIdx = idx + direction;
        if (targetIdx < 0 || targetIdx >= ids.length) return;
        [ids[idx], ids[targetIdx]] = [ids[targetIdx], ids[idx]];
        // Rebuild full order from all groups
        const newOrder = groups.flatMap((g) =>
          g === group ? ids : g.items.map((i) => i.area.area_id),
        );
        await this._saveRoomOrder(newOrder);
        return;
      }
    } else {
      const ids = visible.map((i) => i.area.area_id);
      const idx = ids.indexOf(areaId);
      if (idx === -1) return;
      const targetIdx = idx + direction;
      if (targetIdx < 0 || targetIdx >= ids.length) return;
      [ids[idx], ids[targetIdx]] = [ids[targetIdx], ids[idx]];
      await this._saveRoomOrder(ids);
    }
  }

  private async _saveRoomOrder(order: string[]) {
    this._roomOrder = order;
    this._areaInfosCache = this._computeAreaInfos();
    try {
      await this.hass.callWS({ type: "roommind/settings/save", room_order: order });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] saveRoomOrder:", err);
    }
  }

  private _onReorderDone() {
    this._reorderMode = false;
  }

  private _onRoomUpdated() {
    this._loadRooms();
  }

  private _onSaveStatus = (e: CustomEvent<{ status: "saving" | "saved" | "error" }>) => {
    e.stopPropagation();
    if (this._saveStatusTimeout) clearTimeout(this._saveStatusTimeout);
    this._saveStatus = e.detail.status;
    if (e.detail.status === "saved") {
      this._saveStatusTimeout = setTimeout(() => {
        this._saveStatus = "idle";
      }, 2000);
    }
  };

  private _renderSaveIndicator() {
    if (this._saveStatus === "idle") return nothing;
    const l = this.hass.language;
    const icon =
      this._saveStatus === "saving"
        ? "mdi:content-save-outline"
        : this._saveStatus === "saved"
          ? "mdi:check"
          : "mdi:alert-circle-outline";
    const label =
      this._saveStatus === "saving"
        ? localize("settings.saving", l)
        : this._saveStatus === "saved"
          ? localize("settings.saved", l)
          : localize("settings.error", l);
    return html`
      <span class="save-indicator ${this._saveStatus}">
        <ha-icon .icon=${icon}></ha-icon>
        ${label}
      </span>
    `;
  }

  protected willUpdate(changedProps: Map<string, unknown>) {
    if (changedProps.has("route") && this._routeApplied) {
      this._applyRoute();
    }
    if (changedProps.has("_rooms") || changedProps.has("hass")) {
      this._areaInfosCache = this._computeAreaInfos();
    }
  }

  updated(changedProps: Map<string, unknown>) {
    if (changedProps.has("hass") && this.hass && !this._roomsLoaded) {
      this._loadRooms();
    }
  }

  private _navigate(path: string) {
    history.replaceState(null, "", `/roommind${path}`);
    window.dispatchEvent(new Event("location-changed"));
  }

  private _applyRoute() {
    const path = this.route?.path ?? "";
    if (path.startsWith("/room/")) {
      this._activeTab = "areas";
      this._selectedAreaId = decodeURIComponent(path.slice(6));
    } else if (path.startsWith("/analytics/")) {
      this._activeTab = "analytics";
      this._selectedAreaId = null;
      this._analyticsRoom = decodeURIComponent(path.slice(11));
    } else if (path === "/analytics") {
      this._activeTab = "analytics";
      this._selectedAreaId = null;
      this._analyticsRoom = "";
    } else if (path === "/settings") {
      this._activeTab = "settings";
      this._selectedAreaId = null;
    } else {
      this._activeTab = "areas";
      this._selectedAreaId = null;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "roommind-panel": RoomMindPanel;
  }
}

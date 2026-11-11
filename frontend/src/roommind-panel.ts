import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, PriceStatus, RoomConfig, RoomWithoutArea } from "./types";
import { loadHaElements } from "./load-ha-elements";
import { localize } from "./utils/localize";
import { fireSaveStatus } from "./utils/events";
import { computeAreaInfos, type AreaInfo } from "./utils/dashboard";
import type { HouseSummary } from "./components/dashboard/rs-dashboard";
import {
  getSettingsCategory,
  resolveSettingsCategory,
} from "./components/settings/settings-categories";
import "./components/rs-settings";
import "./components/rs-analytics";
import "./components/dashboard/rs-dashboard";
import "./components/dashboard/rs-dashboard-edit";
import "./components/shared/rs-icon-button";

type TabId = "areas" | "analytics" | "settings";

/** Panel width from which settings show list and panel side by side (design system). */
const SETTINGS_WIDE_MIN = 900;

/** Esc in these stays with the control (close a dropdown, keep a typed but uncommitted value). */
const ESC_KEEPING_TAGS = new Set([
  "INPUT",
  "TEXTAREA",
  "SELECT",
  "HA-SELECT",
  "HA-COMBO-BOX",
  "HA-ENTITY-PICKER",
  "HA-TEXTFIELD",
  "VAADIN-COMBO-BOX",
  "VAADIN-COMBO-BOX-OVERLAY",
  "MWC-LIST",
  "HA-LIST-ITEM",
]);

@customElement("roommind-panel")
export class RoomMindPanel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) public narrow = false;
  @property({ type: Object }) public route: { path: string } = { path: "" };
  @property({ type: Object }) public panel: Record<string, unknown> = {};

  @state() private _activeTab: TabId = "areas";
  @state() private _rooms: Record<string, RoomConfig> = {};
  @state() private _roomsWithoutArea: RoomWithoutArea[] = [];
  @state() private _roomsLoaded = false;
  @state() private _selectedAreaId: string | null = null;
  @state() private _analyticsRoom = "";
  @state() private _vacationActive = false;
  @state() private _vacationTemp: number | null = null;
  @state() private _vacationUntil: number | null = null;
  @state() private _hiddenRooms: string[] = [];
  @state() private _outdoorTemp: number | null = null;
  @state() private _controlMode: "mpc" | "bangbang" = "mpc";
  @state() private _climateControlActive = true;
  @state() private _presenceEnabled = false;
  @state() private _priceEntity = "";
  @state() private _priceStatus: PriceStatus | null = null;
  @state() private _valveProtectionEnabled = false;
  @state() private _coilDryEnabled = false;
  @state() private _coilDryMinutes = 20;
  @state() private _coilDryMode = "fan_only";
  @state() private _coilDryFanMode = "low";
  @state() private _anyoneHome = true;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _saveStatus: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private _roomOrder: string[] = [];
  @state() private _groupByFloor = false;
  @state() private _editing = false;
  @state() private _elementsLoaded = false;
  @state() private _settingsCategory = "";
  @state() private _wide = window.innerWidth >= SETTINGS_WIDE_MIN;

  private _refreshInterval?: ReturnType<typeof setInterval>;
  private _routeApplied = false;
  private _saveStatusTimeout?: ReturnType<typeof setTimeout>;
  private _areaInfosCache: AreaInfo[] = [];
  private _boundVisibilityHandler?: () => void;
  private _boundConnectionReady?: () => void;
  /** Bumped on every dashboard settings save; polls started before it keep their old layout. */
  private _layoutEpoch = 0;
  private _layoutSaves = 0;
  private _resizeObserver?: ResizeObserver;

  static styles = css`
    :host {
      display: block;
      font-family: var(--primary-font-family, Roboto, sans-serif);
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100vh;

      /* Round the corners of all MDC-based inputs (ha-textfield, ha-select,
         ha-entity-picker, ha-combo-box) to match the rest of the design.
         The bottom corners are rounded via inputStyles in each component. */
      --mdc-shape-small: 8px;
      --mdc-shape-medium: 8px;
      --md-filled-text-field-container-shape: 8px;
      --md-outlined-text-field-container-shape: 8px;
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

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .toolbar.editing {
      background-color: var(--secondary-background-color, var(--app-header-background-color));
    }

    .toolbar rs-icon-button {
      color: var(--app-header-text-color, var(--primary-text-color));
    }

    .toolbar .done {
      margin-right: 4px;
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
    window.addEventListener("keydown", this._onSettingsKey);
    this._resizeObserver ??= new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) this._wide = width >= SETTINGS_WIDE_MIN;
    });
    this._resizeObserver.observe(this);
    if (!this._routeApplied) {
      this._applyRoute();
      this._routeApplied = true;
    }
    // Visibility handler survives disconnectedCallback (intentionally not removed).
    // HA's ha-panel-custom has a bug: after disconnect it clears _setProperties
    // but doesn't re-create the panel element on reconnect if the config hasn't
    // changed. This leaves a blank panel. Reload recovers from this state.
    if (!this._boundVisibilityHandler) {
      this._boundVisibilityHandler = () => {
        if (document.hidden) return;
        if (!this.isConnected) {
          window.location.reload();
          return;
        }
        this._loadRooms();
        this.requestUpdate();
      };
      document.addEventListener("visibilitychange", this._boundVisibilityHandler);
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
    window.removeEventListener("keydown", this._onEditKey);
    window.removeEventListener("keydown", this._onSettingsKey);
    this._resizeObserver?.disconnect();
    // NOTE: _boundVisibilityHandler intentionally NOT removed here.
    // It must survive disconnect to detect when tab becomes visible again
    // and trigger re-navigation if HA removed our element during idle.
    if (this._boundConnectionReady) {
      this.hass?.connection?.removeEventListener("ready", this._boundConnectionReady);
      this._boundConnectionReady = undefined;
    }
  }

  render() {
    if (!this._elementsLoaded || !this.hass) return html``;

    const l = this.hass.language;
    const inDetail = !!this._selectedAreaId;
    const detailArea = inDetail ? this.hass?.areas?.[this._selectedAreaId!] : null;

    const tabLabels: Record<TabId, string> = {
      areas: localize("panel.tab.rooms", l),
      analytics: localize("tabs.analytics", l),
      settings: localize("panel.tab.settings", l),
    };

    if (this._isEditing()) {
      return html`
        <div class="toolbar editing">
          <rs-icon-button
            icon="mdi:close"
            .label=${localize("panel.edit.close", l)}
            @click=${this._stopEditing}
          ></rs-icon-button>
          <div class="title">${localize("panel.edit_rooms", l)}</div>
          ${this._renderSaveIndicator()}
          <ha-button class="done" @click=${this._stopEditing}
            >${localize("panel.edit.done", l)}</ha-button
          >
        </div>
        <div class="content">${this._renderTab()}</div>
      `;
    }

    const settingsPage = this._settingsSubpage();
    let title = localize("panel.title", l);
    if (inDetail) {
      title = this._rooms[this._selectedAreaId!]?.display_name || detailArea?.name || "";
    } else if (settingsPage) {
      title = localize(getSettingsCategory(settingsPage)!.title, l);
    }

    return html`
      <div class="toolbar">
        ${
          inDetail
            ? html`<rs-icon-button
                icon="mdi:arrow-left"
                .label=${localize("room.back", l)}
                @click=${this._onBackFromDetail}
              ></rs-icon-button>`
            : settingsPage
              ? html`<rs-icon-button
                  icon="mdi:arrow-left"
                  .label=${localize("settings.back", l)}
                  @click=${this._onBackFromSettingsPage}
                ></rs-icon-button>`
              : html`<ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>`
        }
        <div class="title">${title}</div>
        ${this._renderSaveIndicator()}
        ${
          !inDetail && this._activeTab === "areas" && this._roomsLoaded
            ? html`<rs-icon-button
                icon="mdi:pencil"
                .label=${localize("panel.edit_rooms", l)}
                @click=${this._startEditing}
              ></rs-icon-button>`
            : nothing
        }
        ${
          inDetail && this._rooms[this._selectedAreaId!]
            ? html`<rs-icon-button
                icon="mdi:chart-line"
                .label=${localize("detail.analytics", l)}
                @click=${this._onGoToAnalytics}
              ></rs-icon-button>`
            : nothing
        }
        ${
          !inDetail && this._activeTab === "analytics" && this._analyticsRoom
            ? html`<rs-icon-button
                icon="mdi:thermometer"
                .label=${localize("detail.open_room", l)}
                @click=${this._onGoToRoomFromAnalytics}
              ></rs-icon-button>`
            : nothing
        }
      </div>

      ${
        !inDetail && !settingsPage
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
          : nothing
      }

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
    if (!this._roomsLoaded) {
      return html`<div class="loading">${localize("panel.loading", this.hass.language)}</div>`;
    }

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
            .priceConfigured=${!!this._priceEntity}
            .presencePersons=${this._presencePersons}
            .climateControlActive=${this._climateControlActive}
            .valveProtectionEnabled=${this._valveProtectionEnabled}
            .controlMode=${this._controlMode}
            .coilDryEnabled=${this._coilDryEnabled}
            .coilDryMinutes=${this._coilDryMinutes}
            .coilDryMode=${this._coilDryMode}
            .coilDryFanMode=${this._coilDryFanMode}
            .outdoorTemp=${this._outdoorTemp}
            .vacationActive=${this._vacationActive}
            .vacationUntil=${this._vacationUntil}
            @room-updated=${this._onRoomUpdated}
            @room-deleted=${this._onRoomDeleted}
            @open-analytics=${this._onGoToAnalytics}
          ></rs-room-detail>
        `;
      }
      this._selectedAreaId = null;
    }

    const common = {
      hass: this.hass,
      infos: this._areaInfosCache,
      hiddenRooms: this._hiddenRooms,
      groupByFloor: this._groupByFloor,
      controlMode: this._controlMode,
      climateControlActive: this._climateControlActive,
    };
    if (this._isEditing()) {
      return html`<rs-dashboard-edit
        .hass=${common.hass}
        .infos=${common.infos}
        .hiddenRooms=${common.hiddenRooms}
        .groupByFloor=${common.groupByFloor}
        .controlMode=${common.controlMode}
        .climateControlActive=${common.climateControlActive}
        @room-order-changed=${this._onRoomOrderChanged}
        @room-hidden-changed=${this._onRoomHiddenChanged}
        @group-by-floor-changed=${this._onGroupByFloorChanged}
        @area-selected=${this._onAreaSelected}
      ></rs-dashboard-edit>`;
    }
    const summary: HouseSummary = {
      vacationActive: this._vacationActive,
      vacationUntil: this._vacationUntil,
      presenceEnabled: this._presenceEnabled,
      anyoneHome: this._anyoneHome,
      outdoorTemp: this._outdoorTemp,
      priceEntity: this._priceEntity,
      priceStatus: this._priceStatus,
    };
    return html`<rs-dashboard
      .hass=${common.hass}
      .infos=${common.infos}
      .hiddenRooms=${common.hiddenRooms}
      .groupByFloor=${common.groupByFloor}
      .controlMode=${common.controlMode}
      .climateControlActive=${common.climateControlActive}
      .summary=${summary}
      @area-selected=${this._onAreaSelected}
      @room-updated=${this._onRoomUpdated}
      @edit-requested=${this._startEditing}
    ></rs-dashboard>`;
  }

  private _renderSettings() {
    return html`<rs-settings
      .hass=${this.hass}
      .rooms=${this._rooms}
      .roomsWithoutArea=${this._roomsWithoutArea}
      .climateControlActive=${this._climateControlActive}
      .priceStatus=${this._priceStatus}
      .category=${this._settingsCategory}
      .wide=${this._wide}
      @settings-category-changed=${this._onSettingsCategoryChanged}
    ></rs-settings>`;
  }

  /** The settings category shown as its own page (narrow layout), else "". */
  private _settingsSubpage() {
    if (this._activeTab !== "settings" || this._selectedAreaId || this._wide) return "";
    return resolveSettingsCategory(
      this._settingsCategory,
      this._roomsWithoutArea.length > 0,
      false,
    );
  }

  private _onSettingsCategoryChanged(e: CustomEvent<{ category: string }>) {
    this._settingsCategory = e.detail.category;
    this._navigate(this._settingsCategory ? `/settings/${this._settingsCategory}` : "/settings");
  }

  private _onBackFromSettingsPage = () => {
    this._settingsCategory = "";
    this._navigate("/settings");
  };

  private _onSettingsKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || e.defaultPrevented || !this._settingsSubpage()) return;
    const path = e.composedPath();
    const inControl = path.some(
      (el) =>
        el instanceof HTMLElement &&
        (ESC_KEEPING_TAGS.has(el.tagName) ||
          el.getAttribute("role") === "combobox" ||
          el.getAttribute("role") === "listbox"),
    );
    if (inControl) return;
    this._onBackFromSettingsPage();
  };

  private async _loadRooms() {
    if (!this.hass) return;
    const epoch = this._layoutEpoch;
    try {
      const result = await this.hass.callWS<{
        rooms: Record<string, RoomConfig>;
        rooms_without_area?: RoomWithoutArea[];
        outdoor_temp?: number | null;
        vacation_active: boolean;
        vacation_temp: number | null;
        vacation_until: number | null;
        hidden_rooms: string[];
        room_order: string[];
        group_by_floor: boolean;
        control_mode: "mpc" | "bangbang";
        climate_control_active: boolean;
        presence_enabled: boolean;
        price_entity?: string;
        price_status?: PriceStatus | null;
        anyone_home: boolean;
        presence_persons: string[];
        presence_away_action: "eco" | "off";
        schedule_off_action: "eco" | "off";
        valve_protection_enabled: boolean;
        coil_dry_enabled: boolean;
        coil_dry_minutes: number;
        coil_dry_mode: string;
        coil_dry_fan_mode: string;
      }>({
        type: "roommind/rooms/list",
      });
      this._rooms = result.rooms;
      this._roomsWithoutArea = result.rooms_without_area ?? [];
      this._vacationActive = result.vacation_active ?? false;
      this._vacationTemp = result.vacation_temp ?? null;
      this._vacationUntil = result.vacation_until ?? null;
      // A layout save started or finished meanwhile: this answer may predate it.
      if (epoch === this._layoutEpoch && this._layoutSaves === 0) {
        this._hiddenRooms = result.hidden_rooms ?? [];
        this._roomOrder = result.room_order ?? [];
        this._groupByFloor = result.group_by_floor ?? false;
      }
      this._outdoorTemp = result.outdoor_temp ?? null;
      this._controlMode = result.control_mode ?? "mpc";
      this._climateControlActive = result.climate_control_active ?? true;
      this._presenceEnabled = result.presence_enabled ?? false;
      this._priceEntity = result.price_entity ?? "";
      this._priceStatus = result.price_status ?? null;
      this._valveProtectionEnabled = result.valve_protection_enabled ?? false;
      this._coilDryEnabled = result.coil_dry_enabled ?? false;
      this._coilDryMinutes = result.coil_dry_minutes ?? 20;
      this._coilDryMode = result.coil_dry_mode ?? "fan_only";
      this._coilDryFanMode = result.coil_dry_fan_mode ?? "low";
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

  /** The room page removed the room after its own confirmation. */
  private _onRoomDeleted() {
    this._selectedAreaId = null;
    this._navigate("");
    this._loadRooms();
  }

  private _onTabClicked(tab: TabId) {
    this._stopEditing();
    this._activeTab = tab;
    this._selectedAreaId = null;
    this._settingsCategory = "";
    if (tab === "areas") {
      this._navigate("");
    } else {
      this._navigate(`/${tab}`);
    }
  }

  private _onAreaSelected(e: CustomEvent<{ areaId: string }>) {
    this._stopEditing();
    this._selectedAreaId = e.detail.areaId;
    this._navigate(`/room/${e.detail.areaId}`);
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

  private _isEditing(): boolean {
    return this._editing && this._activeTab === "areas" && !this._selectedAreaId;
  }

  private _startEditing = () => {
    this._editing = true;
    window.addEventListener("keydown", this._onEditKey);
  };

  private _stopEditing = () => {
    this._editing = false;
    window.removeEventListener("keydown", this._onEditKey);
  };

  private _onEditKey = (e: KeyboardEvent) => {
    // Tooltips, menus and a running drag catch their own Esc first (capture phase).
    if (e.key === "Escape" && this._isEditing() && !e.defaultPrevented) this._stopEditing();
  };

  private _onRoomOrderChanged(e: CustomEvent<{ order: string[] }>) {
    const previous = this._roomOrder;
    this._roomOrder = e.detail.order;
    this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
    this._saveLayout({ room_order: e.detail.order }, () => {
      this._roomOrder = previous;
    });
  }

  private _onRoomHiddenChanged(e: CustomEvent<{ areaId: string; hidden: boolean }>) {
    const previous = this._hiddenRooms;
    const { areaId, hidden } = e.detail;
    this._hiddenRooms = hidden
      ? [...new Set([...this._hiddenRooms, areaId])]
      : this._hiddenRooms.filter((id) => id !== areaId);
    this._saveLayout({ hidden_rooms: this._hiddenRooms }, () => {
      this._hiddenRooms = previous;
    });
  }

  private _onGroupByFloorChanged(e: CustomEvent<{ value: boolean }>) {
    const previous = this._groupByFloor;
    this._groupByFloor = e.detail.value;
    this._saveLayout({ group_by_floor: e.detail.value }, () => {
      this._groupByFloor = previous;
    });
  }

  /**
   * Dashboard layout (order, hidden rooms, floors) through the settings merge, with the
   * toolbar's save status; rolls back on error. Polls already on the way don't overwrite it.
   */
  private async _saveLayout(changes: Record<string, unknown>, rollback: () => void) {
    this._layoutEpoch++;
    this._layoutSaves++;
    fireSaveStatus(this, "saving");
    try {
      await this.hass.callWS({ type: "roommind/settings/save", ...changes });
      fireSaveStatus(this, "saved");
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] save dashboard layout:", err);
      rollback();
      this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
      fireSaveStatus(this, "error");
    } finally {
      this._layoutSaves--;
      this._layoutEpoch++;
      this._loadRooms();
    }
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
    if (changedProps.has("_rooms") || changedProps.has("hass") || changedProps.has("_roomOrder")) {
      this._areaInfosCache = computeAreaInfos(this.hass, this._rooms, this._roomOrder);
    }
  }

  updated(changedProps: Map<string, unknown>) {
    if (changedProps.has("hass") && this.hass && !this._roomsLoaded) {
      this._loadRooms();
    }
    if (changedProps.has("hass") && this.hass?.connection && !this._boundConnectionReady) {
      this._boundConnectionReady = () => {
        this._loadRooms();
        this.requestUpdate();
      };
      this.hass.connection.addEventListener("ready", this._boundConnectionReady);
    }
  }

  private _navigate(path: string) {
    history.replaceState(null, "", `/roommind${path}`);
    window.dispatchEvent(new Event("location-changed"));
  }

  private _applyRoute() {
    this._stopEditing();
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
    } else if (path === "/settings" || path.startsWith("/settings/")) {
      this._activeTab = "settings";
      this._selectedAreaId = null;
      const requested = decodeURIComponent(path.slice(10));
      this._settingsCategory = getSettingsCategory(requested) ? requested : "";
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

/**
 * rs-settings – Global RoomMind settings page (orchestrator).
 * Owns all state, loads/saves settings and shows them as master-detail: grouped categories
 * with a one-line summary each, the selected category's sub-component beside them (`wide`) or
 * alone as a subpage (narrow). The panel owns the selected category (URL) and the width;
 * selecting one fires `settings-category-changed` { category } ("" = back to the list).
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  GlobalSettings,
  RoomConfig,
  NotificationTarget,
  CompressorGroup,
  RoomWithoutArea,
  PriceStatus,
} from "../types";
import { localize } from "../utils/localize";
import { errorText } from "../utils/errors";
import { fireSaveStatus } from "../utils/events";
import { VACATION_SENTINEL } from "../utils/constants";
import { formatMinutes, formatNumber, formatPercent } from "../utils/format";
import { formatTempLocale, tempUnit, toDisplayDelta } from "../utils/temperature";
import { describePriceStatus } from "../utils/price-status";
import { tokens, alertStyles } from "../styles/tokens";
import {
  SETTINGS_GROUPS,
  getSettingsCategory,
  resolveSettingsCategory,
  type SettingsCategoryId,
} from "./settings/settings-categories";
import "./shared/rs-list-row";
import "./shared/rs-badge";
import "./settings/rs-settings-general";
import "./settings/rs-settings-sensors";
import "./settings/rs-settings-price";
import "./settings/rs-settings-control";
import "./settings/rs-settings-presence";
import "./settings/rs-settings-vacation";
import "./settings/rs-settings-valve";
import "./settings/rs-settings-compressor";
import "./settings/rs-settings-coil-dry";
import "./settings/rs-settings-mold";
import "./settings/rs-settings-notifications";
import "./settings/rs-settings-learning";
import "./settings/rs-settings-reset";
import "./settings/rs-settings-orphans";

@customElement("rs-settings")
export class RsSettings extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ attribute: false }) public roomsWithoutArea: RoomWithoutArea[] = [];
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ attribute: false }) public priceStatus: PriceStatus | null = null;
  /** Requested category (from the URL); unknown or unavailable ones fall back. */
  @property({ type: String }) public category = "";
  /** List and panel side by side; otherwise list, then the panel as a subpage. */
  @property({ type: Boolean }) public wide = true;
  @state() private _deletedOrphans: ReadonlySet<string> = new Set();

  @state() private _groupByFloor = false;
  @state() private _climateControlActive = true;
  @state() private _learningDisabledRooms: string[] = [];
  @state() private _outdoorTempSensor = "";
  @state() private _priceEntity = "";
  @state() private _outdoorHumiditySensor = "";
  @state() private _outdoorCoolingMin = 16;
  @state() private _outdoorHeatingMax = 22;
  @state() private _controlMode: "mpc" | "bangbang" = "mpc";
  @state() private _comfortWeight = 70;
  @state() private _weatherEntity = "";
  @state() private _outdoorUnavailableNotify = true;
  @state() private _predictionEnabled = true;
  @state() private _vacationActive = false;
  @state() private _vacationTemp = 15;
  @state() private _vacationUntil = "";
  @state() private _presenceEnabled = false;
  @state() private _presencePersons: string[] = [];
  @state() private _presenceAwayAction: "eco" | "off" = "eco";
  @state() private _presenceClearsOverride = false;
  @state() private _scheduleOffAction: "eco" | "off" = "eco";
  @state() private _valveProtectionEnabled = false;
  @state() private _valveProtectionInterval = 7;
  @state() private _moldDetectionEnabled = false;
  @state() private _moldHumidityThreshold = 70;
  @state() private _moldFRsi = 0.8;
  @state() private _moldSustainedMinutes = 30;
  @state() private _moldNotificationCooldown = 60;
  @state() private _moldNotificationsEnabled = true;
  @state() private _moldNotificationTargets: NotificationTarget[] = [];
  @state() private _moldPreventionEnabled = false;
  @state() private _moldPreventionIntensity: "light" | "medium" | "strong" = "medium";
  @state() private _moldPreventionNotify = false;
  @state() private _compressorGroups: CompressorGroup[] = [];
  @state() private _coilDryEnabled = false;
  @state() private _coilDryMinutes = 20;
  @state() private _coilDryMode: "fan_only" | "dry" = "fan_only";
  @state() private _coilDryFanMode = "low";
  @state() private _coilDryMinCoolingMinutes = 10;
  @state() private _coilDryDrainMinutes = 0;
  @state() private _loaded = false;
  // A failed load must not render the forms: the next full-payload save would write defaults.
  @state() private _loadFailed = false;
  @state() private _saveError = "";

  private _saveDebounce?: ReturnType<typeof setTimeout>;
  // switch.roommind_climate_control can change it while this page is open (#291), so it
  // is only sent after the toggle here was used, never as a stale copy with other settings.
  private _climateControlDirty = false;

  connectedCallback() {
    super.connectedCallback();
    this._loadSettings();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) {
      // Leaving the tab within the debounce: send the change instead of dropping it.
      clearTimeout(this._saveDebounce);
      this._saveDebounce = undefined;
      void this._doSave();
    }
  }

  private async _loadSettings() {
    this._loadFailed = false;
    try {
      const result = await this.hass.callWS<{ settings: GlobalSettings }>({
        type: "roommind/settings/get",
      });
      const s = result.settings;
      this._groupByFloor = s.group_by_floor ?? false;
      this._climateControlActive = s.climate_control_active ?? true;
      this._learningDisabledRooms = s.learning_disabled_rooms ?? [];
      this._outdoorTempSensor = s.outdoor_temp_sensor ?? "";
      this._priceEntity = s.price_entity ?? "";
      this._outdoorHumiditySensor = s.outdoor_humidity_sensor ?? "";
      this._outdoorCoolingMin = s.outdoor_cooling_min ?? 16;
      this._outdoorHeatingMax = s.outdoor_heating_max ?? 22;
      this._controlMode = s.control_mode ?? "mpc";
      this._comfortWeight = s.comfort_weight ?? 70;
      this._weatherEntity = s.weather_entity ?? "";
      this._outdoorUnavailableNotify = s.outdoor_unavailable_notify ?? true;
      this._predictionEnabled = s.prediction_enabled ?? true;
      const vUntil = s.vacation_until;
      this._vacationActive = !!(vUntil && vUntil > Date.now() / 1000);
      this._vacationTemp = s.vacation_temp ?? 15;
      if (vUntil && vUntil > Date.now() / 1000 && vUntil < VACATION_SENTINEL) {
        this._vacationUntil = this._tsToDatetimeLocal(vUntil);
      } else {
        this._vacationUntil = "";
      }
      this._presenceEnabled = s.presence_enabled ?? false;
      this._presencePersons = s.presence_persons ?? [];
      this._presenceAwayAction = s.presence_away_action ?? "eco";
      this._presenceClearsOverride = s.presence_clears_override ?? false;
      this._scheduleOffAction = s.schedule_off_action ?? "eco";
      this._valveProtectionEnabled = s.valve_protection_enabled ?? false;
      this._valveProtectionInterval = s.valve_protection_interval_days ?? 7;
      this._moldDetectionEnabled = s.mold_detection_enabled ?? false;
      this._moldHumidityThreshold = s.mold_humidity_threshold ?? 70;
      this._moldFRsi = s.mold_f_rsi ?? 0.8;
      this._moldSustainedMinutes = s.mold_sustained_minutes ?? 30;
      this._moldNotificationCooldown = s.mold_notification_cooldown ?? 60;
      this._moldNotificationsEnabled = s.mold_notifications_enabled ?? true;
      this._moldNotificationTargets = s.mold_notification_targets ?? [];
      this._moldPreventionEnabled = s.mold_prevention_enabled ?? false;
      this._moldPreventionIntensity = s.mold_prevention_intensity ?? "medium";
      this._moldPreventionNotify = s.mold_prevention_notify_enabled ?? false;
      this._compressorGroups = s.compressor_groups ?? [];
      this._coilDryEnabled = s.coil_dry_enabled ?? false;
      this._coilDryMinutes = s.coil_dry_minutes ?? 20;
      this._coilDryMode = s.coil_dry_mode ?? "fan_only";
      this._coilDryFanMode = s.coil_dry_fan_mode ?? "low";
      this._coilDryMinCoolingMinutes = s.coil_dry_min_cooling_minutes ?? 10;
      this._coilDryDrainMinutes = s.coil_dry_drain_minutes ?? 0;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.debug("[RoomMind] loadSettings:", err);
      this._loadFailed = true;
    } finally {
      this._loaded = true;
    }
  }

  protected willUpdate(changed: Map<string, unknown>) {
    if (
      (changed.has("roomsWithoutArea") || changed.has("_deletedOrphans")) &&
      this.category === "orphans" &&
      this._visibleOrphans().length === 0 &&
      ((changed.get("roomsWithoutArea") as RoomWithoutArea[] | undefined)?.length ||
        changed.has("_deletedOrphans"))
    ) {
      // The last resting room went away (deleted here or its area came back): leave its page.
      this._selectCategory("");
    }
    if (changed.has("roomsWithoutArea") && this._deletedOrphans.size) {
      // The list from the backend is current again; an id resting later must show up again
      const listed = new Set(this.roomsWithoutArea.map((r) => r.area_id));
      this._deletedOrphans = new Set([...this._deletedOrphans].filter((id) => listed.has(id)));
    }
    if (
      changed.has("climateControlActive") &&
      changed.get("climateControlActive") !== undefined &&
      !this._climateControlDirty
    ) {
      this._climateControlActive = this.climateControlActive;
    }
  }

  protected updated(changed: Map<string, unknown>) {
    if (!changed.has("category") || this.wide) return;
    const previous = changed.get("category") as string | undefined;
    if (this.category && resolveSettingsCategory(this.category, this._hasOrphans(), false)) {
      // Subpage opened from a scrolled list: start at its top, focus its heading.
      window.scrollTo({ top: 0 });
      this.renderRoot.querySelector<HTMLElement>("#page-title")?.focus({ preventScroll: true });
    } else if (previous) {
      // Back to the list: return to the entry the subpage was opened from.
      const row = this.renderRoot.querySelector<HTMLElement>(`rs-list-row[data-id="${previous}"]`);
      row?.scrollIntoView({ block: "center" });
      row?.focus();
    }
  }

  protected render() {
    const l = this.hass.language;
    if (!this._loaded) {
      return html`<div class="loading">${localize("panel.loading", l)}</div>`;
    }
    if (this._loadFailed) {
      return html`<ha-card class="load-error">
        <div role="alert">${localize("settings.load_error", l)}</div>
        <ha-button @click=${() => this._loadSettings()}>${localize("common.retry", l)}</ha-button>
      </ha-card>`;
    }

    const selected = resolveSettingsCategory(this.category, this._hasOrphans(), this.wide);
    if (!this.wide && selected) return this._renderPage(selected);

    return html`<div class="layout ${this.wide ? "wide" : ""}">
      ${this._renderNav(selected)} ${this.wide && selected ? this._renderPage(selected) : nothing}
    </div>`;
  }

  private _renderNav(selected: SettingsCategoryId | "") {
    const l = this.hass.language;
    const hasOrphans = this._hasOrphans();
    return html`<nav aria-label=${localize("panel.tab.settings", l)}>
      ${SETTINGS_GROUPS.map((group) => {
        const categories = group.categories.filter((c) => c.id !== "orphans" || hasOrphans);
        if (!categories.length) return nothing;
        return html`<section class="group">
          <h2 class="group-label">${localize(group.label, l)}</h2>
          <ha-card class="nav-card">
            ${categories.map((c) => {
              const summary = this._summary(c.id);
              const attention = c.id === "orphans";
              return html`<rs-list-row
                data-id=${c.id}
                href=${`/roommind/settings/${c.id}`}
                single-line
                .icon=${c.icon}
                .iconColor=${attention ? "var(--rs-warn)" : ""}
                .variant=${attention ? "warn" : "default"}
                .heading=${localize(c.title, l)}
                .secondary=${summary.text}
                .status=${summary.on === undefined ? "" : summary.on ? "on" : "off"}
                .selected=${this.wide && selected === c.id}
                .chevron=${!this.wide}
                @click=${(e: MouseEvent) => this._onNavClick(e, c.id)}
              ></rs-list-row>`;
            })}
          </ha-card>
        </section>`;
      })}
    </nav>`;
  }

  private _renderPage(id: SettingsCategoryId) {
    const l = this.hass.language;
    const category = getSettingsCategory(id)!;
    return html`<ha-card class="page">
      <section aria-labelledby="page-title">
        <header class="page-head">
          <span class="page-icon ${id === "orphans" ? "attention" : ""}" aria-hidden="true">
            <ha-icon .icon=${category.icon}></ha-icon>
          </span>
          <div class="page-text">
            <div class="page-title-row">
              <h2 id="page-title" tabindex="-1">${localize(category.title, l)}</h2>
              ${
                id === "notifications"
                  ? html`<rs-badge
                      tooltip
                      .label=${localize("badge.beta", l)}
                      .hint=${localize("badge.beta_hint", l)}
                    ></rs-badge>`
                  : nothing
              }
            </div>
            <p>${localize(category.intro, l)}</p>
          </div>
        </header>
        <div class="page-body">
          ${
            this._saveError
              ? html`<p class="rs-alert" role="alert">
                  ${localize("settings.save_error", l, { error: this._saveError })}
                </p>`
              : nothing
          }
          ${this._renderPanel(id)}
        </div>
      </section>
    </ha-card>`;
  }

  private _renderPanel(id: SettingsCategoryId) {
    switch (id) {
      case "orphans":
        return html`<rs-settings-orphans
          .hass=${this.hass}
          .rooms=${this._visibleOrphans()}
          @orphan-deleted=${(e: CustomEvent<string>) => {
            this._deletedOrphans = new Set([...this._deletedOrphans, e.detail]);
          }}
        ></rs-settings-orphans>`;
      case "general":
        return html`<rs-settings-general
          .hass=${this.hass}
          .groupByFloor=${this._groupByFloor}
          .climateControlActive=${this._climateControlActive}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-general>`;
      case "sensors":
        return html`<rs-settings-sensors
          .hass=${this.hass}
          .outdoorTempSensor=${this._outdoorTempSensor}
          .outdoorHumiditySensor=${this._outdoorHumiditySensor}
          .weatherEntity=${this._weatherEntity}
          .outdoorUnavailableNotify=${this._outdoorUnavailableNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-sensors>`;
      case "price":
        return html`<rs-settings-price
          .hass=${this.hass}
          .priceEntity=${this._priceEntity}
          .status=${this.priceStatus}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-price>`;
      case "control":
        return html`<rs-settings-control
          .hass=${this.hass}
          .controlMode=${this._controlMode}
          .comfortWeight=${this._comfortWeight}
          .outdoorCoolingMin=${this._outdoorCoolingMin}
          .outdoorHeatingMax=${this._outdoorHeatingMax}
          .predictionEnabled=${this._predictionEnabled}
          .scheduleOffAction=${this._scheduleOffAction}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-control>`;
      case "presence":
        return html`<rs-settings-presence
          .hass=${this.hass}
          .presenceEnabled=${this._presenceEnabled}
          .presencePersons=${this._presencePersons}
          .presenceAwayAction=${this._presenceAwayAction}
          .presenceClearsOverride=${this._presenceClearsOverride}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-presence>`;
      case "vacation":
        return html`<rs-settings-vacation
          .hass=${this.hass}
          .vacationActive=${this._vacationActive}
          .vacationTemp=${this._vacationTemp}
          .vacationUntil=${this._vacationUntil}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-vacation>`;
      case "valve":
        return html`<rs-settings-valve
          .hass=${this.hass}
          .valveProtectionEnabled=${this._valveProtectionEnabled}
          .valveProtectionInterval=${this._valveProtectionInterval}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-valve>`;
      case "compressor":
        return html`<rs-settings-compressor
          .hass=${this.hass}
          .compressorGroups=${this._compressorGroups}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-compressor>`;
      case "coil_dry":
        return html`<rs-settings-coil-dry
          .hass=${this.hass}
          .coilDryEnabled=${this._coilDryEnabled}
          .coilDryMinutes=${this._coilDryMinutes}
          .coilDryMode=${this._coilDryMode}
          .coilDryFanMode=${this._coilDryFanMode}
          .coilDryMinCoolingMinutes=${this._coilDryMinCoolingMinutes}
          .coilDryDrainMinutes=${this._coilDryDrainMinutes}
          .availableFanModes=${this._availableAcFanModes()}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-coil-dry>`;
      case "mold":
        return html`<rs-settings-mold
          .hass=${this.hass}
          .moldDetectionEnabled=${this._moldDetectionEnabled}
          .moldHumidityThreshold=${this._moldHumidityThreshold}
          .moldFRsi=${this._moldFRsi}
          .moldSustainedMinutes=${this._moldSustainedMinutes}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionIntensity=${this._moldPreventionIntensity}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-mold>`;
      case "notifications":
        return html`<rs-settings-notifications
          .hass=${this.hass}
          .notificationsEnabled=${this._moldNotificationsEnabled}
          .notificationTargets=${this._moldNotificationTargets}
          .notificationCooldown=${this._moldNotificationCooldown}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionNotify=${this._moldPreventionNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-notifications>`;
      case "learning":
        return html`<rs-settings-learning
          .hass=${this.hass}
          .rooms=${this.rooms}
          .learningDisabledRooms=${this._learningDisabledRooms}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-learning>`;
      case "reset":
        return html`<rs-settings-reset
          .hass=${this.hass}
          .rooms=${this.rooms}
        ></rs-settings-reset>`;
    }
  }

  /** One line per category in the list: what is set right now; `on` only for on/off features. */
  private _summary(id: SettingsCategoryId): { text: string; on?: boolean } {
    const l = this.hass.language;
    const off = localize("settings.summary.off", l);
    const count = (n: number) => formatNumber(n, this.hass);
    switch (id) {
      case "orphans": {
        const names = this._visibleOrphans().map((r) => r.display_name || r.area_id);
        return {
          text: localize(
            names.length === 1 ? "settings.summary.orphans_one" : "settings.summary.orphans",
            l,
            { count: count(names.length), names: new Intl.ListFormat(l).format(names) },
          ),
        };
      }
      case "general": {
        if (!this._climateControlActive) {
          return { text: localize("settings.summary.general_off", l), on: false };
        }
        const n = Object.values(this.rooms).filter(
          (r) =>
            (r.devices?.length ?? 0) > 0 && !r.is_outdoor && r.climate_control_enabled !== false,
        ).length;
        return {
          text: localize(
            n === 1 ? "settings.summary.general_on_one" : "settings.summary.general_on",
            l,
            { count: count(n) },
          ),
          on: true,
        };
      }
      case "vacation": {
        if (!this._vacationActive) return { text: off, on: false };
        const temp = `${formatTempLocale(this._vacationTemp, this.hass, 0, 1)} ${tempUnit(this.hass)}`;
        const until = this._vacationUntil ? new Date(this._vacationUntil) : null;
        return {
          text:
            until && !isNaN(until.getTime())
              ? localize("settings.summary.vacation_until", l, {
                  temp,
                  date: new Intl.DateTimeFormat(l, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    hour: "numeric",
                    minute: "2-digit",
                  }).format(until),
                })
              : localize("settings.summary.vacation_open", l, { temp }),
          on: true,
        };
      }
      case "presence": {
        if (!this._presenceEnabled) return { text: off, on: false };
        const n = this._presencePersons.filter((p) => p).length;
        const action = localize(
          this._presenceAwayAction === "off"
            ? "settings.summary.away_off"
            : "settings.summary.away_eco",
          l,
        );
        const key =
          n === 0
            ? "settings.summary.presence_none"
            : n === 1
              ? "settings.summary.presence_one"
              : "settings.summary.presence";
        return { text: localize(key, l, { count: count(n), action }), on: true };
      }
      case "control":
        return {
          text:
            this._controlMode === "bangbang"
              ? localize("settings.summary.control_simple", l)
              : localize("settings.summary.control_mpc", l, {
                  weight: formatPercent(this._comfortWeight, this.hass),
                }),
        };
      case "sensors": {
        const parts: string[] = [];
        if (this._outdoorTempSensor) {
          const v = this._sensorValue(this._outdoorTempSensor);
          parts.push(
            v === null
              ? localize("settings.summary.outdoor_waiting", l)
              : localize("settings.summary.outdoor", l, {
                  value: `${formatNumber(v, this.hass, 1)} ${tempUnit(this.hass)}`,
                }),
          );
        }
        if (this._outdoorHumiditySensor) {
          const v = this._sensorValue(this._outdoorHumiditySensor);
          if (v !== null) parts.push(formatPercent(v, this.hass));
        }
        if (this._weatherEntity) {
          const name =
            this.hass.states[this._weatherEntity]?.attributes?.friendly_name ?? this._weatherEntity;
          parts.push(localize("settings.summary.weather", l, { name: String(name) }));
        }
        return {
          text: parts.length ? parts.join(" · ") : localize("settings.summary.not_set_up", l),
        };
      }
      case "price": {
        if (!this._priceEntity) return { text: localize("settings.summary.not_set_up", l) };
        const s = describePriceStatus(this.priceStatus, this._priceEntity, l);
        if (s.state === "waiting") return { text: localize("settings.price_waiting", l) };
        if (s.state === "unreadable") {
          return { text: localize("settings.summary.price_unreadable", l) };
        }
        return { text: `${localize("settings.price_now", l, { level: s.level })} · ${s.detail}` };
      }
      case "learning": {
        const ids = Object.keys(this.rooms);
        const paused = this._learningDisabledRooms.filter((id) => ids.includes(id)).length;
        let text: string;
        if (!ids.length) text = localize("settings.summary.learning_no_rooms", l);
        else if (!paused) {
          text = localize(
            ids.length === 1
              ? "settings.summary.learning_all_one"
              : "settings.summary.learning_all",
            l,
            { count: count(ids.length) },
          );
        } else if (paused === ids.length) {
          text = localize("settings.summary.learning_paused_all", l);
        } else {
          text = localize("settings.summary.learning_some", l, {
            paused: count(paused),
            count: count(ids.length),
          });
        }
        return { text };
      }
      case "mold": {
        const parts: string[] = [];
        if (this._moldDetectionEnabled) {
          parts.push(
            localize("settings.summary.mold_detect", l, {
              value: formatPercent(this._moldHumidityThreshold, this.hass),
            }),
          );
        }
        if (this._moldPreventionEnabled) {
          const k = { light: 1, medium: 2, strong: 3 }[this._moldPreventionIntensity] ?? 2;
          parts.push(
            localize("settings.summary.mold_prevent", l, {
              delta: `${formatNumber(toDisplayDelta(k, this.hass), this.hass, 0, 1)} ${tempUnit(this.hass)}`,
            }),
          );
        }
        return parts.length ? { text: parts.join(" · "), on: true } : { text: off, on: false };
      }
      case "valve":
        return this._valveProtectionEnabled
          ? {
              text: localize("settings.summary.valve_on", l, {
                days: count(this._valveProtectionInterval),
              }),
              on: true,
            }
          : { text: off, on: false };
      case "compressor": {
        const groups = this._compressorGroups.length;
        if (!groups) return { text: localize("settings.summary.compressor_none", l) };
        const devices = this._compressorGroups.reduce((n, g) => n + g.members.length, 0);
        return {
          text: [
            localize(groups === 1 ? "settings.summary.groups_one" : "settings.summary.groups", l, {
              count: count(groups),
            }),
            localize(
              devices === 1 ? "settings.summary.devices_one" : "settings.summary.devices",
              l,
              { count: count(devices) },
            ),
          ].join(" · "),
        };
      }
      case "coil_dry":
        return this._coilDryEnabled
          ? {
              text: localize("settings.summary.coil_dry_on", l, {
                time: formatMinutes(this._coilDryMinutes, l),
              }),
              on: true,
            }
          : { text: off, on: false };
      case "notifications": {
        if (!this._moldNotificationsEnabled) return { text: off, on: false };
        const n = this._moldNotificationTargets.filter((t) => t.entity_id).length;
        const key =
          n === 0
            ? "settings.summary.notify_none"
            : n === 1
              ? "settings.summary.notify_one"
              : "settings.summary.notify";
        return { text: localize(key, l, { count: count(n) }), on: true };
      }
      case "reset":
        return { text: localize("settings.summary.reset", l) };
    }
  }

  private _sensorValue(entityId: string): number | null {
    const st = this.hass.states[entityId];
    if (!st || st.state === "unavailable" || st.state === "unknown") return null;
    const v = parseFloat(st.state);
    return isNaN(v) ? null : v;
  }

  private _visibleOrphans(): RoomWithoutArea[] {
    return this.roomsWithoutArea.filter((r) => !this._deletedOrphans.has(r.area_id));
  }

  private _hasOrphans(): boolean {
    return this._visibleOrphans().length > 0;
  }

  private _onNavClick(e: MouseEvent, id: SettingsCategoryId) {
    // Ctrl/Cmd/Shift/middle click keep the browser's "open in new tab".
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    this._selectCategory(id);
  }

  private _selectCategory(category: SettingsCategoryId | "") {
    this.dispatchEvent(
      new CustomEvent("settings-category-changed", {
        detail: { category },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    if (key === "climateControlActive") this._climateControlDirty = true;
    (this as Record<string, unknown>)[`_${key}`] = value;
    this._autoSave();
  }

  /**
   * Union of fan_modes across every configured AC entity.
   *
   * The global setting has no single device to read fan_modes from, so show
   * the speeds the user's actual hardware reports instead of a guessed list.
   */
  private _availableAcFanModes(): string[] {
    const modes = new Set<string>();
    for (const room of Object.values(this.rooms ?? {})) {
      for (const dev of room.devices ?? []) {
        if (dev.type !== "ac") continue;
        const st = this.hass?.states?.[dev.entity_id];
        for (const fm of (st?.attributes?.fan_modes ?? []) as string[]) modes.add(fm);
      }
    }
    return [...modes].sort();
  }

  private _tsToDatetimeLocal(ts: number): string {
    const d = new Date(ts * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  private _autoSave() {
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this, "saving");
    const sentClimateControl = this._climateControlDirty ? this._climateControlActive : undefined;

    try {
      await this.hass.callWS({
        type: "roommind/settings/save",
        group_by_floor: this._groupByFloor,
        ...(sentClimateControl !== undefined ? { climate_control_active: sentClimateControl } : {}),
        learning_disabled_rooms: this._learningDisabledRooms,
        outdoor_temp_sensor: this._outdoorTempSensor,
        price_entity: this._priceEntity,
        outdoor_humidity_sensor: this._outdoorHumiditySensor,
        outdoor_cooling_min: this._outdoorCoolingMin,
        outdoor_heating_max: this._outdoorHeatingMax,
        control_mode: this._controlMode,
        comfort_weight: this._comfortWeight,
        weather_entity: this._weatherEntity,
        outdoor_unavailable_notify: this._outdoorUnavailableNotify,
        prediction_enabled: this._predictionEnabled,
        vacation_temp: this._vacationTemp,
        vacation_until: this._vacationActive
          ? this._vacationUntil
            ? new Date(this._vacationUntil).getTime() / 1000
            : VACATION_SENTINEL
          : null,
        presence_enabled: this._presenceEnabled,
        presence_persons: this._presencePersons.filter((p) => p),
        presence_away_action: this._presenceAwayAction,
        presence_clears_override: this._presenceClearsOverride,
        schedule_off_action: this._scheduleOffAction,
        valve_protection_enabled: this._valveProtectionEnabled,
        valve_protection_interval_days: this._valveProtectionInterval,
        compressor_groups: this._compressorGroups.filter((g) => g.members.length > 0),
        coil_dry_enabled: this._coilDryEnabled,
        coil_dry_minutes: this._coilDryMinutes,
        coil_dry_mode: this._coilDryMode,
        coil_dry_fan_mode: this._coilDryFanMode,
        coil_dry_min_cooling_minutes: this._coilDryMinCoolingMinutes,
        coil_dry_drain_minutes: this._coilDryDrainMinutes,
        mold_detection_enabled: this._moldDetectionEnabled,
        mold_humidity_threshold: this._moldHumidityThreshold,
        mold_f_rsi: this._moldFRsi,
        mold_sustained_minutes: this._moldSustainedMinutes,
        mold_notification_cooldown: this._moldNotificationCooldown,
        mold_notifications_enabled: this._moldNotificationsEnabled,
        mold_notification_targets: this._moldNotificationTargets.filter((t) => t.entity_id),
        mold_prevention_enabled: this._moldPreventionEnabled,
        mold_prevention_intensity: this._moldPreventionIntensity,
        mold_prevention_notify_enabled: this._moldPreventionNotify,
        mold_prevention_notify_targets: this._moldPreventionNotify
          ? this._moldNotificationTargets.filter((t) => t.entity_id)
          : [],
      });
      // Toggled again while the request was out: stays dirty, the queued save sends it.
      if (this._climateControlActive === sentClimateControl) this._climateControlDirty = false;
      this._saveError = "";
      fireSaveStatus(this, "saved");
    } catch (err) {
      const l = this.hass.language;
      this._saveError = errorText(err, localize("error.unknown", l), l);
      if (this._climateControlActive === sentClimateControl) {
        this._climateControlDirty = false;
        this._climateControlActive = this.climateControlActive;
      }
      fireSaveStatus(this, "error");
    }
  }

  static styles = [
    tokens,
    alertStyles,
    css`
      :host {
        display: block;
      }

      .layout {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-5);
      }

      .layout.wide {
        display: grid;
        grid-template-columns: 330px minmax(0, 1fr);
        align-items: start;
      }

      nav {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
        min-width: 0;
      }

      .group-label {
        margin: 0 var(--rs-space-2) var(--rs-space-2);
        font-size: var(--rs-font-sm);
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .nav-card {
        padding: var(--rs-space-1);
        --rs-list-row-padding: var(--rs-space-3);
      }

      .page {
        min-width: 0;
      }

      .page-head {
        display: flex;
        gap: var(--rs-space-4);
        align-items: flex-start;
        padding: var(--rs-space-5) var(--rs-space-5) var(--rs-space-4);
      }

      .page-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        flex: none;
        display: grid;
        place-items: center;
        background: var(--rs-fill-primary);
        color: var(--primary-color);
        --mdc-icon-size: 26px;
      }

      .page-icon.attention {
        background: color-mix(in srgb, var(--rs-warn) 14%, transparent);
        color: var(--rs-warn);
      }

      .page-text {
        min-width: 0;
      }

      .page-title-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
        margin-top: 2px;
      }

      h2 {
        margin: 0;
        font-size: 22px;
        font-weight: 400;
        line-height: 1.3;
        overflow-wrap: anywhere;
      }

      h2:focus {
        outline: none;
      }

      .page-text p {
        margin: var(--rs-space-1) 0 0;
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
        max-width: 70ch;
      }

      .page-body {
        --rs-settings-inline: var(--rs-space-5);
        padding: 0 var(--rs-space-5) var(--rs-space-1);
      }

      @media (max-width: 600px) {
        .page-head {
          padding: var(--rs-space-4) var(--rs-space-4) var(--rs-space-3);
        }

        .page-body {
          --rs-settings-inline: var(--rs-space-4);
          padding: 0 var(--rs-space-4);
        }

        h2 {
          font-size: var(--rs-font-xl);
        }
      }

      .loading {
        padding: 80px 16px;
        text-align: center;
        color: var(--secondary-text-color);
      }

      .load-error {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: var(--rs-space-3);
        padding: var(--rs-space-4);
        color: var(--primary-text-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings": RsSettings;
  }
}

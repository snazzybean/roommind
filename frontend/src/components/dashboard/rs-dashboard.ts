import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import type { HomeAssistant, PriceStatus } from "../../types";
import { floorGroups, type AreaInfo } from "../../utils/dashboard";
import { localize, type TranslationKey } from "../../utils/localize";
import { formatTempLocale, tempUnit } from "../../utils/temperature";
import { VACATION_SENTINEL } from "../../utils/constants";
import { tokens } from "../../styles/tokens";
import { dashboardStyles } from "./dashboard-styles";
import "./rs-room-card";
import "../shared/rs-pill";

export interface HouseSummary {
  vacationActive: boolean;
  vacationUntil: number | null;
  presenceEnabled: boolean;
  anyoneHome: boolean;
  outdoorTemp: number | null;
  priceEntity: string;
  priceStatus: PriceStatus | null;
}

const PRICE_LEVEL_KEYS: Record<"cheap" | "normal" | "expensive", TranslationKey> = {
  cheap: "settings.price_level_cheap",
  normal: "settings.price_level_normal",
  expensive: "settings.price_level_expensive",
};

/** Rooms tab: house summary pills and the room cards, grouped by floor if wanted. */
@customElement("rs-dashboard")
export class RsDashboard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  /** All areas in display order, hidden ones included. */
  @property({ attribute: false }) public infos: AreaInfo[] = [];
  @property({ attribute: false }) public hiddenRooms: string[] = [];
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Boolean }) public climateControlActive = true;
  @property({ attribute: false }) public summary!: HouseSummary;

  static styles = [tokens, dashboardStyles];

  render() {
    const l = this.hass.language;
    if (this.infos.length === 0) {
      return html`<div class="placeholder">
        <ha-icon icon="mdi:home"></ha-icon>
        <p>${localize("panel.no_areas", l)}<br />${localize("panel.no_areas_hint", l)}</p>
      </div>`;
    }
    const hidden = new Set(this.hiddenRooms);
    const visible = this.infos.filter((i) => !hidden.has(i.area.area_id));
    if (visible.length === 0) {
      return html`${this._renderPills(visible)}
        <div class="placeholder">
          <ha-icon icon="mdi:eye-off-outline"></ha-icon>
          <p>${localize("panel.all_hidden", l)}</p>
          <ha-button @click=${this._requestEdit}>${localize("panel.edit_rooms", l)}</ha-button>
        </div>`;
    }
    const groups = floorGroups(visible, this.hass, this.groupByFloor);
    return html`
      ${this._renderPills(visible)}
      ${groups.map(
        (g) => html`
          ${
            g.name
              ? html`<h2 class="floor">${g.name} <span class="count">${g.items.length}</span></h2>`
              : nothing
          }
          <div class="grid">
            ${repeat(
              g.items,
              (i) => i.area.area_id,
              (i) =>
                html`<rs-room-card
                  .hass=${this.hass}
                  .area=${i.area}
                  .config=${i.config}
                  .climateEntityCount=${i.climateEntityCount}
                  .tempSensorCount=${i.tempSensorCount}
                  .controlMode=${this.controlMode}
                  .climateControlActive=${this.climateControlActive}
                ></rs-room-card>`,
            )}
          </div>
        `,
      )}
    `;
  }

  private _renderPills(visible: AreaInfo[]) {
    const l = this.hass.language;
    const s = this.summary;
    const configured = visible.filter((i) => i.config);
    const heating = visible.filter((i) => i.config?.live?.mode === "heating").length;
    const cooling = visible.filter((i) => i.config?.live?.mode === "cooling").length;
    const mold = visible.filter(
      (i) =>
        i.config?.live?.mold_risk_level === "warning" ||
        i.config?.live?.mold_risk_level === "critical",
    ).length;
    const level = s.priceEntity ? s.priceStatus?.level : null;
    const vacationUntil =
      s.vacationActive && s.vacationUntil && s.vacationUntil < VACATION_SENTINEL
        ? new Intl.DateTimeFormat(l, { day: "numeric", month: "short" }).format(
            new Date(s.vacationUntil * 1000),
          )
        : null;

    const pills = [
      configured.length
        ? html`<rs-pill icon="mdi:home-thermometer-outline"
            ><b>${configured.length}</b> ${localize("panel.pill.rooms", l)}</rs-pill
          >`
        : nothing,
      configured.length
        ? html`<rs-pill icon="mdi:fire" .tone=${heating ? "heat" : "default"}
            ><b>${heating}</b> ${localize("panel.pill.heating", l)}</rs-pill
          >`
        : nothing,
      cooling
        ? html`<rs-pill icon="mdi:snowflake" tone="cool"
            ><b>${cooling}</b> ${localize("panel.pill.cooling", l)}</rs-pill
          >`
        : nothing,
      s.outdoorTemp != null
        ? html`<rs-pill icon="mdi:thermometer"
            >${localize("panel.pill.outdoor", l)}
            <b>${formatTempLocale(s.outdoorTemp, this.hass)} ${tempUnit(this.hass)}</b></rs-pill
          >`
        : nothing,
      level
        ? html`<rs-pill
            icon="mdi:cash-clock"
            .tone=${level === "cheap" ? "ok" : level === "expensive" ? "warn" : "default"}
            >${localize("panel.pill.price", l)}
            <b>${localize(PRICE_LEVEL_KEYS[level], l)}</b></rs-pill
          >`
        : nothing,
      s.vacationActive
        ? html`<rs-pill icon="mdi:airplane" tone="ok"
            >${
              vacationUntil
                ? localize("panel.pill.vacation_until", l, { date: vacationUntil })
                : localize("panel.stat.vacation", l)
            }</rs-pill
          >`
        : nothing,
      s.presenceEnabled && !s.anyoneHome
        ? html`<rs-pill icon="mdi:home-export-outline">${localize("panel.pill.away", l)}</rs-pill>`
        : nothing,
      mold
        ? html`<rs-pill icon="mdi:water-alert" tone="warn"
            ><b>${mold}</b> ${localize("panel.pill.mold", l)}</rs-pill
          >`
        : nothing,
    ].filter((p) => p !== nothing);
    if (!pills.length) return nothing;
    return html`<div class="pills" role="list" aria-label=${localize("panel.pill.label", l)}>
      ${pills.map((p) => html`<span role="listitem">${p}</span>`)}
    </div>`;
  }

  private _requestEdit() {
    this.dispatchEvent(new CustomEvent("edit-requested", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-dashboard": RsDashboard;
  }
}

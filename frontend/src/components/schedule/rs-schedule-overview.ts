/**
 * rs-schedule-overview – Every Home Assistant schedule helper with the rooms that use it.
 * Room schedules (and helpers no room uses) open the schedule editor; cover schedules only
 * Home Assistant's more-info, the editor has no cover position (a force block without one
 * would close to 0 %). Admins can create a schedule here without a room.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { isAdmin } from "../../utils/schedule-api";
import { formatClock, haTimeZone, sameDayInZone } from "../../utils/analytics-time";
import { openEntityInfo } from "../../utils/events";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-card";
import "../shared/rs-list-row";
import "./rs-schedule-create";

interface ScheduleItem {
  entityId: string;
  name: string;
  rooms: string[];
  coverRooms: string[];
}

@customElement("rs-schedule-overview")
export class RsScheduleOverview extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};

  @state() private _creating = false;

  private _items(): ScheduleItem[] {
    const lang = this.hass.language;
    const roomName = (id: string) =>
      this.rooms[id]?.display_name || this.hass.areas?.[id]?.name || id;
    return Object.keys(this.hass.states)
      .filter((id) => id.startsWith("schedule."))
      .map((entityId) => {
        const uses = (list: { entity_id: string }[] | undefined) =>
          (list ?? []).some((s) => s.entity_id === entityId);
        const rooms = Object.values(this.rooms);
        return {
          entityId,
          name: (this.hass.states[entityId].attributes?.friendly_name as string) || entityId,
          rooms: rooms.filter((r) => uses(r.schedules)).map((r) => roomName(r.area_id)),
          coverRooms: rooms.filter((r) => uses(r.cover_schedules)).map((r) => roomName(r.area_id)),
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name, lang));
  }

  render() {
    const l = this.hass.language;
    const items = this._items();
    // Only for covers means not for the editor; a helper no room uses yet may become either
    const covers = items.filter((i) => i.coverRooms.length && !i.rooms.length);
    const rooms = items.filter((i) => !covers.includes(i));
    return html`
      <rs-list-card .heading=${localize("schedules.rooms_title", l)}>
        ${
          rooms.length
            ? rooms.map((i) => this._renderRow(i, false))
            : html`<p class="empty">${localize("schedules.empty", l)}</p>`
        }
        ${isAdmin(this.hass) ? this._renderCreate() : nothing}
      </rs-list-card>
      ${
        covers.length
          ? html`<rs-list-card .heading=${localize("schedules.covers_title", l)}>
              ${covers.map((i) => this._renderRow(i, true))}
            </rs-list-card>`
          : nothing
      }
      <p class="note">${localize("schedules.note", l)}</p>
    `;
  }

  private _renderRow(item: ScheduleItem, cover: boolean) {
    const l = this.hass.language;
    const used = cover ? item.coverRooms : item.rooms;
    const on = this.hass.states[item.entityId]?.state === "on";
    return html`<rs-list-row
      clickable
      chevron
      wrap
      icon=${cover ? "mdi:blinds" : "mdi:calendar-clock"}
      icon-label=${localize("detail.more_info", l)}
      .iconColor=${on ? "var(--primary-color)" : ""}
      .heading=${item.name}
      .secondary=${[
        used.length ? used.join(", ") : localize("schedules.unused", l),
        this._stateText(item.entityId),
      ]
        .filter(Boolean)
        .join(" · ")}
      @row-click=${() => (cover ? this._moreInfo(item.entityId) : this._open(item.entityId))}
      @icon-click=${() => this._moreInfo(item.entityId)}
    ></rs-list-row>`;
  }

  /** "On until 22:00", "Off until Mon 06:00"; just on/off without a next change. */
  private _stateText(entityId: string): string {
    const l = this.hass.language;
    const st = this.hass.states[entityId];
    if (!st || (st.state !== "on" && st.state !== "off")) return "";
    const on = st.state === "on";
    const next = Date.parse(String(st.attributes?.next_event ?? ""));
    if (!Number.isFinite(next)) return localize(on ? "schedules.on" : "schedules.off", l);
    const zone = haTimeZone(this.hass);
    const time = sameDayInZone(next, Date.now(), zone)
      ? formatClock(next, l, zone)
      : new Intl.DateTimeFormat(l, {
          weekday: "short",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: zone,
        }).format(next);
    return localize(on ? "schedules.on_until" : "schedules.off_until", l, { time });
  }

  private _renderCreate() {
    const l = this.hass.language;
    if (!this._creating) {
      return html`<rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("schedule_editor.create", l)}
        @row-click=${() => (this._creating = true)}
      ></rs-list-row>`;
    }
    return html`<div class="create">
      <rs-schedule-create
        .hass=${this.hass}
        @create-cancelled=${() => (this._creating = false)}
        @schedule-created=${(e: CustomEvent<{ entityId: string }>) => {
          this._creating = false;
          this._open(e.detail.entityId);
        }}
      ></rs-schedule-create>
    </div>`;
  }

  private _open(entityId: string) {
    this.dispatchEvent(
      new CustomEvent("open-schedule-editor", {
        detail: { entityId, areaId: "" },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _moreInfo(entityId: string) {
    openEntityInfo(this, entityId);
  }

  static styles = [
    tokens,
    css`
      :host {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-4);
        max-width: 760px;
        margin: 0 auto;
      }
      .empty {
        margin: 0;
        padding: var(--rs-space-2) var(--rs-space-4) var(--rs-space-3);
        color: var(--secondary-text-color);
        font-size: var(--rs-font-md);
      }
      .create {
        padding: 0 var(--rs-space-4);
      }
      .note {
        margin: 0;
        padding: 0 var(--rs-space-1);
        font-size: 13px;
        line-height: 1.5;
        color: var(--secondary-text-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-overview": RsScheduleOverview;
  }
}

import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import type { HomeAssistant } from "../../types";
import { floorGroups, orderWithGroup, type AreaInfo, type FloorGroup } from "../../utils/dashboard";
import { DragReorderController } from "../../utils/drag-reorder";
import { localize } from "../../utils/localize";
import { roomKind, roomStateInfo } from "../../utils/room-state";
import { formatTempLocale, tempUnit } from "../../utils/temperature";
import { tokens, srOnly } from "../../styles/tokens";
import { dashboardStyles } from "./dashboard-styles";
import type { RsMenuItem } from "../shared/rs-menu";
import "./rs-room-card";
import "../shared/rs-icon-button";
import "../shared/rs-menu";
import "../shared/rs-toggle-row";

const NARROW_QUERY = "(max-width: 599px)";
/** Group key for areas without a floor (FloorGroup.key null) in data attributes. */
const NO_FLOOR = "__none__";

const groupAttr = (key: string | null) => (key === null ? NO_FLOOR : key);

/**
 * Edit mode of the rooms tab: drag cards into a new order (within their floor), hide and
 * show rooms, group by floor. From 600 px the real cards (WYSIWYG), below compact tiles.
 * Fires `room-order-changed` {order}, `room-hidden-changed` {areaId, hidden},
 * `group-by-floor-changed` {value} and `area-selected` {areaId}; the panel persists.
 */
@customElement("rs-dashboard-edit")
export class RsDashboardEdit extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public infos: AreaInfo[] = [];
  @property({ attribute: false }) public hiddenRooms: string[] = [];
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Boolean }) public climateControlActive = true;

  @state() private _narrow = window.matchMedia(NARROW_QUERY).matches;

  private _mq = window.matchMedia(NARROW_QUERY);
  private _groups: FloorGroup[] = [];

  private _drag = new DragReorderController(this, {
    groupIds: (group) =>
      this._groups.find((g) => groupAttr(g.key) === group)?.items.map((i) => i.area.area_id) ?? [],
    onReorder: (group, ids) => {
      const key = group === NO_FLOOR ? null : group;
      this._fire("room-order-changed", { order: orderWithGroup(this._groups, key, ids) });
    },
    announce: (id, position, total) =>
      localize("panel.edit.moved", this.hass.language, {
        name: this._name(id),
        position,
        total,
      }),
  });

  static styles = [
    tokens,
    srOnly,
    dashboardStyles,
    css`
      .intro {
        display: flex;
        align-items: center;
        gap: 14px;
        flex-wrap: wrap;
        padding: 12px 16px;
        margin-bottom: 12px;
      }

      .intro > ha-icon {
        --mdc-icon-size: 26px;
        color: var(--primary-color);
        flex: none;
      }

      .intro .txt {
        flex: 1;
        min-width: min(220px, 100%);
        font-size: 13px;
        color: var(--secondary-text-color);
        line-height: 1.45;
      }

      .intro .txt b {
        display: block;
        margin-bottom: 2px;
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .intro rs-toggle-row {
        flex: 0 1 auto;
        min-width: min(240px, 100%);
      }

      /* ----- WYSIWYG (>= 600 px) ----- */
      .editwrap {
        position: relative;
        border-radius: var(--rs-radius);
        user-select: none;
        -webkit-user-select: none;
        min-width: 0;
      }

      .editwrap rs-room-card {
        pointer-events: none;
      }

      .editwrap.hiddenroom rs-room-card {
        opacity: 0.35;
      }

      .eover {
        position: absolute;
        inset: 0;
        border-radius: var(--rs-radius);
        border: 2px dashed color-mix(in srgb, var(--primary-color) 55%, transparent);
        background: color-mix(in srgb, var(--card-background-color, transparent) 18%, transparent);
        cursor: grab;
        box-sizing: border-box;
      }

      .eover:hover {
        background: color-mix(in srgb, var(--primary-color) 5%, transparent);
      }

      .grab {
        position: absolute;
        top: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 88px;
        height: 32px;
        display: grid;
        place-items: center;
        border: none;
        background: none;
        padding: 0;
        cursor: grab;
        touch-action: none;
        border-radius: 8px;
      }

      .grab::before {
        content: "";
        width: 40px;
        height: 5px;
        border-radius: 3px;
        background: var(--secondary-text-color);
        opacity: 0.6;
      }

      @media (pointer: coarse) {
        .grab {
          height: var(--rs-touch);
          width: 120px;
        }
      }

      .grab:focus-visible,
      .handle:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }

      .ectl {
        position: absolute;
        top: 8px;
        right: 8px;
        display: flex;
        gap: 6px;
        --rs-icon-button-background: var(--card-background-color);
      }

      .ectl rs-icon-button,
      .ectl rs-menu {
        border-radius: 50%;
        box-shadow:
          0 0 0 1px var(--divider-color),
          0 1px 3px rgb(0 0 0 / 14%);
        background: var(--card-background-color);
      }

      .hidtag {
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 32px;
        padding: 0 14px;
        border-radius: 16px;
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        font-size: 13px;
        font-weight: 500;
        white-space: nowrap;
        --mdc-icon-size: 18px;
        pointer-events: none;
      }

      .placeholder-slot {
        border: 2px dashed var(--primary-color);
        background: var(--rs-fill-primary);
      }

      .placeholder-slot > * {
        visibility: hidden;
      }

      /* ----- compact tiles (< 600 px) ----- */
      .egrid {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: 8px;
      }

      .etile {
        display: flex;
        align-items: center;
        gap: 8px;
        height: 68px;
        padding: 0 4px 0 2px;
        box-sizing: border-box;
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: var(--rs-radius);
        user-select: none;
        -webkit-user-select: none;
        min-width: 0;
      }

      .handle {
        width: 40px;
        height: 56px;
        flex: none;
        display: grid;
        place-items: center;
        border: none;
        background: none;
        padding: 0;
        border-radius: 8px;
        color: var(--secondary-text-color);
        cursor: grab;
        touch-action: none;
        --mdc-icon-size: 22px;
      }

      .handle:hover {
        background: var(--rs-fill);
        color: var(--primary-text-color);
      }

      .echip {
        width: 36px;
        height: 36px;
        flex: none;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: var(--rs-fill-strong);
        color: var(--secondary-text-color);
        --mdc-icon-size: 20px;
      }

      .echip.heat {
        background: color-mix(in srgb, var(--rs-heat) 16%, transparent);
        color: var(--rs-heat);
      }

      .echip.cool {
        background: color-mix(in srgb, var(--rs-cool) 16%, transparent);
        color: var(--rs-cool);
      }

      .etile .txt {
        flex: 1;
        min-width: 0;
      }

      .etile .name,
      .etile .sec {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .etile .name {
        font-weight: 500;
      }

      .etile .sec {
        font-size: 12px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .etile.hiddenroom .echip,
      .etile.hiddenroom .txt {
        opacity: 0.45;
      }

      /* ----- dragging ----- */
      .ghost {
        position: fixed;
        top: 0;
        left: 0;
        z-index: 50;
        pointer-events: none;
        cursor: grabbing;
        border-radius: var(--rs-radius);
        box-shadow: var(--rs-shadow-lift);
      }

      .ghost .eover {
        border-style: solid;
        border-color: var(--primary-color);
      }

      .ghost .etile {
        border-color: var(--primary-color);
        height: 100%;
      }

      .edit-foot {
        display: flex;
        align-items: flex-start;
        gap: 6px;
        margin: 16px 4px 0;
        font-size: 12px;
        color: var(--secondary-text-color);
        --mdc-icon-size: 16px;
      }

      .edit-foot ha-icon {
        flex: none;
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    this._mq.addEventListener("change", this._onMq);
    this._narrow = this._mq.matches;
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._mq.removeEventListener("change", this._onMq);
  }

  private _onMq = () => {
    this._drag.cancel();
    this._narrow = this._mq.matches;
  };

  protected willUpdate(): void {
    this._groups = floorGroups(this.infos, this.hass, this.groupByFloor);
  }

  render() {
    const l = this.hass.language;
    const hiddenCount = this.infos.filter((i) => this.hiddenRooms.includes(i.area.area_id)).length;
    const dragging = this._drag.dragging;
    const ghostInfo = dragging ? this.infos.find((i) => i.area.area_id === dragging.id) : null;
    return html`
      <ha-card class="intro">
        <ha-icon icon="mdi:gesture-tap-hold" aria-hidden="true"></ha-icon>
        <div class="txt">
          <b>${localize("panel.edit_rooms", l)}</b>
          ${localize(this._narrow ? "panel.edit.intro_narrow" : "panel.edit.intro_wide", l)}
          ${hiddenCount ? localize("panel.edit.hidden_count", l, { count: hiddenCount }) : nothing}
        </div>
        <rs-toggle-row
          .label=${localize("settings.group_by_floor", l)}
          .checked=${this.groupByFloor}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("group-by-floor-changed", { value: e.detail })}
        ></rs-toggle-row>
      </ha-card>
      ${this._groups.map((g) => {
        const group = groupAttr(g.key);
        const byId = new Map(g.items.map((i) => [i.area.area_id, i]));
        const ids = this._drag.order(
          group,
          g.items.map((i) => i.area.area_id),
        );
        const items = ids.map((id) => byId.get(id)!).filter(Boolean);
        return html`
          ${
            g.name
              ? html`<h2 class="floor">${g.name} <span class="count">${g.items.length}</span></h2>`
              : nothing
          }
          <div class=${this._narrow ? "egrid" : "grid"}>
            ${repeat(
              items,
              (i) => i.area.area_id,
              (i, idx) =>
                this._narrow
                  ? this._renderTile(i, group, idx, items.length)
                  : this._renderEditCard(i, group, idx, items.length),
            )}
          </div>
        `;
      })}
      <div class="edit-foot">
        <ha-icon icon="mdi:information-outline" aria-hidden="true"></ha-icon>
        <span>${localize("panel.edit.footer", l)}</span>
      </div>
      <div class="sr-only" aria-live="polite">${this._drag.announcement}</div>
      ${
        dragging && ghostInfo
          ? html`<div class="ghost" data-drag-ghost aria-hidden="true">
              ${
                this._narrow
                  ? this._renderTile(ghostInfo, "", 0, 0, true)
                  : this._renderEditCard(ghostInfo, "", 0, 0, true)
              }
            </div>`
          : nothing
      }
    `;
  }

  private _name(id: string): string {
    const info = this.infos.find((i) => i.area.area_id === id);
    return info?.config?.display_name || info?.area.name || id;
  }

  private _menuItems(id: string, idx: number, total: number): RsMenuItem[] {
    const l = this.hass.language;
    return [
      {
        value: "earlier",
        label: localize("panel.edit.move_earlier", l),
        icon: "mdi:arrow-up",
        disabled: idx === 0,
      },
      {
        value: "later",
        label: localize("panel.edit.move_later", l),
        icon: "mdi:arrow-down",
        disabled: idx >= total - 1,
      },
      { value: "open", label: localize("panel.edit.open_room", l), icon: "mdi:arrow-right" },
    ];
  }

  private _controls(info: AreaInfo, group: string, idx: number, total: number) {
    const l = this.hass.language;
    const id = info.area.area_id;
    const name = this._name(id);
    const hidden = this.hiddenRooms.includes(id);
    return html`
      <rs-icon-button
        size="sm"
        .icon=${hidden ? "mdi:eye-off-outline" : "mdi:eye-outline"}
        .label=${localize(hidden ? "panel.edit.show_room" : "panel.edit.hide_room", l, { name })}
        @click=${() => this._fire("room-hidden-changed", { areaId: id, hidden: !hidden })}
      ></rs-icon-button>
      <rs-menu
        .label=${localize("panel.edit.more", l, { name })}
        .items=${this._menuItems(id, idx, total)}
        @menu-select=${(e: CustomEvent<{ value: string }>) =>
          this._onMenu(e.detail.value, group, id)}
      ></rs-menu>
    `;
  }

  private _renderEditCard(
    info: AreaInfo,
    group: string,
    idx: number,
    total: number,
    ghost = false,
  ) {
    const l = this.hass.language;
    const id = info.area.area_id;
    const hidden = this.hiddenRooms.includes(id);
    const placeholder = !ghost && this._drag.isPlaceholder(id);
    const name = this._name(id);
    return html`<div
      class="editwrap ${hidden ? "hiddenroom" : ""} ${placeholder ? "placeholder-slot" : ""}"
      data-drag-id=${ghost ? nothing : id}
      data-drag-group=${ghost ? nothing : group}
    >
      <rs-room-card
        preview
        .hass=${this.hass}
        .area=${info.area}
        .config=${info.config}
        .climateEntityCount=${info.climateEntityCount}
        .tempSensorCount=${info.tempSensorCount}
        .controlMode=${this.controlMode}
        .climateControlActive=${this.climateControlActive}
      ></rs-room-card>
      <div class="eover" data-drag-handle="mouse">
        <button
          type="button"
          class="grab"
          data-drag-handle
          data-drag-key
          aria-label=${localize("panel.edit.move_handle", l, { name })}
        ></button>
        ${
          hidden
            ? html`<span class="hidtag"
                ><ha-icon icon="mdi:eye-off-outline"></ha-icon
                >${localize("panel.edit.hidden", l)}</span
              >`
            : nothing
        }
        <span class="ectl">${ghost ? nothing : this._controls(info, group, idx, total)}</span>
      </div>
    </div>`;
  }

  private _renderTile(info: AreaInfo, group: string, idx: number, total: number, ghost = false) {
    const l = this.hass.language;
    const id = info.area.area_id;
    const hidden = this.hiddenRooms.includes(id);
    const placeholder = !ghost && this._drag.isPlaceholder(id);
    const name = this._name(id);
    const kind = roomKind(info.config, info.climateEntityCount);
    const st =
      kind === "controlled" ? roomStateInfo(info.config!, this.climateControlActive) : null;
    const temp = info.config?.live?.current_temp;
    const parts: string[] = [];
    if (hidden) parts.push(localize("panel.edit.hidden", l));
    else {
      if (temp != null) parts.push(`${formatTempLocale(temp, this.hass)} ${tempUnit(this.hass)}`);
      if (st) parts.push(localize(st.key, l));
      else if (kind === "outdoor") parts.push(localize("card.outdoor", l));
      else if (kind === "unconfigured") parts.push(localize("card.not_set_up", l));
      else if (kind === "empty") parts.push(localize("card.no_climate", l));
    }
    return html`<div
      class="etile ${hidden ? "hiddenroom" : ""} ${placeholder ? "placeholder-slot" : ""}"
      data-drag-id=${ghost ? nothing : id}
      data-drag-group=${ghost ? nothing : group}
    >
      <button
        type="button"
        class="handle"
        data-drag-handle
        data-drag-key
        aria-label=${localize("panel.edit.move_handle", l, { name })}
      >
        <ha-icon icon="mdi:drag"></ha-icon>
      </button>
      <span
        class="echip ${st?.tone === "heat" ? "heat" : st?.tone === "cool" ? "cool" : ""}"
        aria-hidden="true"
      >
        <ha-icon .icon=${info.area.icon || "mdi:texture-box"}></ha-icon>
      </span>
      <span class="txt">
        <div class="name">${name}</div>
        <div class="sec">${parts.join(" · ")}</div>
      </span>
      ${ghost ? nothing : this._controls(info, group, idx, total)}
    </div>`;
  }

  private _onMenu(value: string, group: string, id: string) {
    if (value === "open") {
      this._fire("area-selected", { areaId: id });
      return;
    }
    this._drag.moveBy(group, id, value === "earlier" ? -1 : 1);
  }

  private _fire(type: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-dashboard-edit": RsDashboardEdit;
  }
}

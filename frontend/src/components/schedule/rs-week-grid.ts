import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { tokens, srOnly } from "../../styles/tokens";
import {
  DAY_MINUTES,
  SNAP_MINUTES,
  createBlock,
  hm,
  moveBlock,
  resizeBlock,
  snap,
  weeksEqual,
  type ScheduleBlock,
  type Week,
} from "../../utils/schedule-week";
import type { RsMenuItem } from "../shared/rs-menu";
import "../shared/rs-menu";

export interface BlockLook {
  /** Text inside a wide block ("Komfort", "21–24°"). */
  label: string;
  /** Text for narrow blocks ("21°"); empty shows nothing. */
  short: string;
  /** Full description for screen readers and the popover title. */
  description: string;
  color: string;
  /** Strength of the fill in percent. */
  tint: number;
}

type DragMode = "create" | "move" | "start" | "end";

interface Drag {
  mode: DragMode;
  day: number;
  index: number;
  pointerId: number;
  originX: number;
  originMinute: number;
  blockStart: number;
  track: HTMLElement;
  moved: boolean;
}

/** Pixels a pointer must travel before a press counts as a drag (else it is a click). */
const DRAG_THRESHOLD = 4;
const AXIS_HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

/**
 * Desktop week grid: Monday to Sunday rows on a 0-24 h axis. Dragging on free space creates a
 * block, dragging a block moves it, its edges change start or end (15-min snap, stopped by the
 * neighbours). Blocks are buttons: arrows move, Shift+arrows change the end, Enter opens,
 * Delete removes. Fires `week-change` `{ week, day, index }`, `block-open`
 * `{ day, index, anchor }`, `block-delete` `{ day, index }` and `day-action` `{ day, action }`.
 */
@customElement("rs-week-grid")
export class RsWeekGrid extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public week: Week = [];
  @property({ type: Boolean }) public editable = false;
  @property({ type: Number }) public nowDay = -1;
  @property({ type: Number }) public nowMinute = -1;
  @property({ attribute: false }) public look!: (block: ScheduleBlock, day: number) => BlockLook;
  @property({ attribute: false }) public dayNames: string[] = [];
  @property({ attribute: false }) public dayShort: string[] = [];
  /** Block whose popover is open (highlighted). */
  @property({ attribute: false }) public selected: { day: number; index: number } | null = null;

  @state() private _preview: Week | null = null;
  @state() private _announce = "";

  private _drag: Drag | null = null;
  private _suppressClick = false;

  static styles = [
    tokens,
    srOnly,
    css`
      :host {
        display: block;
      }

      .grid {
        display: grid;
        grid-template-columns: 44px minmax(0, 1fr) var(--rs-touch);
        column-gap: var(--rs-space-2);
        row-gap: var(--rs-space-2);
        align-items: center;
      }

      .axis {
        grid-column: 2;
        position: relative;
        height: 18px;
        font-size: var(--rs-font-xs);
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .axis span {
        position: absolute;
        top: 0;
        transform: translateX(-50%);
      }

      .axis span:first-child {
        transform: none;
      }

      .axis span.last {
        transform: translateX(-100%);
      }

      .axis .now-label {
        color: var(--primary-text-color);
        font-weight: 500;
        background: var(--rs-surface);
        padding: 0 2px;
      }

      .day {
        display: flex;
        flex-direction: column;
        font-size: var(--rs-font-md);
        line-height: 1.2;
      }

      .day.today {
        color: var(--primary-color);
        font-weight: 500;
      }

      .day small {
        font-size: var(--rs-font-xs);
        font-weight: 400;
      }

      .track {
        position: relative;
        height: 40px;
        border-radius: var(--rs-radius-sm);
        background-color: var(--rs-fill);
        background-image: repeating-linear-gradient(
          to right,
          transparent 0 calc(12.5% - 1px),
          var(--rs-border) calc(12.5% - 1px) 12.5%
        );
        touch-action: pan-y;
        user-select: none;
        -webkit-user-select: none;
      }

      .track.editable {
        cursor: crosshair;
      }

      .block {
        position: absolute;
        top: 3px;
        bottom: 3px;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 4px;
        padding: 0 6px;
        overflow: hidden;
        border: 1px solid color-mix(in srgb, var(--block-color) 55%, transparent);
        border-radius: 6px;
        background: color-mix(in srgb, var(--block-color) var(--block-tint), var(--rs-surface));
        color: var(--primary-text-color);
        font: inherit;
        font-size: var(--rs-font-sm);
        white-space: nowrap;
        text-overflow: ellipsis;
        cursor: default;
      }

      .editable .block {
        cursor: grab;
      }

      .block:focus-visible,
      .block.selected {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
        z-index: 1;
      }

      .block .text {
        overflow: hidden;
        text-overflow: ellipsis;
        pointer-events: none;
      }

      .edge {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 8px;
        cursor: ew-resize;
      }

      .edge.start {
        left: 0;
      }

      .edge.end {
        right: 0;
      }

      .edge::after {
        content: "";
        position: absolute;
        top: 30%;
        bottom: 30%;
        left: 3px;
        width: 2px;
        border-radius: 1px;
        background: var(--block-color);
        opacity: 0;
      }

      .block:hover .edge::after,
      .block:focus-visible .edge::after,
      .block.selected .edge::after {
        opacity: 0.9;
      }

      .now {
        position: absolute;
        top: -4px;
        bottom: -4px;
        width: 2px;
        margin-left: -1px;
        background: var(--primary-text-color);
        pointer-events: none;
        z-index: 2;
      }

      .dragging,
      .dragging * {
        cursor: grabbing !important;
      }
    `,
  ];

  /** The button of a block, to anchor the popover and to return the focus to. */
  public blockElement(day: number, index: number): HTMLElement | null {
    return this.renderRoot.querySelector<HTMLElement>(
      `.block[data-day="${day}"][data-index="${index}"]`,
    );
  }

  render() {
    const l = this.hass.language;
    const week = this._preview ?? this.week;
    const menuItems = (day: number): RsMenuItem[] => [
      { value: "add", label: localize("schedule_editor.add_block", l), icon: "mdi:plus" },
      {
        value: "copy",
        label: localize("schedule_editor.copy_day", l),
        icon: "mdi:content-copy",
        disabled: week[day].length === 0,
      },
      {
        value: "clear",
        label: localize("schedule_editor.clear_day", l),
        icon: "mdi:eraser",
        disabled: week[day].length === 0,
      },
    ];
    const showNow = this.nowDay >= 0 && this.nowMinute >= 0;
    const nowPct = (this.nowMinute / DAY_MINUTES) * 100;
    // The now label would collide with an hour label: hide hour labels close to it.
    const nearNow = (h: number) => showNow && Math.abs(h * 60 - this.nowMinute) < 75;
    return html`
      <div class="grid ${this._drag?.moved ? "dragging" : ""}">
        <div class="axis" aria-hidden="true">
          ${AXIS_HOURS.map(
            (h) =>
              html`<span
                class=${h === 24 ? "last" : ""}
                style="left:${(h / 24) * 100}%"
                ?hidden=${nearNow(h) && h !== 0 && h !== 24}
                >${h}</span
              >`,
          )}
          ${
            showNow
              ? html`<span class="now-label" style="left:${nowPct}%">${hm(this.nowMinute)}</span>`
              : nothing
          }
        </div>
        <span></span>
        ${week.map((blocks, day) => {
          const today = day === this.nowDay;
          return html`
            <div class="day ${today ? "today" : ""}">
              <span aria-hidden="true">${this.dayShort[day]}</span>
              <span class="sr-only">${this.dayNames[day]}</span>
              ${today ? html`<small>${localize("schedule_editor.today", l)}</small>` : nothing}
            </div>
            <div
              class="track ${this.editable ? "editable" : ""}"
              data-day=${day}
              role="group"
              aria-label=${this.dayNames[day]}
              @pointerdown=${this._onPointerDown}
              @pointermove=${this._onPointerMove}
              @pointerup=${this._onPointerUp}
              @pointercancel=${this._onPointerCancel}
            >
              ${blocks.map((b, index) => this._renderBlock(b, day, index))}
              ${today && showNow ? html`<span class="now" style="left:${nowPct}%"></span>` : nothing}
            </div>
            ${
              this.editable
                ? html`<rs-menu
                    .items=${menuItems(day)}
                    .label=${localize("schedule_editor.day_actions", l, {
                      day: this.dayNames[day],
                    })}
                    @menu-select=${(e: CustomEvent<{ value: string }>) =>
                      this._fire("day-action", { day, action: e.detail.value })}
                  ></rs-menu>`
                : html`<span></span>`
            }
          `;
        })}
      </div>
      <div class="sr-only" aria-live="polite">${this._announce}</div>
    `;
  }

  private _renderBlock(block: ScheduleBlock, day: number, index: number) {
    const look = this.look(block, day);
    const length = block.end - block.start;
    const text = length >= 120 ? look.label : length >= 60 ? look.short : "";
    const selected = this.selected?.day === day && this.selected?.index === index;
    const style =
      `left:${(block.start / DAY_MINUTES) * 100}%;` +
      `width:${(length / DAY_MINUTES) * 100}%;` +
      `--block-color:${look.color};--block-tint:${look.tint}%`;
    if (!this.editable) {
      return html`<div
        class="block"
        style=${style}
        role="img"
        aria-label=${look.description}
        data-day=${day}
        data-index=${index}
      >
        <span class="text">${text}</span>
      </div>`;
    }
    return html`<button
      type="button"
      class="block ${selected ? "selected" : ""}"
      style=${style}
      data-day=${day}
      data-index=${index}
      aria-label=${look.description}
      aria-haspopup="dialog"
      @click=${(e: Event) => this._onBlockClick(e, day, index)}
      @keydown=${(e: KeyboardEvent) => this._onBlockKey(e, day, index)}
    >
      <span class="edge start" data-edge="start" aria-hidden="true"></span>
      <span class="text">${text}</span>
      <span class="edge end" data-edge="end" aria-hidden="true"></span>
    </button>`;
  }

  // ─── Pointer ────────────────────────────────────────────────────────

  private _minuteAt(track: HTMLElement, clientX: number): number {
    const rect = track.getBoundingClientRect();
    const ratio = (clientX - rect.left) / Math.max(1, rect.width);
    return Math.max(0, Math.min(DAY_MINUTES, ratio * DAY_MINUTES));
  }

  private _onPointerDown(e: PointerEvent) {
    if (!this.editable || e.button !== 0 || this._drag) return;
    this._suppressClick = false;
    const track = e.currentTarget as HTMLElement;
    const day = Number(track.dataset.day);
    const target = e.composedPath()[0] as HTMLElement;
    const blockEl = target.closest<HTMLElement>(".block");
    const minute = this._minuteAt(track, e.clientX);
    let mode: DragMode = "create";
    let index = -1;
    let blockStart = 0;
    if (blockEl) {
      index = Number(blockEl.dataset.index);
      blockStart = this.week[day][index]?.start ?? 0;
      const edge = target.dataset.edge as "start" | "end" | undefined;
      mode = edge ?? "move";
    }
    this._drag = {
      mode,
      day,
      index,
      pointerId: e.pointerId,
      originX: e.clientX,
      originMinute: minute,
      blockStart,
      track,
      moved: false,
    };
  }

  private _onPointerMove(e: PointerEvent) {
    const drag = this._drag;
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (!drag.moved && Math.abs(e.clientX - drag.originX) < DRAG_THRESHOLD) return;
    if (!drag.moved) {
      // Captured only once it is a drag: a captured press would send the click to the track.
      drag.track.setPointerCapture(e.pointerId);
      drag.moved = true;
    }
    const minute = this._minuteAt(drag.track, e.clientX);
    const { day, index } = drag;
    let next: Week | null = null;
    if (drag.mode === "move") {
      next = moveBlock(this.week, day, index, snap(drag.blockStart + minute - drag.originMinute));
    } else if (drag.mode === "start" || drag.mode === "end") {
      next = resizeBlock(this.week, day, index, drag.mode, snap(minute));
    } else {
      const anchor = Math.floor(drag.originMinute / SNAP_MINUTES) * SNAP_MINUTES;
      next = createBlock(this.week, day, anchor, snap(minute))?.week ?? null;
    }
    this._preview = next;
  }

  private _onPointerUp(e: PointerEvent) {
    const drag = this._drag;
    if (!drag || e.pointerId !== drag.pointerId) return;
    this._drag = null;
    const preview = this._preview;
    this._preview = null;
    if (!drag.moved) return;
    // The click that follows a drag must not open the popover.
    this._suppressClick = drag.mode !== "create";
    if (!preview || weeksEqual(preview, this.week)) return;
    let index = drag.index;
    if (drag.mode === "create") {
      index = preview[drag.day].findIndex(
        (b) => !this.week[drag.day].some((o) => o.start === b.start && o.end === b.end),
      );
    } else {
      const moved = preview[drag.day].find(
        (b) => !this.week[drag.day].some((o) => o.start === b.start && o.end === b.end),
      );
      index = moved ? preview[drag.day].indexOf(moved) : index;
    }
    this._fire("week-change", {
      week: preview,
      day: drag.day,
      index,
      created: drag.mode === "create",
    });
    const block = preview[drag.day][index];
    if (block) this._announce = `${this.dayNames[drag.day]} ${hm(block.start)}–${hm(block.end)}`;
  }

  private _onPointerCancel() {
    this._drag = null;
    this._preview = null;
  }

  // ─── Click and keyboard ─────────────────────────────────────────────

  private _onBlockClick(e: Event, day: number, index: number) {
    e.stopPropagation();
    if (this._suppressClick) {
      this._suppressClick = false;
      return;
    }
    this._fire("block-open", { day, index, anchor: e.currentTarget });
  }

  private _onBlockKey(e: KeyboardEvent, day: number, index: number) {
    const block = this.week[day][index];
    if (!block) return;
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      this._fire("block-delete", { day, index });
      return;
    }
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const delta = e.key === "ArrowRight" ? SNAP_MINUTES : -SNAP_MINUTES;
    const next = e.shiftKey
      ? resizeBlock(this.week, day, index, "end", block.end + delta)
      : moveBlock(this.week, day, index, block.start + delta);
    if (next === this.week) return;
    const moved = next[day][index];
    this._announce = `${this.dayNames[day]} ${hm(moved.start)}–${hm(moved.end)}`;
    this._fire("week-change", { week: next, day, index, created: false });
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-week-grid": RsWeekGrid;
  }
}

import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens, srOnly } from "../../styles/tokens";
import { DAY_MINUTES, type ScheduleBlock } from "../../utils/schedule-week";

const AXIS_HOURS = [0, 6, 12, 18, 24];

/**
 * One day of a schedule as a 24-hour bar: blocks, a now marker and an hour axis. Display only;
 * `label` is the text alternative (the blocks as times), the bar itself is hidden from screen readers.
 */
@customElement("rs-day-timeline")
export class RsDayTimeline extends LitElement {
  @property({ attribute: false }) public blocks: ScheduleBlock[] = [];
  /** Minute of the day for the now marker, -1 = none. */
  @property({ type: Number }) public nowMinute = -1;
  @property({ type: String }) public color = "var(--rs-heat)";
  @property({ type: String }) public label = "";

  static styles = [
    tokens,
    srOnly,
    css`
      :host {
        display: block;
        margin-top: var(--rs-space-2);
      }

      .track {
        position: relative;
        height: 10px;
        border-radius: 5px;
        background: var(--rs-fill-strong);
      }

      .block {
        position: absolute;
        top: 0;
        bottom: 0;
        min-width: 3px;
        box-sizing: border-box;
        border-radius: 5px;
        border: 1px solid color-mix(in srgb, var(--block-color) 70%, transparent);
        background: color-mix(in srgb, var(--block-color) 45%, var(--rs-surface));
      }

      .now {
        position: absolute;
        top: -3px;
        bottom: -3px;
        width: 2px;
        margin-left: -1px;
        border-radius: 1px;
        background: var(--primary-text-color);
      }

      .axis {
        position: relative;
        height: 14px;
        margin-top: 2px;
        font-size: var(--rs-font-xs);
        line-height: 14px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .axis span {
        position: absolute;
        transform: translateX(-50%);
        white-space: nowrap;
      }

      .axis span.first {
        transform: none;
      }

      .axis span.last {
        transform: translateX(-100%);
      }
    `,
  ];

  render() {
    const pct = (minute: number) => `${(minute / DAY_MINUTES) * 100}%`;
    return html`
      <span class="sr-only">${this.label}</span>
      <div class="track" aria-hidden="true" style="--block-color:${this.color}">
        ${this.blocks.map(
          (b) =>
            html`<span
              class="block"
              style="left:${pct(b.start)};width:${pct(b.end - b.start)}"
            ></span>`,
        )}
        ${
          this.nowMinute >= 0
            ? html`<span class="now" style="left:${pct(this.nowMinute)}"></span>`
            : nothing
        }
      </div>
      <div class="axis" aria-hidden="true">
        ${AXIS_HOURS.map(
          (h) =>
            html`<span
              class=${h === 0 ? "first" : h === 24 ? "last" : ""}
              style="left:${pct(h * 60)}"
              >${h}</span
            >`,
        )}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-day-timeline": RsDayTimeline;
  }
}

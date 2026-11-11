import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { CoverScheduleEntry } from "../types";
import { localize } from "../utils/localize";
import { formatPercent } from "../utils/format";
import { RsScheduleBase } from "./shared/rs-schedule-base";
import { inputStyles } from "../styles/input-styles";
import { tokens } from "../styles/tokens";
import "./shared/rs-list-row";
import "./shared/rs-segmented";

/** Cover schedules of a room (edit mode only): order, mode per schedule, selector. */
@customElement("rs-cover-schedule")
export class RsCoverSchedule extends RsScheduleBase {
  @property({ attribute: false }) public schedules: CoverScheduleEntry[] = [];

  static styles = [
    tokens,
    RsScheduleBase.sharedStyles,
    inputStyles,
    css`
      .entries {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-2);
        margin-bottom: var(--rs-space-3);
      }

      .entries rs-list-row {
        margin-inline: calc(-1 * var(--rs-form-inline, 16px));
        --rs-list-row-padding: var(--rs-form-inline, 16px);
      }

      .entries rs-list-row.unreachable {
        opacity: 0.6;
      }

      rs-segmented {
        display: block;
        padding-inline-start: calc(40px + var(--rs-space-4));
      }

      @container (max-width: 520px) {
        rs-segmented {
          padding-inline-start: 0;
        }
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    const count = this.schedules.length;
    const usedIds = new Set(this.schedules.map((s) => s.entity_id));

    return html`
      ${
        count > 0
          ? html`<div class="entries">
              ${this.schedules.map((entry, index) => this._renderEntry(entry, index, count))}
            </div>`
          : nothing
      }
      ${this._renderAddRow(
        localize("covers.add_schedule", l),
        this._getAvailableEntities(usedIds),
        (eid) => this._addSchedule(eid),
        localize("covers.schedule_create_link", l),
      )}
      ${this._renderSelectorSection(
        count,
        localize("covers.schedule_selector", l),
        localize("covers.schedule_selector_hint", l),
        localize("covers.schedule_selector_warning", l),
        (value) => this._emitSelectorChanged(value),
      )}
    `;
  }

  private _renderEntry(entry: CoverScheduleEntry, index: number, count: number) {
    const l = this.hass.language;
    const state = this._getScheduleState(index, count);
    const name = this._getFriendlyName(entry.entity_id);
    const mode = entry.mode ?? "force";
    const pos = mode === "force" ? this._getBlockPosition(entry.entity_id) : null;
    const secondary = [
      count >= 2 ? `#${index + 1}` : "",
      this._statusText(state, l),
      pos !== null ? formatPercent(pos, this.hass) : "",
    ]
      .filter(Boolean)
      .join(" · ");
    return html`<div>
      <rs-list-row
        class=${state}
        single-line
        icon="mdi:calendar-clock"
        icon-label=${localize("detail.more_info", l)}
        .heading=${name}
        .secondary=${secondary}
        .status=${state === "active" ? "on" : "off"}
        @icon-click=${() => this._openEntityInfo(entry.entity_id)}
      >
        <span slot="end"
          >${this._renderScheduleControls(
            index,
            count,
            (i, dir) => this._moveSchedule(i, dir),
            (i) => this._removeSchedule(i),
            name,
          )}</span
        >
      </rs-list-row>
      <rs-segmented
        wrap
        size="sm"
        .label=${name}
        .options=${[
          { value: "force", label: localize("covers.schedule_mode_force", l) },
          { value: "gate", label: localize("covers.schedule_mode_gate", l) },
        ]}
        .value=${mode}
        @value-changed=${(e: CustomEvent<{ value: string }>) =>
          this._updateMode(index, e.detail.value as "force" | "gate")}
      ></rs-segmented>
    </div>`;
  }

  /** Position from the schedule's running block (`position` in its data). */
  private _getBlockPosition(entityId: string): number | null {
    const st = this.hass?.states?.[entityId];
    if (!st || st.state !== "on") return null;
    const pos = st.attributes?.position;
    return pos != null && Number.isFinite(Number(pos)) ? Number(pos) : null;
  }

  private _statusText(state: "active" | "inactive" | "unreachable", l: string): string {
    if (state === "active") return localize("covers.schedule_state_active", l);
    if (state === "unreachable") return localize("covers.schedule_state_unreachable", l);
    return localize("covers.schedule_state_inactive", l);
  }

  private _addSchedule(entityId: string) {
    this._emitSchedules([...this.schedules, { entity_id: entityId, mode: "force" }]);
  }

  /** Removing asks nothing; the room page offers Undo, like for the room's schedules. */
  private _removeSchedule(index: number) {
    this._emitSchedules(this.schedules.filter((_, i) => i !== index));
  }

  private _moveSchedule(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= this.schedules.length) return;
    const next = [...this.schedules];
    [next[index], next[target]] = [next[target], next[index]];
    this._emitSchedules(next);
  }

  private _updateMode(index: number, mode: "force" | "gate") {
    const next = this.schedules.map((entry, i) => (i === index ? { ...entry, mode } : entry));
    this._emitSchedules(next);
  }

  private _emitSchedules(value: CoverScheduleEntry[]) {
    this.dispatchEvent(
      new CustomEvent("cover-schedules-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _emitSelectorChanged(value: string) {
    this.dispatchEvent(
      new CustomEvent("cover-schedule-selector-changed", {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-cover-schedule": RsCoverSchedule;
  }
}

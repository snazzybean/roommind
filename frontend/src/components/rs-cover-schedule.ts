import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { CoverScheduleEntry } from "../types";
import { localize } from "../utils/localize";
import { RsScheduleBase } from "./shared/rs-schedule-base";

@customElement("rs-cover-schedule")
export class RsCoverSchedule extends RsScheduleBase {
  @property({ attribute: false }) public schedules: CoverScheduleEntry[] = [];

  static styles = [RsScheduleBase.sharedStyles, css`
    .pos-badge {
      font-size: 0.8em; padding: 1px 6px; border-radius: 10px;
      background: var(--primary-color); color: var(--text-primary-color);
      flex-shrink: 0;
    }
  `];

  render() {
    return this.editing ? this._renderEdit() : this._renderView();
  }

  private _renderView() {
    const l = this.hass.language;
    if (this.schedules.length === 0) return nothing;

    const hasMultiple = this.schedules.length >= 2;

    return html`
      <div class="schedule-list">
        ${this.schedules.map((entry, index) => {
          const state = this._getScheduleState(index, this.schedules.length);
          const pos = this._getBlockPosition(entry.entity_id);
          return html`
            <div class="schedule-row ${state}">
              ${hasMultiple ? html`<span class="schedule-number">${index + 1}</span>` : nothing}
              <span class="schedule-status-dot"></span>
              <span class="schedule-name schedule-link"
                @click=${() => this._openEntityInfo(entry.entity_id)}
              >${this._getFriendlyName(entry.entity_id)}</span>
              ${pos !== null ? html`<span class="pos-badge">${pos}%</span>` : nothing}
              <span class="schedule-status">${this._statusText(state, l)}</span>
            </div>
          `;
        })}
      </div>
    `;
  }

  private _renderEdit() {
    const l = this.hass.language;
    const count = this.schedules.length;
    const usedIds = new Set(this.schedules.map(s => s.entity_id));

    return html`
      <div class="section-hint">${localize("covers.schedule_section_hint", l)}</div>

      ${count > 0 ? html`
        <div class="schedule-list">
          ${this.schedules.map((entry, index) => {
            const state = this._getScheduleState(index, count);
            return html`
              <div class="schedule-row ${state}">
                ${count >= 2 ? html`<span class="schedule-number">${index + 1}</span>` : nothing}
                <span class="schedule-status-dot"></span>
                <span class="schedule-name">${this._getFriendlyName(entry.entity_id)}</span>
                <span class="schedule-status">${this._statusText(state, l)}</span>
                ${this._renderScheduleControls(index, count,
                  (i, dir) => this._moveSchedule(i, dir),
                  (i) => this._removeSchedule(i))}
              </div>
            `;
          })}
        </div>
      ` : nothing}

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

  // ─── Helpers ────────────────────────────────────────────────────

  /** Read position from schedule entity's active block data attribute. */
  private _getBlockPosition(entityId: string): number | null {
    const st = this.hass?.states?.[entityId];
    if (!st || st.state !== "on") return null;
    const pos = st.attributes?.position;
    return pos != null ? Number(pos) : null;
  }

  private _statusText(state: "active" | "inactive" | "unreachable", l: string): string {
    if (state === "active") return localize("covers.schedule_state_active", l);
    if (state === "unreachable") return localize("covers.schedule_state_unreachable", l);
    return localize("covers.schedule_state_inactive", l);
  }

  // ─── Schedule management ─────────────────────────────────────────

  private _addSchedule(entityId: string) {
    this._emitSchedules([...this.schedules, { entity_id: entityId }]);
  }

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

  private _emitSchedules(value: CoverScheduleEntry[]) {
    this.dispatchEvent(new CustomEvent("cover-schedules-changed", {
      detail: { value }, bubbles: true, composed: true,
    }));
  }

  private _emitSelectorChanged(value: string) {
    this.dispatchEvent(new CustomEvent("cover-schedule-selector-changed", {
      detail: { value }, bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-cover-schedule": RsCoverSchedule;
  }
}

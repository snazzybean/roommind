import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { CoverScheduleEntry } from "../types";
import { localize } from "../utils/localize";
import { RsScheduleBase } from "./shared/rs-schedule-base";
import { inputStyles } from "../styles/input-styles";

@customElement("rs-cover-schedule")
export class RsCoverSchedule extends RsScheduleBase {
  @property({ attribute: false }) public schedules: CoverScheduleEntry[] = [];

  static styles = [
    RsScheduleBase.sharedStyles,
    inputStyles,
    css`
      .pos-badge {
        font-size: 0.8em;
        padding: 1px 6px;
        border-radius: 10px;
        background: var(--primary-color);
        color: var(--text-primary-color);
        flex-shrink: 0;
      }
      .gate-badge {
        font-size: 0.8em;
        padding: 1px 6px;
        border-radius: 10px;
        background: var(--accent-color, var(--primary-color));
        color: var(--text-primary-color);
        opacity: 0.8;
        flex-shrink: 0;
      }
      .mode-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        padding: 4px 0 0;
      }
      @media (max-width: 480px) {
        .mode-row {
          grid-template-columns: 1fr;
        }
      }
      .mode-option {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        font-size: 13px;
        cursor: pointer;
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        background: var(--card-background-color);
        transition:
          border-color 0.15s ease,
          background 0.15s ease;
      }
      .mode-option.active {
        border-color: rgba(3, 169, 244, 0.4);
        background: rgba(3, 169, 244, 0.08);
      }
    `,
  ];

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
          const isGate = entry.mode === "gate";
          const pos = !isGate ? this._getBlockPosition(entry.entity_id) : null;
          return html`
            <div class="schedule-row ${state}">
              ${hasMultiple ? html`<span class="schedule-number">${index + 1}</span>` : nothing}
              <span class="schedule-status-dot"></span>
              <span
                class="schedule-name schedule-link"
                @click=${() => this._openEntityInfo(entry.entity_id)}
                >${this._getFriendlyName(entry.entity_id)}</span
              >
              ${
                isGate
                  ? html`<span class="gate-badge"
                      >${localize("covers.schedule_mode_gate_short", l)}</span
                    >`
                  : pos !== null
                    ? html`<span class="pos-badge">${pos}%</span>`
                    : nothing
              }
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
    const usedIds = new Set(this.schedules.map((s) => s.entity_id));

    return html`
      ${
        count > 0
          ? html`
              <div class="schedule-list">
                ${this.schedules.map((entry, index) => {
                  const state = this._getScheduleState(index, count);
                  return html`
                    <div class="schedule-row ${state}">
                      ${
                        count >= 2
                          ? html`<span class="schedule-number">${index + 1}</span>`
                          : nothing
                      }
                      <span class="schedule-status-dot"></span>
                      <span class="schedule-name">${this._getFriendlyName(entry.entity_id)}</span>
                      <span class="schedule-status">${this._statusText(state, l)}</span>
                      ${this._renderScheduleControls(
                        index,
                        count,
                        (i, dir) => this._moveSchedule(i, dir),
                        (i) => this._removeSchedule(i),
                      )}
                    </div>
                    <div class="mode-row">
                      <div
                        class="mode-option ${(entry.mode ?? "force") === "force" ? "active" : ""}"
                        role="radio"
                        tabindex="0"
                        aria-checked=${(entry.mode ?? "force") === "force"}
                        @click=${() => this._updateMode(index, "force")}
                        @keydown=${(e: KeyboardEvent) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            this._updateMode(index, "force");
                          }
                        }}
                      >
                        <ha-radio
                          .checked=${(entry.mode ?? "force") === "force"}
                          tabindex="-1"
                        ></ha-radio>
                        ${localize("covers.schedule_mode_force", l)}
                      </div>
                      <div
                        class="mode-option ${entry.mode === "gate" ? "active" : ""}"
                        role="radio"
                        tabindex="0"
                        aria-checked=${entry.mode === "gate"}
                        @click=${() => this._updateMode(index, "gate")}
                        @keydown=${(e: KeyboardEvent) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            this._updateMode(index, "gate");
                          }
                        }}
                      >
                        <ha-radio .checked=${entry.mode === "gate"} tabindex="-1"></ha-radio>
                        ${localize("covers.schedule_mode_gate", l)}
                      </div>
                    </div>
                  `;
                })}
              </div>
            `
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
    this._emitSchedules([...this.schedules, { entity_id: entityId, mode: "force" }]);
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

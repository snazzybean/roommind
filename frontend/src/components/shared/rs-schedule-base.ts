/**
 * Abstract base class for schedule list components.
 * Shared by rs-schedule-settings (temperature) and rs-cover-schedule (covers).
 */
import { LitElement, html, css, nothing, type TemplateResult } from "lit";
import { property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue, openEntityInfo } from "../../utils/events";

export abstract class RsScheduleBase extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Number }) public activeIndex = -1;
  @property({ type: String }) public selectorEntity = "";
  @property({ type: Boolean }) public editing = false;

  /** Shared CSS for schedule rows, status indicators, selector section. */
  static sharedStyles = css`
    :host { display: block; }

    .schedule-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 12px;
    }

    .schedule-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s, opacity 0.3s;
    }

    .schedule-row.active { background: rgba(76, 175, 80, 0.1); }
    .schedule-row.inactive { background: rgba(0, 0, 0, 0.04); }
    .schedule-row.unreachable { background: rgba(0, 0, 0, 0.02); opacity: 0.4; }

    .schedule-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 500;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--divider-color, #e0e0e0);
      color: var(--primary-text-color);
      flex-shrink: 0;
    }
    .schedule-row.active .schedule-number { background: #4caf50; color: #fff; }

    .schedule-status-dot {
      width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    }
    .schedule-row.active .schedule-status-dot {
      background: #4caf50; box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }
    .schedule-row.inactive .schedule-status-dot { background: var(--disabled-text-color, #bdbdbd); }
    .schedule-row.unreachable .schedule-status-dot { background: var(--disabled-text-color, #bdbdbd); }

    .schedule-name {
      flex: 1; font-size: 14px; font-weight: 500;
      min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .schedule-link { cursor: pointer; }
    .schedule-link:hover { text-decoration: underline; }
    .schedule-row.active .schedule-name { color: var(--primary-text-color); }
    .schedule-row.inactive .schedule-name { color: var(--secondary-text-color); }
    .schedule-row.unreachable .schedule-name { color: var(--secondary-text-color); }

    .schedule-status { font-size: 12px; white-space: nowrap; }
    .schedule-row.active .schedule-status { color: #2e7d32; }
    .schedule-row.inactive .schedule-status { color: var(--secondary-text-color); }
    .schedule-row.unreachable .schedule-status { color: var(--secondary-text-color); }

    .schedule-controls {
      display: flex; align-items: center; gap: 2px; flex-shrink: 0;
    }
    .schedule-controls ha-icon-button {
      --mdc-icon-button-size: 28px; --mdc-icon-size: 16px;
    }

    .add-schedule-row { margin-top: 4px; }
    .add-schedule-row ha-select { width: 100%; }

    .helper-link {
      display: inline-block; margin-top: 4px;
      font-size: 12px; color: var(--primary-color); text-decoration: none;
    }
    .helper-link:hover { text-decoration: underline; }

    .no-schedules {
      font-size: 13px;
      color: var(--secondary-text-color);
      padding: 12px 0;
      text-align: center;
    }

    .form-label {
      display: block; font-size: 13px; font-weight: 500;
      color: var(--secondary-text-color); margin-bottom: 6px;
      text-transform: uppercase; letter-spacing: 0.3px;
    }

    .selector-section { margin-top: 16px; }

    .selector-value {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      padding-left: 4px;
    }

    .selector-warning {
      display: flex; align-items: center; gap: 8px;
      margin-top: 8px; padding: 10px 14px; border-radius: 8px;
      background: rgba(255, 152, 0, 0.08);
      color: var(--warning-color, #ff9800); font-size: 13px;
    }
    .selector-warning ha-icon { --mdc-icon-size: 18px; flex-shrink: 0; }

    .section-hint {
      font-size: 12px; color: var(--secondary-text-color);
      line-height: 1.5; margin-bottom: 12px;
    }
  `;

  // SVG paths for icon buttons
  protected static readonly ICON_CLOSE =
    "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";
  protected static readonly ICON_UP =
    "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z";
  protected static readonly ICON_DOWN =
    "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z";

  // ─── State computation ───────────────────────────────────────────

  protected _getScheduleState(index: number, count: number): "active" | "inactive" | "unreachable" {
    if (count === 0) return "inactive";
    if (index === this.activeIndex) return "active";
    if (!this.selectorEntity) {
      return index === 0 ? "active" : "unreachable";
    }
    const st = this.hass?.states?.[this.selectorEntity];
    if (!st) return "inactive";
    if (this.selectorEntity.startsWith("input_boolean.")) {
      return index <= 1 ? "inactive" : "unreachable";
    }
    if (this.selectorEntity.startsWith("input_number.")) {
      const min = Number(st.attributes?.min ?? 1);
      const max = Number(st.attributes?.max ?? count);
      return (index + 1) >= min && (index + 1) <= max ? "inactive" : "unreachable";
    }
    return "inactive";
  }

  // ─── Available schedule entities ─────────────────────────────────

  protected _getAvailableEntities(usedIds: Set<string>): string[] {
    if (!this.hass?.states) return [];
    return Object.keys(this.hass.states)
      .filter(id => id.startsWith("schedule.") && !usedIds.has(id));
  }

  protected _getFriendlyName(entityId: string): string {
    return (this.hass?.states?.[entityId]?.attributes?.friendly_name as string) || entityId;
  }

  // ─── Shared rendering helpers ────────────────────────────────────

  protected _renderAddRow(
    label: string,
    available: string[],
    onAdd: (entityId: string) => void,
    createLabel: string,
  ): TemplateResult {
    return html`
      <div class="add-schedule-row">
        <ha-select
          .value=${""}
          .label=${label}
          .options=${available.map(eid => ({
            value: eid,
            label: this._getFriendlyName(eid),
          }))}
          @selected=${(e: Event) => {
            const eid = getSelectValue(e);
            if (!eid) return;
            onAdd(eid);
            requestAnimationFrame(() => {
              (e.target as HTMLElement & { value: string }).value = "";
            });
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
          naturalMenuWidth
        >
          ${available.map(eid => html`
            <ha-list-item value=${eid}>${this._getFriendlyName(eid)}</ha-list-item>
          `)}
        </ha-select>
        <a href="/config/helpers" target="_top" class="helper-link">
          ${createLabel}
        </a>
      </div>
    `;
  }

  protected _renderSelectorSection(
    count: number,
    selectorLabel: string,
    selectorHint: string,
    selectorWarning: string,
    onSelectorChanged: (value: string) => void,
  ): TemplateResult | typeof nothing {
    if (count < 2) return nothing;

    const selectorState = this.selectorEntity
      ? this.hass?.states?.[this.selectorEntity]
      : null;

    return html`
      <div class="selector-section">
        <label class="form-label">${selectorLabel}</label>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.selectorEntity}
          .includeDomains=${["input_boolean", "input_number"]}
          allow-custom-entity
          @value-changed=${(e: CustomEvent) => {
            e.stopPropagation();
            onSelectorChanged(e.detail?.value ?? "");
          }}
        ></ha-entity-picker>
        ${this.selectorEntity && selectorState ? html`
          <div class="selector-value">
            ${this.selectorEntity.startsWith("input_boolean.")
              ? localize("schedule.selector_value_boolean", this.hass.language, {
                  value: selectorState.state === "on" ? "On" : "Off",
                })
              : localize("schedule.selector_value_number", this.hass.language, {
                  value: selectorState.state,
                })}
          </div>
        ` : nothing}
        <div class="section-hint" style="margin-top:4px">${selectorHint}</div>
        ${count > 1 && !this.selectorEntity ? html`
          <div class="selector-warning">
            <ha-icon icon="mdi:alert-outline"></ha-icon>
            ${selectorWarning}
          </div>
        ` : nothing}
      </div>
    `;
  }

  protected _renderScheduleControls(
    index: number,
    count: number,
    onMove: (index: number, dir: -1 | 1) => void,
    onRemove: (index: number) => void,
  ): TemplateResult {
    const hasMultiple = count >= 2;
    return html`
      <span class="schedule-controls">
        ${hasMultiple && index > 0 ? html`
          <ha-icon-button
            .path=${RsScheduleBase.ICON_UP}
            @click=${() => onMove(index, -1)}
          ></ha-icon-button>
        ` : nothing}
        ${hasMultiple && index < count - 1 ? html`
          <ha-icon-button
            .path=${RsScheduleBase.ICON_DOWN}
            @click=${() => onMove(index, 1)}
          ></ha-icon-button>
        ` : nothing}
        <ha-icon-button
          .path=${RsScheduleBase.ICON_CLOSE}
          @click=${() => onRemove(index)}
        ></ha-icon-button>
      </span>
    `;
  }

  protected _openEntityInfo(entityId: string): void {
    openEntityInfo(this, entityId);
  }
}

/**
 * Abstract base class for schedule list components.
 * Shared by rs-schedule-settings (temperature) and rs-cover-schedule (covers).
 */
import { LitElement, html, css, nothing, type TemplateResult } from "lit";
import { property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue, openEntityInfo } from "../../utils/events";
import "./rs-icon-button";
import "./rs-field";
import "./rs-list-row";

export abstract class RsScheduleBase extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Number }) public activeIndex = -1;
  @property({ type: String }) public selectorEntity = "";
  @property({ type: Boolean }) public editing = false;

  /** Shared CSS for schedule rows, status indicators, selector section. */
  static sharedStyles = css`
    :host {
      display: block;
    }

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
      transition:
        background 0.3s,
        opacity 0.3s;
    }

    .schedule-row.active {
      background: color-mix(in srgb, var(--success-color) 10%, transparent);
    }
    .schedule-row.inactive {
      background: color-mix(in srgb, var(--secondary-text-color) 5%, transparent);
    }
    .schedule-row.unreachable {
      background: color-mix(in srgb, var(--secondary-text-color) 5%, transparent);
      opacity: 0.4;
    }

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
    .schedule-row.active .schedule-number {
      background: var(--success-color);
      color: var(--text-primary-color, #fff);
    }

    .schedule-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .schedule-row.active .schedule-status-dot {
      background: var(--success-color);
      box-shadow: 0 0 6px color-mix(in srgb, var(--success-color) 50%, transparent);
    }
    .schedule-row.inactive .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }
    .schedule-row.unreachable .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .schedule-link {
      cursor: pointer;
    }
    .schedule-link:hover {
      text-decoration: underline;
    }
    .schedule-row.active .schedule-name {
      color: var(--primary-text-color);
    }
    .schedule-row.inactive .schedule-name {
      color: var(--secondary-text-color);
    }
    .schedule-row.unreachable .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-status {
      font-size: 12px;
      white-space: nowrap;
    }
    /* green text on the green tint stays under 4.5:1; dot and number carry the colour */
    .schedule-row.active .schedule-status {
      color: var(--primary-text-color);
    }
    .schedule-row.inactive .schedule-status {
      color: var(--secondary-text-color);
    }
    .schedule-row.unreachable .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-controls {
      display: flex;
      align-items: center;
      gap: 2px;
      flex-shrink: 0;
    }

    .add-schedule-row {
      margin-top: 4px;
    }
    .add-schedule-row ha-select {
      width: 100%;
    }

    /* rows reach the dialog edge so their text lines up with the fields */
    .helper-link {
      margin: var(--rs-space-1) calc(-1 * var(--rs-form-inline, 16px)) 0;
      --rs-list-row-padding: var(--rs-form-inline, 16px);
    }

    .no-schedules {
      font-size: 13px;
      color: var(--secondary-text-color);
      padding: 12px 0;
      text-align: center;
    }

    .selector-section {
      margin-top: 16px;
    }

    .selector-value {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }

    /* .inline-warning is the same pill outside the selector context (#395). */
    .selector-warning,
    .inline-warning {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--warning-color) 10%, transparent);
      color: var(--primary-text-color);
      font-size: 13px;
    }
    .selector-warning ha-icon,
    .inline-warning ha-icon {
      --mdc-icon-size: 18px;
      flex-shrink: 0;
      color: var(--warning-color);
    }
  `;

  // SVG paths for icon buttons

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
      return index + 1 >= min && index + 1 <= max ? "inactive" : "unreachable";
    }
    return "inactive";
  }

  // ─── Available schedule entities ─────────────────────────────────

  protected _getAvailableEntities(usedIds: Set<string>): string[] {
    if (!this.hass?.states) return [];
    return Object.keys(this.hass.states).filter(
      (id) => id.startsWith("schedule.") && !usedIds.has(id),
    );
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
          .options=${available.map((eid) => ({
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
          ${available.map(
            (eid) => html`
              <ha-list-item value=${eid}>${this._getFriendlyName(eid)}</ha-list-item>
            `,
          )}
        </ha-select>
        ${
          createLabel
            ? html`<rs-list-row
                class="helper-link"
                href="/config/helpers/add?domain=schedule"
                plain-icon
                variant="primary"
                icon="mdi:plus"
                .heading=${createLabel}
              ></rs-list-row>`
            : nothing
        }
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

    const selectorState = this.selectorEntity ? this.hass?.states?.[this.selectorEntity] : null;

    return html`
      <div class="selector-section">
        <rs-field .info=${selectorHint}>
          <ha-entity-picker
            .hass=${this.hass}
            .label=${selectorLabel}
            .value=${this.selectorEntity}
            .includeDomains=${["input_boolean", "input_number"]}
            allow-custom-entity
            @value-changed=${(e: CustomEvent) => {
              e.stopPropagation();
              onSelectorChanged(e.detail?.value ?? "");
            }}
          ></ha-entity-picker>
        </rs-field>
        ${
          this.selectorEntity && selectorState
            ? html`
                <div class="selector-value">
                  ${localize(
                    this.selectorEntity.startsWith("input_boolean.")
                      ? "schedule.selector_value_boolean"
                      : "schedule.selector_value_number",
                    this.hass.language,
                    { value: this.selectorStateText() },
                  )}
                </div>
              `
            : nothing
        }
        ${
          count > 1 && !this.selectorEntity
            ? html`
                <div class="selector-warning">
                  <ha-icon icon="mdi:alert-outline"></ha-icon>
                  ${selectorWarning}
                </div>
              `
            : nothing
        }
      </div>
    `;
  }

  /** The selector's state as the user reads it: "An"/"Aus", or the number. */
  protected selectorStateText(): string {
    const st = this.selectorEntity ? this.hass?.states?.[this.selectorEntity] : undefined;
    if (!st) return "";
    if (this.selectorEntity.startsWith("input_boolean.")) {
      const l = this.hass.language;
      if (st.state === "on") return localize("detail.on", l);
      if (st.state === "off") return localize("detail.off", l);
    }
    return this.hass.formatEntityState?.(st) ?? st.state;
  }

  protected _renderScheduleControls(
    index: number,
    count: number,
    onMove: (index: number, dir: -1 | 1) => void,
    onRemove: (index: number) => void,
    name = "",
  ): TemplateResult {
    const l = this.hass.language;
    const hasMultiple = count >= 2;
    return html`
      <span class="schedule-controls">
        ${
          hasMultiple && index > 0
            ? html`<rs-icon-button
                size="sm"
                icon="mdi:arrow-up"
                .label=${localize("common.move_up_named", l, { name })}
                @click=${() => onMove(index, -1)}
              ></rs-icon-button>`
            : nothing
        }
        ${
          hasMultiple && index < count - 1
            ? html`<rs-icon-button
                size="sm"
                icon="mdi:arrow-down"
                .label=${localize("common.move_down_named", l, { name })}
                @click=${() => onMove(index, 1)}
              ></rs-icon-button>`
            : nothing
        }
        <rs-icon-button
          size="sm"
          icon="mdi:close"
          .label=${localize("common.remove_named", l, { name })}
          @click=${() => onRemove(index)}
        ></rs-icon-button>
      </span>
    `;
  }

  protected _openEntityInfo(entityId: string): void {
    openEntityInfo(this, entityId);
  }
}

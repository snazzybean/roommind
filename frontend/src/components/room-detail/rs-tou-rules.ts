/**
 * rs-tou-rules – tariff rule rows on the room card.
 *
 * Rows are thin references into the shared rule library (settings["tou_rules"],
 * delivered on the rooms/list payload), each row an action anchored to a tier
 * boundary: (action)(anchor)(heat)(cool)(end). The section toggle gates the
 * whole schedule: when off, the rows cannot steer the room — but they stay in
 * place, so a temporary switch-off never loses rules (the library prunes only
 * on last reference). Editing a rule under its name propagates to every room;
 * renaming forks a derivative; renaming onto a taken name merges (backend:
 * websocket_api._async_upsert_tou_rules + TouManager.row_records).
 *
 * Edits stage locally and reach the server only when the row is saved:
 * collapse, the Save button, or the dialog close (flushPending — the room
 * detail calls it before dismissing). A new rule starts as a local draft
 * with a blank name; leaving one unnamed asks to discard.
 *
 * Fires `tou-setting-changed` with `{ key, value }` (`tou_overrides` /
 * `tou_schedule_enabled`); the parent autosaves. Rebuild of the fork's
 * rs-tou-section row grammar against the upstream room-detail conventions.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  RoomConfig,
  TouOverrideAction,
  TouExtraTier,
  TouOverrideRow,
  TouOverrideUntil,
  TouRule,
  TouRuleDef,
  TouTier,
} from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import {
  tempRange,
  tempStep,
  tempUnit,
  toCelsius,
  toCelsiusDelta,
  toDisplay,
  toDisplayDelta,
} from "../../utils/temperature";
import { inputStyles } from "../../styles/input-styles";
import { wireRows } from "../../utils/tou-rows";
import "../shared/rs-list-row";

const TOU_TIERS: TouTier[] = ["peak", "mid", "off", "ultra_low"];
const TIER_ANY = "any";
const PICKER_NEW = "__new__";
const ACTIONS: TouOverrideAction[] = ["set", "raise", "lower", "arrive"];
const UNTILS: TouOverrideUntil[] = ["tier_window", "minutes", "clock"];
const DAY_CHIPS = [
  { value: "monday", abbr: "Mo", key: "mon" },
  { value: "tuesday", abbr: "Tu", key: "tue" },
  { value: "wednesday", abbr: "We", key: "wed" },
  { value: "thursday", abbr: "Th", key: "thu" },
  { value: "friday", abbr: "Fr", key: "fri" },
  { value: "saturday", abbr: "Sa", key: "sat" },
  { value: "sunday", abbr: "Su", key: "sun" },
] as const;
const CHEVRON_RIGHT = "M10,6L8.59,7.41L13.17,12L8.59,16.59L10,18L16,12L10,6Z";
const CHEVRON_DOWN = "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z";
const CHEVRON_UP = "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z";
const CLOSE_ICON =
  "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";

function newId(): string {
  return self.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

@customElement("rs-tou-rules")
export class RsTouRules extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  /** True inside the edit dialog: the full row editor; false: card summary. */
  @property({ type: Boolean }) public editing = false;
  /** The room's schedule-section gate (tou_schedule_enabled). */
  @property({ type: Boolean }) public scheduleEnabled = false;
  /** The room's stored thin row references (config.tou_overrides). */
  @property({ type: Array }) public rows: TouOverrideRow[] = [];
  /** The shared rule library (the rooms/list payload's tou_rules). */
  @property({ type: Array }) public rules: TouRule[] = [];
  /** Sensor-driven energy tier registry (rooms/list payload): extra anchors
   * the tier selects offer alongside the grid ladder (S6). */
  @property({ type: Array }) public extraTiers: TouExtraTier[] = [];
  /** All rooms, for the copy picker's usage counts. */
  @property({ type: Object }) public allRooms: Record<string, RoomConfig> = {};
  /** This room's area id: usage counts exclude it (its rows are visible). */
  @property({ type: String }) public areaId = "";

  @state() private _expanded: Record<string, boolean> = {};
  /** Staged definitions by row id: nothing reaches the server until saved. */
  @state() private _pending: Record<string, TouRuleDef> = {};
  /** Brand-new rules as local drafts: invisible to the server until named. */
  @state() private _drafts: TouOverrideRow[] = [];

  private get _allRows(): TouOverrideRow[] {
    return [...this.rows, ...this._drafts];
  }

  static styles = [
    inputStyles,
    css`
      .hint {
        color: var(--secondary-text-color);
        font-size: 0.85em;
        margin: 4px 0;
      }
      .row-card {
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        padding: 2px 12px 10px;
        margin: 8px 0;
      }
      .row-head {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .row-summary {
        flex: 1;
        min-width: 0;
        cursor: pointer;
        overflow-wrap: anywhere;
      }
      .row-name {
        font-weight: 500;
      }
      .row-item {
        padding: 2px 0;
      }
      .row-item.off .row-summary {
        opacity: 0.5;
      }
      .missing {
        color: var(--error-color);
        font-size: 0.9em;
      }
      .anchor-grid,
      .end-grid,
      .temp-grid,
      .between-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-top: 6px;
      }
      .temp-side ha-select,
      .anchor-grid ha-select,
      .end-grid ha-select {
        width: 100%;
      }
      .day-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 4px 0;
      }
      .day-chip {
        display: flex;
        align-items: center;
        gap: 4px;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 0.85em;
        cursor: pointer;
      }
      .row-foot {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-top: 8px;
      }
      .row-enabled {
        display: flex;
        align-items: center;
        gap: 6px;
        cursor: pointer;
      }
      .foot-actions {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .usage-hint,
      .save-hint {
        color: var(--secondary-text-color);
        font-size: 0.85em;
      }
      .picker {
        margin-top: 12px;
      }
      .picker ha-select {
        width: 100%;
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    // The name field upgrades itself to an editable combobox once the runtime
    // provides ha-combo-box; re-render when it lands (older HA never will,
    // and the text-field fallback keeps working meanwhile).
    if (!customElements.get("ha-combo-box")) {
      customElements.whenDefined("ha-combo-box").then(() => this.requestUpdate());
    }
  }

  render() {
    const l = this.hass.language;
    if (!this.editing) {
      if (this.rows.length === 0) {
        return html`<div class="hint">${localize("tou.schedule_empty", l)}</div>`;
      }
      return html`
        ${this.rows.map((row) => this._renderViewRow(row, l))}
        ${
          this.scheduleEnabled
            ? nothing
            : html`<div class="hint">${localize("tou.schedule_off_hint", l)}</div>`
        }
      `;
    }
    return html`
      <rs-list-row
        switch
        .heading=${localize("tou.schedule_enabled_label", l)}
        .checked=${this.scheduleEnabled}
        @toggle-changed=${(e: CustomEvent<boolean>) => this._emit("tou_schedule_enabled", e.detail)}
      ></rs-list-row>
      <div class="hint">${localize("tou.schedule_hint", l)}</div>
      ${
        this.scheduleEnabled
          ? html`
              ${this._allRows.map((row) => this._renderRowEditor(row, l))}
              ${
                this._allRows.length > 1
                  ? html`<div class="hint">${localize("tou.row_priority_note", l)}</div>`
                  : nothing
              }
              <div class="picker">
                <ha-select
                  .value=${""}
                  .label=${localize("tou.pick_rule", l)}
                  .options=${[
                    { value: PICKER_NEW, label: localize("tou.new_rule", l) },
                    ...this.rules.map((r) => ({ value: r.id, label: r.name || r.id })),
                  ]}
                  @selected=${(e: Event) => {
                    const v = getSelectValue(e);
                    if (!v) return;
                    if (v === PICKER_NEW) this._addNewRule();
                    else this._addFromRule(v);
                    requestAnimationFrame(() => {
                      (e.target as HTMLElement & { value: string }).value = "";
                    });
                  }}
                  @closed=${(e: Event) => e.stopPropagation()}
                  fixedMenuPosition
                ></ha-select>
                <div class="hint">${localize("tou.pick_rule_hint", l)}</div>
              </div>
            `
          : nothing
      }
    `;
  }

  // ---- Card summary rows ----

  private _renderViewRow(row: TouOverrideRow, l: string) {
    const rule = this._defOf(row);
    if (!rule) {
      return html`<div class="row-item off">
        <div class="row-summary missing">${localize("tou.rule_missing", l)}</div>
      </div>`;
    }
    return html`
      <div class="row-item ${row.enabled ? "" : "off"}">
        <div class="row-summary">
          ${rule.name ? html`<span class="row-name">${rule.name}</span> · ` : nothing}${this._summarize(rule, l)}
        </div>
      </div>
    `;
  }

  // ---- Row editor (collapsed ↔ expanded) ----

  private _renderRowEditor(row: TouOverrideRow, l: string) {
    const expanded = !!this._expanded[row.id];
    const rule = this._defOf(row);
    const saved = this._isSavedRow(row.id);
    const idx = this.rows.findIndex((r) => r.id === row.id);
    const head = html`
      <div class="row-head">
        <ha-icon-button
          .path=${expanded ? CHEVRON_DOWN : CHEVRON_RIGHT}
          .label=${localize("tou.schedule_title", l)}
          @click=${() => this._toggleExpanded(row.id)}
        ></ha-icon-button>
        <div class="row-summary" @click=${() => this._toggleExpanded(row.id)}>
          ${
            rule
              ? html`${rule.name ? html`<span class="row-name">${rule.name}</span> · ` : nothing}${this._summarize(rule, l)}`
              : html`<span class="missing">${localize("tou.rule_missing", l)}</span>`
          }
        </div>
        ${
          saved
            ? html`
                <ha-icon-button
                  .path=${CHEVRON_UP}
                  .label=${localize("tou.row_up", l)}
                  .disabled=${idx <= 0}
                  @click=${() => this._moveRow(row.id, -1)}
                ></ha-icon-button>
                <ha-icon-button
                  .path=${CHEVRON_DOWN}
                  .label=${localize("tou.row_down", l)}
                  .disabled=${idx < 0 || idx >= this.rows.length - 1}
                  @click=${() => this._moveRow(row.id, 1)}
                ></ha-icon-button>
              `
            : nothing
        }
        <ha-icon-button
          .path=${CLOSE_ICON}
          .label=${localize("tou.override_delete", l)}
          @click=${() => this._removeRowById(row.id)}
        ></ha-icon-button>
      </div>
    `;
    if (!expanded) {
      return html`<div class="row-card">${head}</div>`;
    }
    if (!rule) {
      // Dangling reference: nothing to edit until the rule is re-added.
      return html`<div class="row-card">
        ${head}
        <div class="missing">${localize("tou.rule_missing", l)}</div>
      </div>`;
    }
    const usage = this._usageCount(row.rule_id);
    const isDelta = rule.action === "raise" || rule.action === "lower";
    const update = (patch: Partial<TouRuleDef>) => this._updateDef(row.id, patch);
    const range = tempRange(5, 35, this.hass);
    const sideLabel = (side: "heat" | "cool") =>
      `${localize(`tou.override_side.${side}`, l)}${isDelta ? ` Δ${tempUnit(this.hass)}` : ` ${tempUnit(this.hass)}`}`;
    return html`
      <div class="row-card">
        ${head} ${this._renderNameField(row, rule, l)}
        <div class="hint">
          ${
            customElements.get("ha-combo-box")
              ? localize("tou.override_name_hint", l)
              : localize("tou.rename_hint", l)
          }
          ${
            usage > 1
              ? html`<div class="usage-hint">
                  ${localize("tou.rule_used_in", l, { count: usage })}
                </div>`
              : nothing
          }
        </div>

        <ha-select
          .label=${localize("tou.override_action_label", l)}
          .value=${rule.action}
          .options=${ACTIONS.map((a) => ({ value: a, label: localize(`tou.override_action.${a}`, l) }))}
          @selected=${(e: Event) => {
            const v = getSelectValue(e);
            if (v === null) return;
            // Entering "arrive" normalizes the hidden anchor fields to a valid
            // coast-through rule; the arrival submode then owns edge/until/clock.
            if (v === "arrive")
              update({ action: v as TouOverrideAction, until: "tier_window", clock: "" });
            else update({ action: v as TouOverrideAction });
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
          style="width:100%"
        ></ha-select>

        ${
          rule.action === "arrive"
            ? this._renderArriveAnchors(row, rule, l)
            : html`
                <div class="anchor-grid">
                  <ha-select
                    .label=${localize("tou.override_tier", l)}
                    .value=${rule.tier}
                    .options=${[
                      { value: TIER_ANY, label: localize("tou.tier_any", l) },
                      ...this._tierOptions(l),
                    ]}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      if (v !== null) update({ tier: v as TouTier | typeof TIER_ANY });
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  ></ha-select>
                  <ha-select
                    .label=${localize("tou.override_edge_label", l)}
                    .value=${rule.edge}
                    .options=${(["start", "end"] as const).map((edge) => ({
                      value: edge,
                      label: localize(`tou.override_edge.${edge}`, l),
                    }))}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      if (v !== null) update({ edge: v as "start" | "end" });
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  ></ha-select>
                </div>
              `
        }

        <div class="temp-grid">
          ${(["heat", "cool"] as const).map((side) => {
            const current = side === "heat" ? rule.heat : rule.cool;
            const named = typeof current === "string" ? current : "";
            const setSide = (v: number | "comfort" | "eco" | null) =>
              update({ [side]: v } as Partial<TouRuleDef>);
            if (isDelta) {
              return html`<ha-textfield
                type="number"
                .value=${current == null ? "" : String(toDisplayDelta(current as number, this.hass))}
                .label=${sideLabel(side)}
                min=${range.min}
                max=${range.max}
                step=${tempStep(this.hass)}
                @change=${(e: Event) => {
                  const raw = (e.target as HTMLInputElement).value.trim();
                  if (raw === "") setSide(null);
                  else {
                    const v = parseFloat(raw);
                    if (!isNaN(v)) setSide(toCelsiusDelta(v, this.hass));
                  }
                }}
              ></ha-textfield>`;
            }
            // The mode select doubles as the side's editor: "Fixed" steers a
            // number, Comfort/Eco aim at the room's own schedule targets and
            // follow them when retuned.
            return html`<div class="temp-side">
              <ha-select
                .label=${sideLabel(side)}
                .value=${named || "fixed"}
                .options=${[
                  { value: "fixed", label: localize("tou.value_fixed", l) },
                  { value: "comfort", label: localize("tou.value_comfort", l) },
                  { value: "eco", label: localize("tou.value_eco", l) },
                ]}
                @selected=${(e: Event) => {
                  const v = getSelectValue(e);
                  if (v === "comfort" || v === "eco") setSide(v);
                  else if (v === "fixed" && named)
                    // Back from a named target: freeze what it was steering.
                    setSide(this._roomTarget(side, named));
                }}
                @closed=${(e: Event) => e.stopPropagation()}
                fixedMenuPosition
              ></ha-select>
              ${
                named
                  ? nothing
                  : html`<ha-textfield
                      type="number"
                      .value=${current == null ? "" : String(toDisplay(current as number, this.hass))}
                      min=${range.min}
                      max=${range.max}
                      step=${tempStep(this.hass)}
                      @change=${(e: Event) => {
                        const raw = (e.target as HTMLInputElement).value.trim();
                        if (raw === "") setSide(null);
                        else {
                          const v = parseFloat(raw);
                          if (!isNaN(v)) setSide(toCelsius(v, this.hass));
                        }
                      }}
                    ></ha-textfield>`
              }
            </div>`;
          })}
        </div>
        <div class="hint">${localize("tou.override_sides_hint", l)}</div>

        ${
          rule.action === "arrive"
            ? html`
                ${
                  this._isTimeArrive(rule)
                    ? html`<ha-textfield
                        .value=${rule.clock ?? ""}
                        .label=${localize("tou.override_arrive_at", l)}
                        pattern="[0-9]{1,2}:[0-9]{2}"
                        @change=${(e: Event) => update({ clock: (e.target as HTMLInputElement).value })}
                      ></ha-textfield>`
                    : nothing
                }
                <div class="hint">${localize("tou.arrive_model_note", l)}</div>
              `
            : html`
                <div class="end-grid">
                  <ha-select
                    .label=${localize("tou.override_until_label", l)}
                    .value=${rule.until}
                    .options=${UNTILS.map((u) => ({ value: u, label: localize(`tou.override_until.${u}`, l) }))}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      if (v !== null) update({ until: v as TouOverrideUntil });
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  ></ha-select>
                  ${
                    rule.until === "minutes"
                      ? html`<ha-textfield
                          type="number"
                          .value=${String(rule.minutes ?? 60)}
                          .label=${localize("tou.override_minutes", l)}
                          min="5"
                          max="720"
                          step="5"
                          @change=${(e: Event) => {
                            const v = parseInt((e.target as HTMLInputElement).value, 10);
                            if (!isNaN(v)) update({ minutes: v });
                          }}
                        ></ha-textfield>`
                      : rule.until === "clock"
                        ? html`<ha-textfield
                            .value=${rule.clock ?? ""}
                            .label=${localize("tou.override_clock", l)}
                            pattern="[0-9]{1,2}:[0-9]{2}"
                            @change=${(e: Event) => update({ clock: (e.target as HTMLInputElement).value })}
                          ></ha-textfield>`
                        : nothing
                  }
                </div>
              `
        }

        <div>
          <div class="hint">${localize("tou.override_days", l)}</div>
          <div class="day-row">
            ${DAY_CHIPS.map(
              (d) =>
                html`<label class="day-chip" title=${localize(`tou.day.${d.key}`, l)}>
                  <input
                    type="checkbox"
                    .checked=${(rule.days ?? []).includes(d.value)}
                    @change=${() =>
                      update({
                        days: (rule.days ?? []).includes(d.value)
                          ? (rule.days ?? []).filter((x) => x !== d.value)
                          : [...(rule.days ?? []), d.value],
                      })}
                  />
                  <span>${d.abbr}</span>
                </label>`,
            )}
          </div>
          <div class="hint">${localize("tou.override_days_hint", l)}</div>
          <div class="between-row">
            <ha-textfield
              .value=${rule.between?.from ?? ""}
              .label=${localize("tou.override_between_from", l)}
              pattern="[0-9]{1,2}:[0-9]{2}"
              @change=${(e: Event) => {
                const v = (e.target as HTMLInputElement).value;
                const to = rule.between?.to ?? "";
                update({ between: v === "" && to === "" ? null : { from: v, to } });
              }}
            ></ha-textfield>
            <ha-textfield
              .value=${rule.between?.to ?? ""}
              .label=${localize("tou.override_between_to", l)}
              pattern="[0-9]{1,2}:[0-9]{2}"
              @change=${(e: Event) => {
                const v = (e.target as HTMLInputElement).value;
                const from = rule.between?.from ?? "";
                update({ between: from === "" && v === "" ? null : { from, to: v } });
              }}
            ></ha-textfield>
          </div>
          <div class="hint">${localize("tou.override_between_hint", l)}</div>
        </div>

        <div class="row-foot">
          <label class="row-enabled">
            <input
              type="checkbox"
              .checked=${row.enabled}
              @change=${(e: Event) => this._updateRow(row.id, { enabled: (e.target as HTMLInputElement).checked })}
            />
            <span>${localize("tou.override_enabled", l)}</span>
          </label>
          ${
            this._pending[row.id] || this._isDraft(row.id)
              ? html`
                  <div class="foot-actions">
                    <div class="save-hint">${localize("tou.save_stage_hint", l)}</div>
                    <ha-button @click=${() => this._toggleExpanded(row.id)}>
                      ${localize("tou.save_button", l)}
                    </ha-button>
                  </div>
                `
              : nothing
          }
        </div>
      </div>
    `;
  }

  // ---- Arrive anchors ----

  /** Arrive mode selector: a clock means "reach by that time" (the charge
   * period's end opens the coast); no clock means the room coasts through the
   * anchored period and arrives at its end. Mirrors the backend inference in
   * TouManager._rule_records, which keys the mode on the clock's presence. */
  private _isTimeArrive(rule: TouRuleDef): boolean {
    return String(rule.clock ?? "").trim() !== "";
  }

  private _renderArriveAnchors(row: TouOverrideRow, rule: TouRuleDef, l: string) {
    const update = (patch: Partial<TouRuleDef>) => this._updateDef(row.id, patch);
    const time = this._isTimeArrive(rule);
    // The submode rewrites the anchor fields as a set — edge/until stay hidden
    // because each mode owns them (end+clock vs start+tier_window).
    const setMode = (wantTime: boolean) => {
      if (wantTime === time) return;
      update(
        wantTime
          ? { until: "clock", clock: rule.clock || "07:00" }
          : { until: "tier_window", clock: "" },
      );
    };
    return html`
      <div class="anchor-grid">
        <ha-select
          .label=${localize("tou.arrive_mode_label", l)}
          .value=${time ? "time" : "coast"}
          .options=${[
            { value: "coast", label: localize("tou.arrive_mode.coast", l) },
            { value: "time", label: localize("tou.arrive_mode.time", l) },
          ]}
          @selected=${(e: Event) => {
            const v = getSelectValue(e);
            if (v !== null) setMode(v === "time");
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
        ></ha-select>
        <ha-select
          .label=${localize(time ? "tou.charge_during" : "tou.coast_through", l)}
          .value=${rule.tier === TIER_ANY ? "" : rule.tier}
          .options=${this._tierOptions(l)}
          @selected=${(e: Event) => {
            const v = getSelectValue(e);
            if (v !== null) update({ tier: v as TouTier });
          }}
          @closed=${(e: Event) => e.stopPropagation()}
          fixedMenuPosition
        ></ha-select>
      </div>
    `;
  }

  // ---- Row / rule state ----

  /**
   * The definition of a row: staged edits first, then the in-session
   * definition, then the library copy. Library entries carry their id; a
   * `definition` never may (ids are library-owned and the schema rejects the
   * echo).
   */
  private _defOf(row: TouOverrideRow): TouRuleDef | null {
    if (this._pending[row.id]) return this._pending[row.id];
    if (row.definition) return row.definition;
    const rule = this.rules.find((r) => r.id === row.rule_id);
    if (!rule) return null;
    const def: Partial<TouRule> = { ...rule };
    delete def.id;
    return def as TouRuleDef;
  }

  private _usageCount(ruleId: string): number {
    return Object.values(this.allRooms).filter((room) =>
      (room.tou_overrides ?? []).some((o) => o.rule_id === ruleId),
    ).length;
  }

  private _isDraft(rowId: string): boolean {
    return this._drafts.some((d) => d.id === rowId);
  }

  private _isSavedRow(rowId: string): boolean {
    return this.rows.some((r) => r.id === rowId);
  }

  /** The definition in flight for a row when it leaves the editor: staged
   * edits for any row, plus the draft's own definition for new rules. */
  private _stagedDef(row: TouOverrideRow): TouRuleDef | null {
    if (this._pending[row.id]) return this._pending[row.id];
    if (this._isDraft(row.id)) return row.definition ?? null;
    return null;
  }

  private static _nameMissing(def: TouRuleDef | null): boolean {
    return def !== null && !String(def.name ?? "").trim();
  }

  private _tierOptions(l: string): { value: string; label: string }[] {
    return [
      ...TOU_TIERS.map((t) => ({ value: t as string, label: localize(`tou.tier.${t}`, l) })),
      ...this.extraTiers.map((t) => ({ value: t.id, label: t.name || t.id })),
    ];
  }

  /** Registry name for an extra tier, else the localized grid label. */
  private _tierLabel(tier: string, l: string): string {
    const extra = this.extraTiers.find((t) => t.id === tier);
    if (extra) return extra.name || extra.id;
    return localize(`tou.tier.${tier}` as TranslationKey, l);
  }

  // ---- Reordering ----

  /** Arrow reorder: swap with the neighbouring saved row. Row order is the
   * engine's priority (the lowest overlapping row wins), so this is a
   * behaviour change — per room, like every other row knob. */
  private _moveRow(rowId: string, delta: number) {
    const rows = [...this.rows];
    const from = rows.findIndex((r) => r.id === rowId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= rows.length) return;
    const [moved] = rows.splice(from, 1);
    rows.splice(to, 0, moved);
    this._emitRows(rows);
  }

  // ---- Staged save / discard ----

  private _toggleExpanded(rowId: string) {
    // Collapsing a row is the save trigger; it may ask to discard instead
    // (unnamed rule) or refuse to collapse (user chose to keep editing).
    if (this._expanded[rowId]) {
      const row = this._allRows.find((r) => r.id === rowId);
      if (row && !this._leaveRow(row)) return;
      this._expanded = { ...this._expanded, [rowId]: false };
      return;
    }
    this._expanded = { ...this._expanded, [rowId]: true };
  }

  /**
   * Move-away gate for one row (collapse, Save, dialog close): saves the
   * staged definition, or — when the rule has no name — asks to discard.
   * Returns false when the user chose to keep editing (the caller must stay
   * put), true when the row was saved or discarded.
   */
  private _leaveRow(row: TouOverrideRow): boolean {
    if (!RsTouRules._nameMissing(this._stagedDef(row))) {
      this._saveRow(row);
      return true;
    }
    const msg = localize(
      this._isDraft(row.id) ? "tou.discard_new_rule" : "tou.discard_unnamed",
      this.hass.language,
    );
    if (confirm(msg)) {
      this._discardRow(row.id);
      return true;
    }
    return false;
  }

  /** Commits one row: promotes a named draft, bakes staged edits. */
  private _saveRow(row: TouOverrideRow): void {
    const pending = this._pending[row.id];
    if (this._isDraft(row.id)) {
      const draft = this._drafts.find((d) => d.id === row.id);
      if (!draft) return;
      this._dropPending(row.id);
      this._drafts = this._drafts.filter((d) => d.id !== row.id);
      this._emitRows([...this.rows, { ...draft, definition: pending ?? draft.definition }]);
      return;
    }
    if (!pending) return;
    this._dropPending(row.id);
    this._emitRows(this.rows.map((r) => (r.id === row.id ? { ...r, definition: pending } : r)));
  }

  /** Drops everything in flight for a row: staged edits, or the whole draft.
   * An existing rule reverts to its plain library reference. */
  private _discardRow(rowId: string): void {
    this._dropPending(rowId);
    if (this._isDraft(rowId)) {
      this._drafts = this._drafts.filter((d) => d.id !== rowId);
      return;
    }
    this._emitRows(
      this.rows.map((r) => {
        if (r.id !== rowId) return r;
        const ref = { ...r };
        delete ref.definition;
        return ref;
      }),
    );
  }

  private _dropPending(rowId: string): void {
    if (this._pending[rowId]) {
      const pend = { ...this._pending };
      delete pend[rowId];
      this._pending = pend;
    }
  }

  /**
   * Called by the room detail before the edit dialog closes: rows in flight
   * are saved (or the discard question is asked) while this element is still
   * connected — a disconnected node's events never bubble. Returns false
   * when the user chose to keep editing, which blocks the close. Walking
   * away without this hook (tab switch, reload) discards by default, because
   * unnamed work never left the card anyway.
   */
  public flushPending(): boolean {
    const l = this.hass.language;
    for (const row of this._allRows) {
      const inFlight = this._pending[row.id] ?? (this._isDraft(row.id) ? row.definition : null);
      if (!inFlight) continue;
      if (RsTouRules._nameMissing(inFlight)) {
        const msg = localize(
          this._isDraft(row.id) ? "tou.discard_new_rule" : "tou.discard_unnamed",
          l,
        );
        if (!confirm(msg)) return false; // keep editing: block the dialog close
      }
    }
    // One batched save — sequential per-row emits would each read the stale
    // rows prop and clobber each other: promote named drafts, bake staged
    // definitions, revert saved rows whose staged rename is nameless.
    if (Object.keys(this._pending).length === 0 && this._drafts.length === 0) return true;
    const promoted: TouOverrideRow[] = [];
    for (const d of this._drafts) {
      const def = this._pending[d.id] ?? d.definition;
      if (def && String(def.name ?? "").trim()) promoted.push({ ...d, definition: def });
    }
    const baked = this.rows.map((r) => {
      const pend = this._pending[r.id];
      if (pend && !String(pend.name ?? "").trim()) {
        const ref = { ...r };
        delete ref.definition;
        return ref;
      }
      return pend ? { ...r, definition: pend } : r;
    });
    this._drafts = [];
    this._pending = {};
    this._emitRows([...baked, ...promoted]);
    return true;
  }

  private _updateRow(rowId: string, patch: Partial<TouOverrideRow>) {
    // Row-level changes (the enabled toggle) save together with any staged
    // definition, so a staged edit can never be silently dropped. An
    // unnamed in-flight definition goes through the move-away gate first.
    const row = this._allRows.find((r) => r.id === rowId);
    if (row && RsTouRules._nameMissing(this._stagedDef(row))) {
      this._leaveRow(row);
      return;
    }
    const pending = this._pending[rowId];
    if (this._isDraft(rowId)) {
      if (pending) this._dropPending(rowId);
      this._drafts = this._drafts.map((d) =>
        d.id === rowId
          ? { ...d, ...patch, definition: pending ? { ...d.definition, ...pending } : d.definition }
          : d,
      );
      return;
    }
    if (pending) this._dropPending(rowId);
    this._emitRows(
      this.rows.map((r) => {
        if (r.id !== rowId) return r;
        const merged = { ...r, ...patch };
        if (pending) merged.definition = pending;
        return merged;
      }),
    );
  }

  /** Stages a definition edit locally; nothing reaches the server until the
   * row is saved (collapse / Save / dialog close). */
  private _updateDef(rowId: string, patch: Partial<TouRuleDef>) {
    const row = this._allRows.find((r) => r.id === rowId);
    if (!row) return;
    const base = this._defOf(row);
    if (!base) return;
    this._pending = { ...this._pending, [rowId]: { ...base, ...patch } };
  }

  // ---- Name field: the rule picker ----

  /**
   * The name doubles as the rule picker. Choosing an existing rule's name on
   * a row with nothing in flight ADOPTS it: the row switches its reference
   * and the editor loads that shared config — nothing is written. A new draft
   * that picks an existing name becomes a plain reference to that rule
   * instead of a same-named clone. With staged edits, the name change rides
   * the staged definition to the save, where the server decides: a fresh
   * name forks a derivative and the shared rule was never touched; a name
   * another rule already owns merges.
   */
  private _onNameChosen(row: TouOverrideRow, raw: string) {
    const name = raw.trim();
    if (!name) return;
    const current = this._defOf(row);
    if (!current || name === current.name) return;
    if (!this._pending[row.id]) {
      const source = this.rules.find((r) => r.name === name);
      if (source && source.id !== row.rule_id) {
        if (this._isDraft(row.id)) {
          this._drafts = this._drafts.filter((d) => d.id !== row.id);
          this._emitRows([...this.rows, { id: row.id, rule_id: source.id, enabled: row.enabled }]);
          return;
        }
        this._emitRows(
          this.rows.map((r) =>
            r.id === row.id ? { id: r.id, rule_id: source.id, enabled: r.enabled } : r,
          ),
        );
        return;
      }
    }
    this._updateDef(row.id, { name });
  }

  private _renderNameField(row: TouOverrideRow, rule: TouRuleDef, l: string) {
    if (customElements.get("ha-combo-box")) {
      return html`
        <ha-combo-box
          .label=${localize("tou.override_name", l)}
          .value=${rule.name}
          .items=${this.rules.map((r) => r.name)}
          allow-custom-value
          @value-changed=${(e: CustomEvent) => this._onNameChosen(row, String(e.detail?.value ?? ""))}
        ></ha-combo-box>
      `;
    }
    // Older HA without the combobox element: plain rename field; the bottom
    // picker remains the way to copy an existing rule.
    return html`
      <ha-textfield
        .value=${rule.name}
        .label=${localize("tou.override_name", l)}
        @change=${(e: Event) =>
          this._updateDef(row.id, { name: (e.target as HTMLInputElement).value })}
      ></ha-textfield>
    `;
  }

  // ---- Add / remove ----

  private _removeRowById(rowId: string) {
    const expanded = { ...this._expanded };
    delete expanded[rowId];
    this._expanded = expanded;
    // Deleting a row discards its staged edits and drafts — they have no
    // future. A saved row's removal also drops its last reference, letting
    // the server prune the shared rule when nothing else uses it.
    this._dropPending(rowId);
    if (this._isDraft(rowId)) {
      this._drafts = this._drafts.filter((d) => d.id !== rowId);
      return;
    }
    this._emitRows(this.rows.filter((r) => r.id !== rowId));
  }

  private _addFromRule(ruleId: string) {
    const id = newId();
    this._expanded = { ...this._expanded, [id]: true };
    this._emitRows([...this.rows, { id, rule_id: ruleId, enabled: true }]);
  }

  /** New rules start as local drafts with a blank name: nothing reaches the
   * server until the row is saved with a name (mandatory). Leaving the draft
   * unnamed asks to discard — and skipping the question discards. */
  private _addNewRule() {
    const ruleId = newId();
    const rowId = newId();
    const definition: TouRuleDef = {
      name: "",
      tier: "peak",
      edge: "start",
      action: "set",
      heat: 18,
      cool: null,
      until: "tier_window",
      minutes: 60,
      clock: "",
      days: [],
      between: null,
    };
    this._expanded = { ...this._expanded, [rowId]: true };
    this._drafts = [...this._drafts, { id: rowId, rule_id: ruleId, enabled: true, definition }];
    this.requestUpdate();
  }

  private _emitRows(rows: TouOverrideRow[]) {
    this._emit("tou_overrides", wireRows(rows));
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(
      new CustomEvent("tou-setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ---- Summary ----

  /** The room's own configured temperature a named side targets (°C) — the
   * same values the schedule section edits. Used when switching a side from
   * Comfort/Eco back to Fixed, so the number starts where the room steered. */
  private _roomTarget(side: "heat" | "cool", name: "comfort" | "eco"): number | null {
    const room = this.allRooms?.[this.areaId];
    if (!room) return null;
    const v =
      name === "comfort"
        ? side === "heat"
          ? room.comfort_heat
          : room.comfort_cool
        : side === "heat"
          ? room.eco_heat
          : room.eco_cool;
    return typeof v === "number" ? v : null;
  }

  /** Compact one-line description of a rule, display units. */
  private _summarize(rule: TouRuleDef, l: string): string {
    const tier =
      rule.tier === TIER_ANY ? localize("tou.tier_any", l) : this._tierLabel(rule.tier, l);
    const edge = localize(
      `tou.override_edge.${rule.edge === "end" ? "end" : "start"}` as TranslationKey,
      l,
    );
    const isDelta = rule.action === "raise" || rule.action === "lower";
    const sides: string[] = [];
    for (const side of ["heat", "cool"] as const) {
      const v = rule[side];
      if (v == null) continue;
      const value = isDelta
        ? `${toDisplayDelta(v as number, this.hass)}${tempUnit(this.hass)}`
        : typeof v === "string"
          ? localize(`tou.value_${v}` as TranslationKey, l)
          : `${toDisplay(v as number, this.hass)}${tempUnit(this.hass)}`;
      sides.push(`${localize(`tou.override_side.${side}` as TranslationKey, l)} ${value}`);
    }
    const action = localize(`tou.override_action.${rule.action}` as TranslationKey, l);
    let end: string;
    if (rule.action === "arrive") {
      end = this._isTimeArrive(rule)
        ? `${localize("tou.override_arrive_by", l)} ${rule.clock}`
        : localize("tou.arrive_coast_end", l);
    } else if (rule.until === "minutes") {
      end = `${localize("tou.override_until.minutes_short", l)} ${rule.minutes ?? 0}`;
    } else if (rule.until === "clock") {
      end = `${localize("tou.override_until.clock_short", l)} ${rule.clock || "--:--"}`;
    } else {
      end = localize("tou.override_until.tier_window", l);
    }
    // An arrive rule's edge is decided by its submode, not authored — showing
    // "Period starts/ends" would only echo a forced field (or the wrong one).
    const parts = rule.action === "arrive" ? [tier, action] : [tier, edge, action];
    return `${parts.join(" · ")} · ${sides.join(" / ")} · ${end}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-tou-rules": RsTouRules;
  }
}

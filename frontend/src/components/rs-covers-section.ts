import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, CoverScheduleEntry } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { formatClock, getEntitiesForArea } from "../utils/room-state";
import { getSelectValue, openEntityInfo } from "../utils/events";
import { formatPercent } from "../utils/format";
import { inputStyles } from "../styles/input-styles";
import { formStyles } from "../styles/form-styles";
import { tokens } from "../styles/tokens";
import "./shared/rs-number-field";
import "./shared/rs-field";
import "./shared/rs-icon-button";
import "./shared/rs-info-icon";
import "./rs-cover-schedule";
import "./shared/rs-list-row";

/** ha-select shows an empty value as no choice; "any direction" is a real one. */
const ANY_DIRECTION = "any";

@customElement("rs-covers-section")
export class RsCoverSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public selectedCovers: Set<string> = new Set();
  @property({ type: Boolean }) public editing = false;
  @property({ type: Boolean }) public autoEnabled = false;
  @property({ type: Number }) public deployThreshold = 1.5;
  @property({ type: Number }) public minPosition = 0;
  @property({ type: Number }) public overrideMinutes = 60;
  @property({ type: Boolean }) public autoPaused = false;
  @property({ type: Number }) public overrideUntil: number | null = null;
  @property({ attribute: false }) public coverSchedules: CoverScheduleEntry[] = [];
  @property({ type: String }) public coverScheduleSelectorEntity = "";
  @property({ type: Number }) public activeCoverScheduleIndex = -1;
  @property({ type: Boolean }) public nightClose = false;
  @property({ type: Number }) public nightPosition = 0;
  @property({ type: Boolean }) public snapDeploy = false;
  @property({ type: String }) public forcedReason = "";
  @property({ type: String }) public coverReason = "";
  @property({ type: Boolean }) public windowHold = false;
  @property({ type: Boolean }) public hasWindowSensors = false;
  @property({ attribute: false }) public coverOrientations: Record<string, number> = {};
  @property({ type: Number }) public nightCloseElevation = 0;
  @property({ type: Number }) public nightCloseOffsetMinutes = 0;
  @property({ type: Number }) public outdoorMinTemp: number | null = 10;
  @property({ attribute: false }) public coverMinPositions: Record<string, number> = {};
  /** The entity picker for covers from other areas is open. */
  @state() private _pickerOpen = false;

  static styles = [
    tokens,
    inputStyles,
    formStyles,
    css`
      :host {
        display: block;
        --rs-form-inline: var(--rs-space-4);
        container-type: inline-size;
      }

      .rows {
        display: flex;
        flex-direction: column;
      }

      .cover + .cover {
        margin-top: var(--rs-space-2);
      }

      /* the cover's own settings line up under its name */
      .cover .pair {
        padding-inline-start: calc(40px + var(--rs-space-4));
        margin-bottom: var(--rs-space-2);
      }

      .pair {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--rs-space-3);
      }

      @container (max-width: 520px) {
        .pair {
          grid-template-columns: 1fr;
        }

        .cover .pair {
          padding-inline-start: 0;
        }
      }

      .picker {
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .picker ha-entity-picker {
        flex: 1;
        min-width: 0;
      }

      .group-title ha-icon {
        --mdc-icon-size: 18px;
        margin-inline-end: var(--rs-space-1);
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    return this.editing ? this._renderEdit(l) : this._renderView(l);
  }

  private _renderView(l: string) {
    const covers = [...this.selectedCovers];
    if (covers.length === 0) {
      return html`<rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("detail.covers.add", l)}
        .secondary=${localize("covers.no_covers", l)}
        @row-click=${this._fireEdit}
      ></rs-list-row>`;
    }
    let status = "";
    if (this.coverReason === "window_hold") status = localize("covers.window_hold_active", l);
    else if (this.forcedReason === "schedule_active")
      status = localize("covers.schedule_active", l);
    else if (this.forcedReason === "night_close") status = localize("covers.night_close_active", l);
    else if (this.autoEnabled && !this.autoPaused) {
      // Shading is what the covers do, not that the automation is on
      const positions = covers
        .map((eid) => this.hass.states[eid]?.attributes?.current_position)
        .filter((p): p is number => typeof p === "number");
      if (positions.length)
        status = localize(
          positions.some((p) => p < 100) ? "covers.shading_active" : "covers.no_shading",
          l,
        );
    }
    return html`
      ${covers.map((eid) => {
        const st = this.hass.states[eid];
        const name = (st?.attributes?.friendly_name as string) ?? eid;
        const pos = st?.attributes?.current_position as number | undefined;
        const orient = this.coverOrientations[eid];
        const orientDir =
          orient !== undefined
            ? RsCoverSection._DIRECTIONS.find((d) => d.deg === orient)
            : undefined;
        const minPos = this.coverMinPositions[eid];
        const details = [
          orientDir ? localize(orientDir.longLabel, l) : "",
          minPos !== undefined && minPos > 0
            ? `${localize("covers.per_cover_min_short", l)} ${formatPercent(minPos, this.hass)}`
            : "",
        ].filter(Boolean);
        return html`<rs-list-row
          clickable
          chevron
          icon="mdi:blinds-horizontal"
          icon-label=${localize("detail.more_info", l)}
          .heading=${name}
          .secondary=${details.join(" · ")}
          .value=${pos !== undefined ? formatPercent(pos, this.hass) : ""}
          @row-click=${this._fireEdit}
          @icon-click=${() => openEntityInfo(this, eid)}
        ></rs-list-row>`;
      })}
      ${
        this.autoPaused
          ? html`<rs-list-row
              variant="warn"
              icon="mdi:hand-back-right"
              .heading=${
                this.overrideUntil
                  ? `${localize("covers.auto_paused_until", l)} ${formatClock(this.overrideUntil, l)}`
                  : localize("covers.auto_paused", l)
              }
            >
              <ha-button slot="end" @click=${this._onResumeAuto}
                >${localize("covers.resume_auto", l)}</ha-button
              >
            </rs-list-row>`
          : nothing
      }
      <rs-list-row
        clickable
        chevron
        icon=${this.autoEnabled ? "mdi:sun-angle-outline" : "mdi:sun-off-outline"}
        .heading=${localize("covers.auto_control", l)}
        .secondary=${status}
        .value=${localize(this.autoEnabled ? "detail.on" : "detail.off", l)}
        @row-click=${this._fireEdit}
      ></rs-list-row>
    `;
  }

  private _fireEdit(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }

  private _entityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    if (id.startsWith("cover.roommind_")) return false;
    return id.startsWith("cover.") && !this.selectedCovers.has(id);
  };

  private _name(entityId: string): string {
    return (this.hass.states[entityId]?.attributes?.friendly_name as string) || entityId;
  }

  private _position(entityId: string): string {
    const pos = this.hass.states[entityId]?.attributes?.current_position as number | undefined;
    return pos !== undefined ? formatPercent(pos, this.hass) : "";
  }

  /** One cover of the room: the row, then its own direction and lowest position. */
  private _renderCover(entityId: string, inArea: boolean) {
    const l = this.hass.language;
    const name = this._name(entityId);
    const orientation = this.coverOrientations[entityId];
    return html`<div class="cover">
      <rs-list-row
        single-line
        icon="mdi:blinds-horizontal"
        icon-label=${localize("detail.more_info", l)}
        .heading=${name}
        .secondary=${[entityId, inArea ? "" : localize("devices.other_area", l)]
          .filter(Boolean)
          .join(" · ")}
        .value=${this._position(entityId)}
        @icon-click=${() => openEntityInfo(this, entityId)}
      >
        <rs-icon-button
          slot="end"
          size="sm"
          icon="mdi:close"
          .label=${localize("common.remove_named", l, { name })}
          @click=${() => this._onToggle(entityId, false)}
        ></rs-icon-button>
      </rs-list-row>
      <div class="pair">
        <rs-field .info=${localize("covers.orientation_hint", l)}>
          <ha-select
            .label=${localize("covers.orientation_group_title", l)}
            .value=${orientation !== undefined ? String(orientation) : ANY_DIRECTION}
            .options=${[
              { value: ANY_DIRECTION, label: localize("covers.orientation_none", l) },
              ...RsCoverSection._DIRECTIONS.map((d) => ({
                value: String(d.deg),
                label: localize(d.longLabel, l),
              })),
            ]}
            fixedMenuPosition
            @selected=${(e: Event) => {
              const val = getSelectValue(e);
              const next = val === ANY_DIRECTION || val === "" ? undefined : Number(val);
              if (next !== orientation) this._setOrientation(entityId, next);
            }}
            @closed=${(e: Event) => e.stopPropagation()}
          >
            <ha-list-item value=${ANY_DIRECTION}
              >${localize("covers.orientation_none", l)}</ha-list-item
            >
            ${RsCoverSection._DIRECTIONS.map(
              (d) =>
                html`<ha-list-item value=${String(d.deg)}
                  >${localize(d.longLabel, l)}</ha-list-item
                >`,
            )}
          </ha-select>
        </rs-field>
        <rs-number-field
          .label=${localize("covers.per_cover_min_position", l)}
          .info=${localize("covers.per_cover_min_position_hint", l)}
          .value=${this.coverMinPositions[entityId] ?? 0}
          .min=${0}
          .max=${99}
          suffix="%"
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._setMinPosition(entityId, e.detail.value)}
        ></rs-number-field>
      </div>
    </div>`;
  }

  private _renderPicker() {
    const l = this.hass.language;
    const label = localize(this.selectedCovers.size ? "sensors.choose_other" : "sensors.choose", l);
    if (!this._pickerOpen) {
      return html`<rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:magnify"
        .heading=${label}
        @row-click=${() => {
          this._pickerOpen = true;
          void this.updateComplete.then(() => {
            const picker = this.renderRoot.querySelector<HTMLElement & { open?: () => void }>(
              "ha-entity-picker",
            );
            if (typeof picker?.open === "function") picker.open();
            else picker?.focus();
          });
        }}
      ></rs-list-row>`;
    }
    return html`<div class="picker">
      <ha-entity-picker
        .hass=${this.hass}
        .includeDomains=${["cover"]}
        .entityFilter=${this._entityFilter}
        .value=${""}
        .label=${label}
        @value-changed=${this._onEntityPicked}
      ></ha-entity-picker>
      <rs-icon-button
        size="sm"
        icon="mdi:close"
        .label=${localize("common.close", l)}
        @click=${() => {
          this._pickerOpen = false;
        }}
      ></rs-icon-button>
    </div>`;
  }

  private _switchRow(key: string, heading: TranslationKey, info: TranslationKey, checked: boolean) {
    const l = this.hass.language;
    return html`<rs-list-row
      switch
      wrap
      .heading=${localize(heading, l)}
      .checked=${checked}
      @toggle-changed=${(e: CustomEvent<boolean>) => this._emit(key, e.detail)}
    >
      <rs-info-icon slot="end" .text=${localize(info, l)}></rs-info-icon>
    </rs-list-row>`;
  }

  private _renderEdit(l: string) {
    // RoomMind's own entities never count as covers of the room (#86)
    const areaCoverIds = getEntitiesForArea(
      this.area.area_id,
      this.hass?.entities,
      this.hass?.devices,
    )
      .map((e) => e.entity_id)
      .filter((id) => id.startsWith("cover.") && !id.startsWith("cover.roommind_"));
    const selected = [...this.selectedCovers];
    const suggestions = areaCoverIds.filter((id) => !this.selectedCovers.has(id));

    return html`
      <section class="group">
        <div class="rows">
          ${selected.map((id) => this._renderCover(id, areaCoverIds.includes(id)))}
          ${selected.length ? nothing : html`<p class="note">${localize("covers.no_covers", l)}</p>`}
          ${suggestions.map(
            (id) =>
              html`<rs-list-row
                clickable
                plain-icon
                icon="mdi:plus"
                .heading=${this._name(id)}
                .secondary=${localize("detail.devices.add_suggestion", l)}
                .value=${this._position(id)}
                @row-click=${() => this._onToggle(id, true)}
              ></rs-list-row>`,
          )}
          ${this._renderPicker()}
        </div>
      </section>
      ${selected.length ? this._renderAutomation(l) : nothing}
    `;
  }

  private _renderAutomation(l: string) {
    return html`
      <section class="group">
        ${this._switchRow(
          "covers_auto_enabled",
          "covers.auto_control",
          "covers.auto_control_hint",
          this.autoEnabled,
        )}
        ${
          this.autoEnabled && (this.hasWindowSensors || this.windowHold)
            ? this._switchRow(
                "covers_window_hold",
                "covers.window_hold",
                "covers.window_hold_hint",
                this.windowHold,
              )
            : nothing
        }
      </section>
      ${this.autoEnabled ? html`${this._renderScheduleGroup(l)} ${this._renderSolarGroup(l)}` : nothing}
    `;
  }

  private _renderScheduleGroup(l: string) {
    return html`<section class="group">
      <h4 class="group-title">
        <ha-icon icon="mdi:calendar-clock" aria-hidden="true"></ha-icon>
        ${localize("covers.schedule_group_title", l)}
        <rs-info-icon .text=${localize("covers.schedule_section_hint", l)}></rs-info-icon>
      </h4>
      <rs-cover-schedule
        .hass=${this.hass}
        .schedules=${this.coverSchedules}
        .selectorEntity=${this.coverScheduleSelectorEntity}
        .activeIndex=${this.activeCoverScheduleIndex}
        .editing=${true}
        @cover-schedules-changed=${(e: CustomEvent) => this._emit("cover_schedules", e.detail.value)}
        @cover-schedule-selector-changed=${(e: CustomEvent) =>
          this._emit("cover_schedule_selector_entity", e.detail.value)}
      ></rs-cover-schedule>
      ${this._switchRow(
        "covers_night_close",
        "covers.night_close",
        "covers.night_close_hint",
        this.nightClose,
      )}
      ${
        this.nightClose
          ? html`<rs-number-field
                .label=${localize("covers.night_position", l)}
                .info=${localize("covers.night_position_hint", l)}
                .value=${this.nightPosition}
                .min=${0}
                .max=${100}
                suffix="%"
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._emit("covers_night_position", e.detail.value)}
              ></rs-number-field>
              <div class="pair">
                <rs-number-field
                  .label=${localize("covers.night_close_elevation", l)}
                  .info=${localize("covers.night_close_elevation_hint", l)}
                  .value=${this.nightCloseElevation}
                  .min=${-18}
                  .max=${10}
                  suffix="°"
                  @value-changed=${(e: CustomEvent<{ value: number }>) =>
                    this._emit("covers_night_close_elevation", e.detail.value)}
                ></rs-number-field>
                <rs-number-field
                  .label=${localize("covers.night_close_offset", l)}
                  .info=${localize("covers.night_close_offset_hint", l)}
                  .value=${this.nightCloseOffsetMinutes}
                  .min=${-120}
                  .max=${120}
                  suffix="min"
                  @value-changed=${(e: CustomEvent<{ value: number }>) =>
                    this._emit("covers_night_close_offset_minutes", e.detail.value)}
                ></rs-number-field>
              </div>`
          : nothing
      }
    </section>`;
  }

  private _renderSolarGroup(l: string) {
    return html`<section class="group">
      <h4 class="group-title">
        <ha-icon icon="mdi:white-balance-sunny" aria-hidden="true"></ha-icon>
        ${localize("covers.solar_group_title", l)}
        <rs-info-icon .text=${localize("covers.info.solar_body", l)}></rs-info-icon>
      </h4>
      <div class="pair">
        <rs-number-field
          .hass=${this.hass}
          kind="temperature-delta"
          .label=${localize("covers.deploy_threshold", l)}
          .info=${localize("covers.deploy_threshold_hint", l)}
          .value=${this.deployThreshold}
          .min=${0.5}
          .max=${5.0}
          .step=${0.1}
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._emit("covers_deploy_threshold", e.detail.value)}
        ></rs-number-field>
        <rs-number-field
          .label=${localize("covers.min_position", l)}
          .info=${localize("covers.min_position_hint", l)}
          .value=${this.minPosition}
          .min=${0}
          .max=${80}
          suffix="%"
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._emit("covers_min_position", e.detail.value)}
        ></rs-number-field>
        <rs-number-field
          .label=${localize("covers.override_minutes", l)}
          .info=${localize("covers.override_minutes_hint", l)}
          .value=${this.overrideMinutes}
          .min=${0}
          .max=${480}
          suffix="min"
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._emit("covers_override_minutes", e.detail.value)}
        ></rs-number-field>
        <rs-number-field
          .hass=${this.hass}
          kind="temperature"
          .label=${localize("covers.outdoor_min_temp", l)}
          .info=${localize("covers.outdoor_min_temp_hint", l)}
          .value=${this.outdoorMinTemp ?? 10}
          .min=${0}
          .max=${35}
          .step=${1}
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._emit("covers_outdoor_min_temp", e.detail.value)}
        ></rs-number-field>
      </div>
      ${this._switchRow(
        "covers_snap_deploy",
        "covers.snap_deploy",
        "covers.snap_deploy_hint",
        this.snapDeploy,
      )}
    </section>`;
  }

  private static readonly _DIRECTIONS: Array<{
    shortLabel: TranslationKey;
    longLabel: TranslationKey;
    deg: number;
  }> = [
    { shortLabel: "covers.orientation_N", longLabel: "covers.orientation_N_full", deg: 0 },
    { shortLabel: "covers.orientation_NE", longLabel: "covers.orientation_NE_full", deg: 45 },
    { shortLabel: "covers.orientation_E", longLabel: "covers.orientation_E_full", deg: 90 },
    { shortLabel: "covers.orientation_SE", longLabel: "covers.orientation_SE_full", deg: 135 },
    { shortLabel: "covers.orientation_S", longLabel: "covers.orientation_S_full", deg: 180 },
    { shortLabel: "covers.orientation_SW", longLabel: "covers.orientation_SW_full", deg: 225 },
    { shortLabel: "covers.orientation_W", longLabel: "covers.orientation_W_full", deg: 270 },
    { shortLabel: "covers.orientation_NW", longLabel: "covers.orientation_NW_full", deg: 315 },
  ];

  private _setMinPosition(eid: string, value: number) {
    const next = { ...this.coverMinPositions };
    next[eid] = value;
    this._emit("cover_min_positions", next);
  }

  private _setOrientation(eid: string, deg: number | undefined) {
    const next = { ...this.coverOrientations };
    if (deg === undefined) {
      delete next[eid];
    } else {
      next[eid] = deg;
    }
    this._emit("cover_orientations", next);
  }

  private _onEntityPicked(ev: CustomEvent) {
    ev.stopPropagation();
    const eid = ev.detail.value as string;
    if (!eid) return;
    (ev.target as HTMLElement & { value: string }).value = "";
    this._pickerOpen = false;
    this._onToggle(eid, true);
  }

  private _onToggle(eid: string, checked: boolean) {
    this.dispatchEvent(
      new CustomEvent("covers-toggle", {
        detail: { entityId: eid, checked },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onResumeAuto() {
    this.dispatchEvent(new CustomEvent("cover-resume-auto", { bubbles: true, composed: true }));
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-covers-section": RsCoverSection;
  }
}

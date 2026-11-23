/**
 * rs-settings-compressor – Compressor protection group management.
 */
import { html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  CompressorGroup,
  ConflictResolution,
  MasterOffMode,
} from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import "../shared/rs-confirm-button";
import "../shared/rs-icon-button";
import "../shared/rs-edit-dialog";
import { numberRow } from "../shared/number-row";
import "../shared/rs-list-row";
import "../shared/rs-field";
import "../shared/rs-info-icon";
import "../shared/rs-segmented";
import { inputStyles } from "../../styles/input-styles";
import { formStyles } from "../../styles/form-styles";
import { toCelsius } from "../../utils/temperature";
import { alertStyles } from "../../styles/tokens";
import { RsSettingsBase } from "./rs-settings-base";

/**
 * Why a group cannot be saved yet, mirroring the backend checks of settings/save: a group needs a
 * member, a device belongs to one group, a main device is no member and drives one group.
 * Groups with a problem stay in the page as drafts and are left out of the save.
 */
export function compressorGroupProblem(
  group: CompressorGroup,
  groups: readonly CompressorGroup[],
): TranslationKey | null {
  if (group.members.length === 0) return "compressor.draft_no_members";
  const others = groups.filter((g) => g !== group);
  if (group.members.some((m) => others.some((g) => g.members.includes(m))))
    return "error.duplicate_member";
  const master = group.master_entity;
  if (master) {
    if (group.members.includes(master)) return "error.master_in_members";
    if (others.some((g) => g.members.includes(master))) return "error.master_is_other_member";
    if (others.some((g) => g.master_entity === master)) return "error.duplicate_master";
  }
  return null;
}

/** A main device gets a mode (climate) or is turned on and off (switch, input_boolean). */
const MASTER_DOMAINS = ["climate", "switch", "input_boolean"];

@customElement("rs-settings-compressor")
export class RsSettingsCompressor extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Array }) public compressorGroups: CompressorGroup[] = [];

  /** Id of the group whose dialog is open. */
  @state() private _editId: string | null = null;

  static styles = [
    ...RsSettingsBase.settingsBaseStyles,
    alertStyles,
    inputStyles,
    formStyles,
    css`
      .dialog-body {
        --rs-form-inline: var(--rs-space-6);
      }
      .members {
        display: flex;
        flex-direction: column;
      }
      .delete-row {
        display: flex;
        justify-content: flex-end;
        margin-top: var(--rs-space-6);
      }
      .draft-note {
        margin: 0;
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }
      .group-problem {
        margin: 0 0 var(--rs-space-2);
      }
      .rs-alert {
        margin: 0;
      }
      ha-textfield,
      ha-select {
        width: 100%;
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    const groups = this.compressorGroups;
    const editing = groups.findIndex((g) => g.id === this._editId);
    return html`
      ${
        groups.length
          ? html`<div class="settings-section first">
              ${groups.map((group, idx) => this._renderGroupRow(group, idx))}
            </div>`
          : nothing
      }
      <div class="settings-section ${groups.length ? "" : "first"}">
        <rs-list-row
          clickable
          plain-icon
          variant="primary"
          icon="mdi:plus"
          .heading=${localize("compressor.add_group", l)}
          .secondary=${groups.length ? "" : localize("compressor.no_groups", l)}
          @row-click=${this._addGroup}
        ></rs-list-row>
      </div>
      ${editing >= 0 ? this._renderDialog(groups[editing], editing) : nothing}
    `;
  }

  private _groupLabel(group: CompressorGroup, idx: number): string {
    return group.name || `${localize("compressor.group", this.hass.language)} ${idx + 1}`;
  }

  /** One group: name, its devices and main device at a glance; the dialog edits it. */
  private _renderGroupRow(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    const n = group.members.length;
    const parts = [
      n === 1
        ? localize("settings.summary.devices_one", l)
        : localize("settings.summary.devices", l, { count: n }),
    ];
    if (group.master_entity) {
      const name =
        (this.hass.states[group.master_entity]?.attributes?.friendly_name as string) ||
        group.master_entity;
      parts.push(localize("compressor.summary_master", l, { name }));
    }
    if ((group.min_rooms ?? 1) > 1)
      parts.push(localize("compressor.summary_rooms", l, { count: group.min_rooms ?? 1 }));
    const problem = compressorGroupProblem(group, this.compressorGroups);
    return html`
      <rs-list-row
        clickable
        chevron
        icon=${group.master_entity.startsWith("climate.") ? "mdi:water-boiler" : "mdi:hvac"}
        .heading=${this._groupLabel(group, idx)}
        .secondary=${parts.join(" · ")}
        variant=${problem && problem !== "compressor.draft_no_members" ? "warn" : "default"}
        @row-click=${() => (this._editId = group.id)}
      ></rs-list-row>
    `;
  }

  private _renderDialog(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    const label = this._groupLabel(group, idx);
    return html`<rs-edit-dialog
      open
      icon="mdi:hvac"
      .heading=${label}
      @rs-dialog-closed=${() => (this._editId = null)}
    >
      <div class="dialog-body">
        ${this._renderProblem(group)}
        <section class="group">
          <ha-textfield
            .value=${group.name}
            .label=${localize("compressor.group_name", l)}
            @change=${(e: Event) => {
              const v = (e.target as HTMLInputElement).value;
              this._updateGroup(idx, "name", v);
            }}
          ></ha-textfield>
        </section>

        <section class="group">
          <h3 class="group-title">
            ${localize("compressor.members", l)}
            <rs-info-icon .text=${localize("compressor.members_hint", l)}></rs-info-icon>
          </h3>
          ${
            group.members.length > 0
              ? html`<div class="members">
                  ${group.members.map((eid) => this._renderMember(eid, idx))}
                </div>`
              : nothing
          }
          <ha-entity-picker
            .hass=${this.hass}
            .value=${""}
            .includeDomains=${["climate"]}
            .entityFilter=${this._memberFilter}
            @value-changed=${(e: CustomEvent) => {
              const v = (e.detail?.value as string) ?? "";
              if (!v) return;
              const updated = [...this.compressorGroups];
              updated[idx] = { ...updated[idx], members: [...updated[idx].members, v] };
              this._fireGroups(updated);
              const picker = e.target as HTMLElement & { value?: string };
              if (picker) picker.value = "";
            }}
          ></ha-entity-picker>
        </section>

        <section class="group">
          <h3 class="group-title">${localize("compressor.section_protection", l)}</h3>
          <div>
            ${numberRow({
              hass: this.hass,
              label: localize("compressor.min_run", l),
              info: localize("compressor.min_run_hint", l),
              unit: localize("compressor.min_run_suffix", l),
              min: 1,
              max: 60,
              value: group.min_run_minutes,
              onChange: (v) => this._updateGroup(idx, "min_run_minutes", v),
            })}
            ${numberRow({
              hass: this.hass,
              label: localize("compressor.min_off", l),
              info: localize("compressor.min_off_hint", l),
              unit: localize("compressor.min_off_suffix", l),
              min: 1,
              max: 30,
              value: group.min_off_minutes,
              onChange: (v) => this._updateGroup(idx, "min_off_minutes", v),
            })}
          </div>
        </section>

        <section class="group">
          <h3 class="group-title">
            ${localize("compressor.master_entity", l)}
            <rs-info-icon .text=${localize("compressor.master_entity_hint", l)}></rs-info-icon>
          </h3>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${group.master_entity || ""}
            .includeDomains=${MASTER_DOMAINS}
            .entityFilter=${this._masterFilter}
            @value-changed=${(e: CustomEvent) => {
              this._updateGroup(idx, "master_entity", (e.detail?.value as string) ?? "");
            }}
          ></ha-entity-picker>
          ${
            group.master_entity && group.master_control_mode === "monitor"
              ? html`<rs-field .info=${localize("compressor.master_schedule_monitor_hint", l)}>
                  ${localize("compressor.master_control_mode_monitor", l)}
                </rs-field>`
              : group.master_entity || group.action_script
                ? this._renderMasterOptions(group, idx)
                : nothing
          }
          ${
            group.master_entity.startsWith("climate.")
              ? html`<rs-field .info=${localize("compressor.master_control_mode_hint", l)}>
                  <ha-select
                    .label=${localize("compressor.master_control_mode", l)}
                    .value=${group.master_control_mode || "hvac_mode"}
                    .options=${[
                      {
                        value: "hvac_mode",
                        label: localize("compressor.master_control_mode_hvac", l),
                      },
                      {
                        value: "target_temperature",
                        label: localize("compressor.master_control_mode_target", l),
                      },
                      {
                        value: "monitor",
                        label: localize("compressor.master_control_mode_monitor", l),
                      },
                    ]}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      if (v) this._updateGroup(idx, "master_control_mode", v);
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  ></ha-select>
                </rs-field>`
              : nothing
          }
        </section>

        <section class="group">
          <h3 class="group-title">${localize("compressor.section_more", l)}</h3>
          <rs-list-row
            switch
            wrap
            .heading=${localize("compressor.enforce_uniform_mode", l)}
            .checked=${group.enforce_uniform_mode || false}
            @toggle-changed=${(e: CustomEvent<boolean>) => {
              this._updateGroup(idx, "enforce_uniform_mode", e.detail);
            }}
          >
            <rs-info-icon
              slot="end"
              .text=${localize("compressor.enforce_uniform_mode_hint", l)}
            ></rs-info-icon>
          </rs-list-row>
          ${
            group.master_entity || group.enforce_uniform_mode
              ? html`<rs-field .info=${localize("compressor.conflict_resolution_hint", l)}>
                  <ha-select
                    .label=${localize("compressor.conflict_resolution", l)}
                    .value=${group.conflict_resolution || "heating_priority"}
                    .options=${[
                      {
                        value: "heating_priority",
                        label: localize("compressor.conflict_heating_priority", l),
                      },
                      {
                        value: "cooling_priority",
                        label: localize("compressor.conflict_cooling_priority", l),
                      },
                      { value: "majority", label: localize("compressor.conflict_majority", l) },
                      {
                        value: "outdoor_temp",
                        label: localize("compressor.conflict_outdoor_temp", l),
                      },
                    ]}
                    @selected=${(e: Event) => {
                      const v = getSelectValue(e);
                      if (v) this._updateGroup(idx, "conflict_resolution", v);
                    }}
                    @closed=${(e: Event) => e.stopPropagation()}
                    fixedMenuPosition
                  ></ha-select>
                </rs-field>`
              : nothing
          }
          <rs-field .info=${localize("compressor.action_script_hint", l)}>
            <ha-entity-picker
              .hass=${this.hass}
              .value=${group.action_script || ""}
              .includeDomains=${["script"]}
              .label=${localize("compressor.action_script", l)}
              @value-changed=${(e: CustomEvent) => {
                this._updateGroup(idx, "action_script", (e.detail?.value as string) ?? "");
              }}
            ></ha-entity-picker>
          </rs-field>
        </section>

        <div class="delete-row">
          <rs-confirm-button
            destructive
            icon="mdi:delete-outline"
            .label=${localize("compressor.delete", l)}
            .accessibleLabel=${`${localize("compressor.delete", l)}: ${label}`}
            .confirmMessage=${localize("compressor.delete_confirm", l).replace("{name}", label)}
            @confirmed=${() => {
              this._editId = null;
              this._fireGroups(this.compressorGroups.filter((_, i) => i !== idx));
            }}
          ></rs-confirm-button>
        </div>
      </div>
    </rs-edit-dialog>`;
  }

  /** Rooms needed, start delay and run-on; setpoints and how it switches off for a thermostat. */
  private _renderMasterOptions(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    const thermostat = group.master_entity.startsWith("climate.");
    const setpoints = group.on_temperature != null;
    return html`
      <div>
        ${numberRow({
          hass: this.hass,
          label: localize("compressor.min_rooms", l),
          info: localize("compressor.min_rooms_hint", l),
          min: 1,
          max: 50,
          value: group.min_rooms ?? 1,
          onChange: (v) => this._updateGroup(idx, "min_rooms", v),
        })}
        ${numberRow({
          hass: this.hass,
          label: localize("compressor.start_delay", l),
          info: localize("compressor.start_delay_hint", l),
          unit: "s",
          min: 0,
          max: 3600,
          step: 30,
          value: group.start_delay_seconds ?? 0,
          onChange: (v) => this._updateGroup(idx, "start_delay_seconds", v),
        })}
        ${numberRow({
          hass: this.hass,
          label: localize("compressor.run_on", l),
          info: localize("compressor.run_on_hint", l),
          unit: "s",
          min: 0,
          max: 3600,
          step: 30,
          value: group.run_on_seconds ?? 0,
          onChange: (v) => this._updateGroup(idx, "run_on_seconds", v),
        })}
        ${
          thermostat
            ? html`
                <rs-list-row
                  switch
                  wrap
                  .heading=${localize("compressor.setpoints", l)}
                  .checked=${setpoints}
                  @toggle-changed=${(e: CustomEvent<boolean>) => this._setSetpoints(group, idx, e.detail)}
                >
                  <rs-info-icon
                    slot="end"
                    .text=${localize("compressor.setpoints_hint", l)}
                  ></rs-info-icon>
                </rs-list-row>
                ${
                  setpoints
                    ? html`
                        ${numberRow({
                          hass: this.hass,
                          kind: "temperature",
                          label: localize("compressor.on_temperature", l),
                          info: localize("compressor.on_temperature_hint", l),
                          min: 5,
                          max: 90,
                          value: group.on_temperature ?? 60,
                          onChange: (v) => this._updateGroup(idx, "on_temperature", v),
                        })}
                        ${numberRow({
                          hass: this.hass,
                          kind: "temperature",
                          label: localize("compressor.off_temperature", l),
                          info: localize("compressor.off_temperature_hint", l),
                          min: 5,
                          max: 90,
                          value: group.off_temperature ?? 5,
                          onChange: (v) => this._updateGroup(idx, "off_temperature", v),
                        })}
                      `
                    : nothing
                }
              `
            : nothing
        }
      </div>
      ${
        thermostat && setpoints
          ? html`<rs-field
              .label=${localize("compressor.off_mode", l)}
              .info=${localize("compressor.off_mode_hint", l)}
            >
              <rs-segmented
                wrap
                .label=${localize("compressor.off_mode", l)}
                .options=${[
                  { value: "off", label: localize("compressor.off_mode_off", l) },
                  { value: "temperature", label: localize("compressor.off_mode_temperature", l) },
                ]}
                .value=${group.off_mode ?? "off"}
                @value-changed=${(e: CustomEvent<{ value: string }>) => {
                  if (e.detail.value)
                    this._updateGroup(idx, "off_mode", e.detail.value as MasterOffMode);
                }}
              ></rs-segmented>
            </rs-field>`
          : nothing
      }
    `;
  }

  /** Setpoints on: start from the thermostat's own setpoint and lowest value; off: mode only. */
  private _setSetpoints(group: CompressorGroup, idx: number, on: boolean) {
    const updated = [...this.compressorGroups];
    if (!on) {
      updated[idx] = { ...group, on_temperature: null, off_temperature: null, off_mode: "off" };
    } else {
      const attrs = this.hass.states[group.master_entity]?.attributes ?? {};
      const inRange = (v: unknown, fallback: number) => {
        const c = typeof v === "number" ? toCelsius(v, this.hass) : NaN;
        return c >= 5 && c <= 90 ? Math.round(c * 2) / 2 : fallback;
      };
      updated[idx] = {
        ...group,
        on_temperature: inRange(attrs.temperature, 60),
        off_temperature: inRange(attrs.min_temp, 5),
      };
    }
    this._fireGroups(updated);
  }

  private _renderMember(entityId: string, groupIdx: number) {
    const l = this.hass.language;
    const state = this.hass.states[entityId];
    const name = (state?.attributes?.friendly_name as string) || entityId;
    const areaId = this.hass.entities[entityId]?.area_id;
    const areaName = areaId ? this.hass.areas[areaId]?.name : undefined;
    return html`
      <rs-list-row
        icon=${(state?.attributes?.icon as string) || "mdi:air-conditioner"}
        .heading=${name}
        .secondary=${state ? (areaName ?? "") : localize("detail.devices.unavailable", l)}
      >
        <rs-icon-button
          slot="end"
          icon="mdi:close"
          .label=${localize("common.remove_named", l, { name })}
          @click=${() => {
            const updated = [...this.compressorGroups];
            updated[groupIdx] = {
              ...updated[groupIdx],
              members: updated[groupIdx].members.filter((m) => m !== entityId),
            };
            this._fireGroups(updated);
          }}
        ></rs-icon-button>
      </rs-list-row>
    `;
  }

  /** Draft note or validation error at the group, so it is seen where it is fixed. */
  private _renderProblem(group: CompressorGroup) {
    const problem = compressorGroupProblem(group, this.compressorGroups);
    if (!problem) return nothing;
    const l = this.hass.language;
    if (problem === "compressor.draft_no_members")
      return html`<p class="draft-note">${localize(problem, l)}</p>`;
    return html`<p class="rs-alert" role="alert">
      ${localize("settings.save_error", l, { error: localize(problem, l) })}
    </p>`;
  }

  private _memberFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    if (id.substring(id.indexOf(".") + 1).startsWith("roommind_")) return false;
    for (const g of this.compressorGroups) {
      if (g.members.includes(id)) return false;
      if (g.master_entity === id) return false;
    }
    return true;
  };

  private _masterFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    if (id.substring(id.indexOf(".") + 1).startsWith("roommind_")) return false;
    for (const g of this.compressorGroups) {
      if (g.members.includes(id)) return false;
      if (g.master_entity === id) return false;
    }
    return true;
  };

  private _updateGroup(
    idx: number,
    field: keyof CompressorGroup,
    value: CompressorGroup[keyof CompressorGroup],
  ) {
    const updated = [...this.compressorGroups];
    updated[idx] = { ...updated[idx], [field]: value };
    this._fireGroups(updated);
  }

  private _addGroup() {
    const id =
      self.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    this._editId = id;
    this._fireGroups([
      ...this.compressorGroups,
      {
        id,
        name: "",
        members: [],
        min_run_minutes: 15,
        min_off_minutes: 5,
        master_entity: "",
        master_control_mode: "hvac_mode",
        conflict_resolution: "heating_priority" as ConflictResolution,
        action_script: "",
        enforce_uniform_mode: false,
        min_rooms: 1,
        start_delay_seconds: 0,
        run_on_seconds: 0,
        on_temperature: null,
        off_temperature: null,
        off_mode: "off",
      },
    ]);
  }

  private _fireGroups(groups: CompressorGroup[]) {
    this._fire("compressorGroups", groups);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-compressor": RsSettingsCompressor;
  }
}

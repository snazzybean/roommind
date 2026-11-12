/**
 * rs-settings-compressor – Compressor protection group management.
 */
import { html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, CompressorGroup, ConflictResolution } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import "../shared/rs-confirm-button";
import "../shared/rs-icon-button";
import "../shared/rs-number-field";
import "../shared/rs-list-row";
import { inputStyles } from "../../styles/input-styles";
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

@customElement("rs-settings-compressor")
export class RsSettingsCompressor extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Array }) public compressorGroups: CompressorGroup[] = [];

  static styles = [
    ...RsSettingsBase.settingsBaseStyles,
    alertStyles,
    inputStyles,
    css`
      .group {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-3);
      }
      .group .field-label {
        margin: var(--rs-space-2) 0 0;
        font-weight: 500;
      }
      .members {
        display: flex;
        flex-direction: column;
      }
      .group .field-hint {
        margin-top: calc(-1 * var(--rs-space-2));
      }
      .delete-row {
        display: flex;
        justify-content: flex-end;
      }
      .draft-note {
        margin: 0;
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }
      .group .rs-alert {
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
    return html`
      ${groups.map((group, idx) => this._renderGroup(group, idx))}
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
    `;
  }

  private _renderGroup(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    const label = group.name || `#${idx + 1}`;
    return html`
      <section class="settings-section group ${idx === 0 ? "first" : ""}" aria-label=${label}>
        ${this._renderProblem(group)}
        <ha-textfield
          .value=${group.name}
          .label=${localize("compressor.group_name", l)}
          @change=${(e: Event) => {
            const v = (e.target as HTMLInputElement).value;
            this._updateGroup(idx, "name", v);
          }}
        ></ha-textfield>

        <span class="field-label">${localize("compressor.members", l)}</span>
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
        <span class="field-hint">${localize("compressor.members_hint", l)}</span>

        <div class="threshold-grid">
          <rs-number-field
            .label=${localize("compressor.min_run", l)}
            .suffix=${localize("compressor.min_run_suffix", l)}
            .hint=${localize("compressor.min_run_hint", l)}
            .min=${1}
            .max=${60}
            .value=${group.min_run_minutes}
            @value-changed=${(e: CustomEvent<{ value: number }>) =>
              this._updateGroup(idx, "min_run_minutes", e.detail.value)}
          ></rs-number-field>
          <rs-number-field
            .label=${localize("compressor.min_off", l)}
            .suffix=${localize("compressor.min_off_suffix", l)}
            .hint=${localize("compressor.min_off_hint", l)}
            .min=${1}
            .max=${30}
            .value=${group.min_off_minutes}
            @value-changed=${(e: CustomEvent<{ value: number }>) =>
              this._updateGroup(idx, "min_off_minutes", e.detail.value)}
          ></rs-number-field>
        </div>

        <span class="field-label">${localize("compressor.master_entity", l)}</span>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${group.master_entity || ""}
          .includeDomains=${["climate"]}
          .entityFilter=${this._masterFilter}
          @value-changed=${(e: CustomEvent) => {
            this._updateGroup(idx, "master_entity", (e.detail?.value as string) ?? "");
          }}
        ></ha-entity-picker>
        <span class="field-hint">${localize("compressor.master_entity_hint", l)}</span>

        <rs-list-row
          switch
          wrap
          .heading=${localize("compressor.enforce_uniform_mode", l)}
          .secondary=${localize("compressor.enforce_uniform_mode_hint", l)}
          .checked=${group.enforce_uniform_mode || false}
          @toggle-changed=${(e: CustomEvent<boolean>) => {
            this._updateGroup(idx, "enforce_uniform_mode", e.detail);
          }}
        ></rs-list-row>

        ${
          group.master_entity || group.enforce_uniform_mode
            ? html`
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
                    {
                      value: "majority",
                      label: localize("compressor.conflict_majority", l),
                    },
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
                >
                </ha-select>
                <span class="field-hint">
                  ${localize("compressor.conflict_resolution_hint", l)}
                </span>
              `
            : nothing
        }

        <ha-entity-picker
          .hass=${this.hass}
          .value=${group.action_script || ""}
          .includeDomains=${["script"]}
          .label=${localize("compressor.action_script", l)}
          @value-changed=${(e: CustomEvent) => {
            this._updateGroup(idx, "action_script", (e.detail?.value as string) ?? "");
          }}
        ></ha-entity-picker>
        <span class="field-hint">${localize("compressor.action_script_hint", l)}</span>

        <div class="delete-row">
          <rs-confirm-button
            destructive
            icon="mdi:delete-outline"
            .label=${localize("compressor.delete", l)}
            .accessibleLabel=${`${localize("compressor.delete", l)}: ${label}`}
            .confirmMessage=${localize("compressor.delete_confirm", l).replace("{name}", label)}
            @confirmed=${() => {
              this._fireGroups(this.compressorGroups.filter((_, i) => i !== idx));
            }}
          ></rs-confirm-button>
        </div>
      </section>
    `;
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
    this._fireGroups([
      ...this.compressorGroups,
      {
        id: self.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        name: "",
        members: [],
        min_run_minutes: 15,
        min_off_minutes: 5,
        master_entity: "",
        conflict_resolution: "heating_priority" as ConflictResolution,
        action_script: "",
        enforce_uniform_mode: false,
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

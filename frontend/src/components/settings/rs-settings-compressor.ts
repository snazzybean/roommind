/**
 * rs-settings-compressor – Compressor protection group management.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, CompressorGroup, ConflictResolution } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import "../shared/rs-confirm-button";
import "../shared/rs-icon-button";
import "../shared/rs-number-field";
import "../shared/rs-list-row";
import { inputStyles } from "../../styles/input-styles";
import { alertStyles, tokens } from "../../styles/tokens";

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
export class RsSettingsCompressor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Array }) public compressorGroups: CompressorGroup[] = [];

  static styles = [
    tokens,
    alertStyles,
    inputStyles,
    css`
      :host {
        display: block;
      }
      .group-card {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
      }
      .member-list {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin: 8px 0;
      }
      .member-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 4px 8px;
        background: var(--card-background-color);
        border-radius: 4px;
      }
      .member-name {
        font-size: 14px;
        flex: 1;
      }
      .member-area {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-left: 4px;
      }
      .member-missing {
        color: var(--error-color);
      }
      .field-row {
        margin-top: 12px;
      }
      .field-hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-top: 4px;
      }
      .section-label {
        font-size: 14px;
        font-weight: 500;
        margin-top: 12px;
        margin-bottom: 4px;
      }
      /* runs to the card edge like the settings pages' other rows */
      .add-row {
        margin: 0 calc(-1 * var(--rs-settings-inline, 0px)) var(--rs-space-2);
        --rs-list-row-padding: var(--rs-settings-inline, 16px);
      }
      .delete-row {
        margin-top: 16px;
        display: flex;
        justify-content: flex-end;
      }
      .draft-note {
        margin: 0 0 var(--rs-space-3);
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }
      ha-textfield {
        width: 100%;
      }
      ha-entity-picker {
        width: 100%;
      }
      .number-fields {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-top: 12px;
      }
      @media (max-width: 500px) {
        .number-fields {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    return html`
      ${this.compressorGroups.map((group, idx) => this._renderGroup(group, idx))}
      <rs-list-row
        class="add-row"
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("compressor.add_group", l)}
        .secondary=${this.compressorGroups.length ? "" : localize("compressor.no_groups", l)}
        @row-click=${this._addGroup}
      ></rs-list-row>
    `;
  }

  private _renderGroup(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    return html`
      <div class="group-card">
        ${this._renderProblem(group)}
        <ha-textfield
          .value=${group.name}
          .label=${localize("compressor.group_name", l)}
          @change=${(e: Event) => {
            const v = (e.target as HTMLInputElement).value;
            this._updateGroup(idx, "name", v);
          }}
        ></ha-textfield>

        <div class="section-label">${localize("compressor.members", l)}</div>
        ${
          group.members.length > 0
            ? html`
                <div class="member-list">
                  ${group.members.map((eid) => this._renderMember(eid, idx))}
                </div>
              `
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
            this._fire(updated);
            const picker = e.target as HTMLElement & { value?: string };
            if (picker) picker.value = "";
          }}
        ></ha-entity-picker>
        <div class="field-hint">${localize("compressor.members_hint", l)}</div>

        <div class="number-fields">
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

        <div class="section-label">${localize("compressor.master_entity", l)}</div>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${group.master_entity || ""}
          .includeDomains=${["climate"]}
          .entityFilter=${this._masterFilter}
          @value-changed=${(e: CustomEvent) => {
            this._updateGroup(idx, "master_entity", (e.detail?.value as string) ?? "");
          }}
        ></ha-entity-picker>
        <div class="field-hint">${localize("compressor.master_entity_hint", l)}</div>

        <div class="field-row">
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
        </div>

        ${
          group.master_entity || group.enforce_uniform_mode
            ? html`
                <div class="field-row">
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
                    style="width: 100%;"
                  >
                  </ha-select>
                  <div class="field-hint">
                    ${localize("compressor.conflict_resolution_hint", l)}
                  </div>
                </div>
              `
            : nothing
        }

        <div class="field-row">
          <ha-entity-picker
            .hass=${this.hass}
            .value=${group.action_script || ""}
            .includeDomains=${["script"]}
            .label=${localize("compressor.action_script", l)}
            @value-changed=${(e: CustomEvent) => {
              this._updateGroup(idx, "action_script", (e.detail?.value as string) ?? "");
            }}
          ></ha-entity-picker>
          <div class="field-hint">${localize("compressor.action_script_hint", l)}</div>
        </div>

        <div class="delete-row">
          <rs-confirm-button
            .label=${localize("compressor.delete", l)}
            .confirmMessage=${localize("compressor.delete_confirm", l).replace(
              "{name}",
              group.name || `#${idx + 1}`,
            )}
            destructive
            @confirmed=${() => {
              this._fire(this.compressorGroups.filter((_, i) => i !== idx));
            }}
          ></rs-confirm-button>
        </div>
      </div>
    `;
  }

  private _renderMember(entityId: string, groupIdx: number) {
    const state = this.hass.states[entityId];
    const missing = !state;
    const name = (state?.attributes?.friendly_name as string) || entityId;
    const areaId = this.hass.entities[entityId]?.area_id;
    const areaName = areaId ? this.hass.areas[areaId]?.name : undefined;
    return html`
      <div class="member-row">
        <span class="member-name ${missing ? "member-missing" : ""}"
          >${name}${areaName ? html`<span class="member-area">(${areaName})</span>` : nothing}</span
        >
        <rs-icon-button
          icon="mdi:close"
          .label=${localize("common.remove_named", this.hass.language, { name })}
          @click=${() => {
            const updated = [...this.compressorGroups];
            updated[groupIdx] = {
              ...updated[groupIdx],
              members: updated[groupIdx].members.filter((m) => m !== entityId),
            };
            this._fire(updated);
          }}
        ></rs-icon-button>
      </div>
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
    this._fire(updated);
  }

  private _addGroup() {
    this._fire([
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

  private _fire(groups: CompressorGroup[]) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key: "compressorGroups", value: groups },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-compressor": RsSettingsCompressor;
  }
}

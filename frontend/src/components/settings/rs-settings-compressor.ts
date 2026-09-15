/**
 * rs-settings-compressor – Compressor protection group management.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, CompressorGroup, ConflictResolution } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import "../shared/rs-confirm-button";
import { inputStyles } from "../../styles/input-styles";

@customElement("rs-settings-compressor")
export class RsSettingsCompressor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Array }) public compressorGroups: CompressorGroup[] = [];

  static styles = [
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
      .add-button {
        margin-top: 12px;
      }
      .delete-row {
        margin-top: 16px;
        display: flex;
        justify-content: flex-end;
      }
      .no-groups {
        color: var(--secondary-text-color);
        font-size: 14px;
        padding: 8px 0;
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
      ${
        this.compressorGroups.length === 0
          ? html`<div class="no-groups">${localize("compressor.no_groups", l)}</div>`
          : this.compressorGroups.map((group, idx) => this._renderGroup(group, idx))
      }
      <ha-button class="add-button" @click=${this._addGroup}>
        <ha-icon icon="mdi:plus" slot="icon"></ha-icon>
        ${localize("compressor.add_group", l)}
      </ha-button>
    `;
  }

  private _renderGroup(group: CompressorGroup, idx: number) {
    const l = this.hass.language;
    return html`
      <div class="group-card">
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
          <div>
            <ha-textfield
              type="number"
              .value=${String(group.min_run_minutes)}
              .label=${localize("compressor.min_run", l)}
              .suffix=${localize("compressor.min_run_suffix", l)}
              min="1"
              max="60"
              step="1"
              @change=${(e: Event) => {
                const v = parseInt((e.target as HTMLInputElement).value, 10);
                if (!isNaN(v) && v >= 1 && v <= 60) this._updateGroup(idx, "min_run_minutes", v);
              }}
            ></ha-textfield>
            <div class="field-hint">${localize("compressor.min_run_hint", l)}</div>
          </div>
          <div>
            <ha-textfield
              type="number"
              .value=${String(group.min_off_minutes)}
              .label=${localize("compressor.min_off", l)}
              .suffix=${localize("compressor.min_off_suffix", l)}
              min="1"
              max="30"
              step="1"
              @change=${(e: Event) => {
                const v = parseInt((e.target as HTMLInputElement).value, 10);
                if (!isNaN(v) && v >= 1 && v <= 30) this._updateGroup(idx, "min_off_minutes", v);
              }}
            ></ha-textfield>
            <div class="field-hint">${localize("compressor.min_off_hint", l)}</div>
          </div>
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
          <ha-formfield .label=${localize("compressor.enforce_uniform_mode", l)}>
            <ha-switch
              .checked=${group.enforce_uniform_mode || false}
              @change=${(e: Event) => {
                this._updateGroup(
                  idx,
                  "enforce_uniform_mode",
                  (e.target as HTMLInputElement).checked,
                );
              }}
            ></ha-switch>
          </ha-formfield>
          <div class="field-hint">${localize("compressor.enforce_uniform_mode_hint", l)}</div>
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
        <ha-icon-button
          .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
          @click=${() => {
            const updated = [...this.compressorGroups];
            updated[groupIdx] = {
              ...updated[groupIdx],
              members: updated[groupIdx].members.filter((m) => m !== entityId),
            };
            this._fire(updated);
          }}
        ></ha-icon-button>
      </div>
    `;
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

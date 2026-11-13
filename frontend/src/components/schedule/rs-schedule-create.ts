/**
 * rs-schedule-create – Form for a new Home Assistant schedule helper: name and a start week.
 * Fires `schedule-created` `{ entityId, kind }` once the helper exists and `create-cancelled`.
 * Used by the room's schedule dialog and the schedule overview.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { errorText } from "../../utils/errors";
import { COVER_TEMPLATES, TEMPLATES, emptyWeek } from "../../utils/schedule-week";
import { createSchedule } from "../../utils/schedule-api";
import { tokens } from "../../styles/tokens";
import { inputStyles } from "../../styles/input-styles";
import "../shared/rs-radio-group";

@customElement("rs-schedule-create")
export class RsScheduleCreate extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public defaultName = "";
  /** A cover schedule offers cover templates (positions) instead of the heating ones. */
  @property({ type: String }) public kind: "climate" | "cover" = "climate";
  /** Without its own border, e.g. inside a dialog. */
  @property({ type: Boolean, reflect: true }) public plain = false;

  @state() private _name = "";
  @state() private _template = "";
  @state() private _busy = false;
  @state() private _error = "";

  connectedCallback() {
    super.connectedCallback();
    this._name = this.defaultName;
  }

  firstUpdated() {
    this.renderRoot.querySelector<HTMLElement>("ha-textfield")?.focus();
  }

  render() {
    const l = this.hass.language;
    return html`<div class="create">
      <ha-textfield
        .label=${localize("schedule_editor.name", l)}
        .value=${this._name}
        required
        autocomplete="off"
        @input=${(e: Event) => (this._name = (e.target as HTMLInputElement).value)}
        @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this._create()}
      ></ha-textfield>
      <span class="create-label">${localize("schedule_editor.start_with", l)}</span>
      <rs-radio-group
        .options=${[
          { value: "", label: localize("schedule_editor.tpl_empty", l) },
          ...this._templates().map((t) => ({
            value: t.id,
            label: `${localize(`schedule_editor.tpl_${t.id}` as "schedule_editor.tpl_split", l)} (${localize(
              `schedule_editor.tpl_${t.id}_sub` as "schedule_editor.tpl_split_sub",
              l,
            )})`,
          })),
        ]}
        .selected=${this._template}
        @selected-changed=${(e: CustomEvent<string>) => {
          e.stopPropagation();
          this._template = e.detail;
        }}
      ></rs-radio-group>
      ${this._error ? html`<span class="create-error" role="alert">${this._error}</span>` : nothing}
      <div class="create-actions">
        <ha-button
          appearance="plain"
          ?disabled=${this._busy}
          @click=${() => this.dispatchEvent(new CustomEvent("create-cancelled"))}
          >${localize("detail.cancel", l)}</ha-button
        >
        <ha-button .loading=${this._busy} ?disabled=${!this._name.trim()} @click=${this._create}
          >${localize("schedule_editor.create_confirm", l)}</ha-button
        >
      </div>
    </div>`;
  }

  private _templates() {
    return this.kind === "cover" ? COVER_TEMPLATES : TEMPLATES;
  }

  protected willUpdate(changed: Map<string, unknown>) {
    // A template of the other kind is no choice there
    if (changed.has("kind") && !this._templates().some((t) => t.id === this._template)) {
      this._template = "";
    }
  }

  private _create = async () => {
    const name = this._name.trim();
    if (!name || this._busy) return;
    this._busy = true;
    this._error = "";
    try {
      const template = this._templates().find((t) => t.id === this._template);
      const entityId = await createSchedule(
        this.hass,
        name,
        template ? template.make() : emptyWeek(),
      );
      this.dispatchEvent(
        new CustomEvent("schedule-created", { detail: { entityId, kind: this.kind } }),
      );
    } catch (err) {
      const l = this.hass.language;
      this._error = errorText(err, localize("schedule_editor.create_error", l), l);
    } finally {
      this._busy = false;
    }
  };

  static styles = [
    tokens,
    inputStyles,
    css`
      :host {
        display: block;
      }
      .create {
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin: 4px 0 16px;
        padding: 12px 14px;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
      }
      :host([plain]) .create {
        margin: 0;
        padding: 0;
        border: none;
      }
      .create-label {
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      .create-actions {
        display: flex;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: 8px;
      }
      .create-error {
        color: var(--rs-err-text);
        font-size: 13px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-schedule-create": RsScheduleCreate;
  }
}

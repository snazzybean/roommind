import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../types";
import { localize } from "../utils/localize";
import "./rs-section-card";
import "./shared/rs-toggle-row";

@customElement("rs-presence-section")
export class RsPresenceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ attribute: false }) public selectedPresencePersons: string[] = [];
  @property({ type: Boolean }) public ignorePresence = false;
  @property({ type: Boolean }) public editing = false;
  @property() public language = "en";

  static styles = css`
    :host {
      display: block;
    }

    .presence-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .presence-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 13px;
      font-family: inherit;
      background: transparent;
      color: var(--secondary-text-color);
      transition:
        background 0.15s,
        border-color 0.15s,
        color 0.15s;
    }

    .presence-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-chip.active {
      border-color: var(--primary-color);
      color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .presence-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s;
    }

    .presence-row.home {
      background: rgba(76, 175, 80, 0.1);
    }

    .presence-row.away {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .presence-row.home .presence-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .presence-row.away .presence-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .presence-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .presence-row.home .presence-name {
      color: var(--primary-text-color);
    }

    .presence-row.away .presence-name {
      color: var(--secondary-text-color);
    }

    .presence-state {
      font-size: 12px;
      white-space: nowrap;
    }

    .presence-row.home .presence-state {
      color: #2e7d32;
    }

    .presence-row.away .presence-state {
      color: var(--secondary-text-color);
    }

    .section-divider {
      border-top: 1px solid var(--divider-color, #e0e0e0);
      margin: 8px 0;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .help-content {
      padding: 0 16px 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }
  `;

  render() {
    if (!this.presenceEnabled || this.presencePersons.length === 0) return nothing;

    return html`
      <rs-section-card
        icon="mdi:home-account"
        .heading=${localize("room.section.presence", this.language)}
        hasInfo
        editable
        .editing=${this.editing}
        .doneLabel=${localize("schedule.done", this.language)}
        @edit-click=${this._onEditClick}
        @done-click=${this._onDoneClick}
      >
        <div slot="info">${localize("presence.ignore_hint", this.language)}</div>
        <rs-toggle-row
          .label=${localize("presence.ignore_toggle", this.language)}
          .checked=${this.ignorePresence}
          @toggle-changed=${this._onIgnoreToggle}
        ></rs-toggle-row>
        ${!this.ignorePresence ? html`<div class="section-divider"></div>` : nothing}
        ${this.ignorePresence
          ? nothing
          : this.editing
            ? this._renderEditMode()
            : this._renderViewMode()}
      </rs-section-card>
    `;
  }

  private _renderEditMode() {
    return html`
      <div style="padding: 8px 16px 16px">
        <div class="presence-chips">
          ${this.presencePersons.map((pid) => {
            const active = this.selectedPresencePersons.includes(pid);
            const name =
              this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join(".");
            return html`
              <button
                class="presence-chip ${active ? "active" : ""}"
                @click=${() => this._onTogglePerson(pid, active)}
              >
                <ha-icon
                  icon=${active ? "mdi:account-check" : "mdi:account-outline"}
                  style="--mdc-icon-size: 16px"
                ></ha-icon>
                ${name}
              </button>
            `;
          })}
        </div>
        <ha-expansion-panel
          outlined
          .header=${localize("presence.room_help_header", this.language)}
          style="margin-top: 12px"
        >
          <div class="help-content">
            <p>${localize("presence.room_help_body", this.language)}</p>
          </div>
        </ha-expansion-panel>
      </div>
    `;
  }

  private _renderViewMode() {
    return html`
      <div style="padding: 8px 16px 16px">
        ${this.selectedPresencePersons.length > 0
          ? html`
              <div class="presence-list">
                ${this.selectedPresencePersons.map((pid) => {
                  const name =
                    this.hass.states[pid]?.attributes?.friendly_name ??
                    pid.split(".").slice(1).join(".");
                  const st = this.hass.states[pid]?.state;
                  const isHome =
                    pid.startsWith("person.") || pid.startsWith("device_tracker.")
                      ? st === "home"
                      : st === "on";
                  return html`
                    <div class="presence-row ${isHome ? "home" : "away"}">
                      <span class="presence-dot"></span>
                      <span class="presence-name">${name}</span>
                      <span class="presence-state"
                        >${isHome
                          ? localize("presence.state_home", this.language)
                          : localize("presence.state_away", this.language)}</span
                      >
                    </div>
                  `;
                })}
              </div>
            `
          : html`
              <span class="field-hint"
                >${localize("presence.room_none_assigned", this.language)}</span
              >
            `}
      </div>
    `;
  }

  private _onEditClick() {
    this.editing = true;
    this.dispatchEvent(
      new CustomEvent("editing-changed", {
        detail: { editing: true },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onDoneClick() {
    this.editing = false;
    this.dispatchEvent(
      new CustomEvent("editing-changed", {
        detail: { editing: false },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onIgnoreToggle(e: CustomEvent<boolean>) {
    this.dispatchEvent(
      new CustomEvent("ignore-presence-changed", {
        detail: e.detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onTogglePerson(pid: string, currentlyActive: boolean) {
    let next: string[];
    if (currentlyActive) {
      next = this.selectedPresencePersons.filter((p) => p !== pid);
    } else {
      next = [...this.selectedPresencePersons, pid];
    }
    this.dispatchEvent(
      new CustomEvent("presence-persons-changed", {
        detail: next,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-presence-section": RsPresenceSection;
  }
}

import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../types";
import { localize } from "../utils/localize";
import { tokens } from "../styles/tokens";
import { formStyles } from "../styles/form-styles";
import "./shared/rs-icon-button";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";

const SETTINGS_PATH = "/roommind/settings/presence";

@customElement("rs-presence-section")
export class RsPresenceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ attribute: false }) public selectedPresencePersons: string[] = [];
  @property({ type: Boolean }) public ignorePresence = false;
  @property({ type: Boolean }) public editing = false;
  /** Global presence_away_action: eco or devices off. */
  @property({ type: String }) public awayAction: "eco" | "off" = "eco";
  @property() public language = "en";

  private _focusPersons = false;

  static styles = [
    tokens,
    formStyles,
    css`
      :host {
        display: block;
        --rs-form-inline: var(--rs-space-4);
      }

      .rows {
        display: flex;
        flex-direction: column;
      }

      .group-sub {
        margin: var(--rs-space-4) 0 0;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }
    `,
  ];

  /** True when the entity is gone from Home Assistant, i.e. dead config (#397). */
  private _isMissing(pid: string): boolean {
    return !this.hass.states[pid];
  }

  private _name(pid: string): string {
    return String(
      this.hass.states[pid]?.attributes?.friendly_name ?? pid.split(".").slice(1).join("."),
    );
  }

  /** Home/away as the backend reads it; unavailable and unknown count as home there. */
  private _state(pid: string): { text: string; home: boolean } {
    const l = this.language;
    const st = this.hass.states[pid]?.state;
    if (st === undefined || st === "unavailable" || st === "unknown") {
      return { text: localize("detail.devices.unavailable", l), home: false };
    }
    const home =
      pid.startsWith("person.") || pid.startsWith("device_tracker.") ? st === "home" : st === "on";
    return { text: localize(home ? "presence.state_home" : "presence.state_away", l), home };
  }

  /** Why the room's presence settings have no effect right now, if they have none. */
  private _inactiveReason(): string {
    if (!this.presenceEnabled) return localize("presence.room_disabled", this.language);
    if (this.presencePersons.length === 0) {
      return localize("presence.room_no_persons", this.language);
    }
    return "";
  }

  protected updated(): void {
    if (!this._focusPersons || !this.editing) return;
    this._focusPersons = false;
    const target = this.renderRoot.querySelector<
      HTMLElement & { updateComplete?: Promise<unknown> }
    >(".persons rs-icon-button, .persons rs-list-row[clickable]");
    void target?.updateComplete?.then(() => target.focus());
  }

  render() {
    return this.editing ? this._renderEditMode() : this._renderViewMode();
  }

  private _renderEditMode() {
    const l = this.language;
    const reason = this._inactiveReason();
    return html`
      ${
        reason
          ? html`<div class="group">
              <p class="note warn">
                <ha-icon icon="mdi:information-outline" aria-hidden="true"></ha-icon>
                <span>${reason}</span>
              </p>
              ${this._renderSettingsLink()}
            </div>`
          : nothing
      }
      <div class="group">
        <rs-list-row
          switch
          wrap
          icon="mdi:home-off-outline"
          .heading=${localize("presence.ignore_toggle", l)}
          .secondary=${localize("presence.ignore_sub", l)}
          .checked=${this.ignorePresence}
          @toggle-changed=${this._onIgnoreToggle}
        >
          <rs-info-icon slot="end" .text=${localize("presence.ignore_info", l)}></rs-info-icon>
        </rs-list-row>
      </div>
      ${this.ignorePresence ? nothing : this._renderPersons()}
    `;
  }

  private _renderSettingsLink() {
    return html`<rs-list-row
      href=${SETTINGS_PATH}
      chevron
      icon="mdi:cog-outline"
      .heading=${localize("presence.open_settings", this.language)}
      @click=${this._onSettingsClick}
    ></rs-list-row>`;
  }

  private _renderPersons() {
    const l = this.language;
    const selected = this.selectedPresencePersons;
    const others = this.presencePersons.filter((pid) => !selected.includes(pid));
    return html`<div class="group persons">
      <h4 class="group-title">
        ${localize("presence.room_persons", l)}
        <rs-info-icon .text=${localize("presence.persons_info", l)}></rs-info-icon>
      </h4>
      <div class="rows">
        ${
          selected.length
            ? selected.map((pid) => this._renderAssigned(pid))
            : html`<p class="note">${localize(this._allCountKey(), l)}</p>`
        }
        ${
          others.length
            ? html`<p class="group-sub">
                  ${localize(selected.length ? "presence.others" : "presence.only_some", l)}
                </p>
                ${others.map(
                  (pid) =>
                    html`<rs-list-row
                      clickable
                      plain-icon
                      icon="mdi:plus"
                      .heading=${this._name(pid)}
                      .secondary=${localize(
                        // Everybody counts already; picking one narrows the room to that person
                        selected.length ? "detail.devices.add_suggestion" : "presence.only_this",
                        l,
                      )}
                      .value=${this._state(pid).text}
                      @row-click=${() => this._setPersons([...selected, pid])}
                    ></rs-list-row>`,
                )}`
            : nothing
        }
      </div>
    </div>`;
  }

  private _allCountKey() {
    return this.awayAction === "off"
      ? ("presence.room_none_assigned_off" as const)
      : ("presence.room_none_assigned" as const);
  }

  private _renderAssigned(pid: string) {
    const l = this.language;
    const name = this._name(pid);
    const missing = this._isMissing(pid);
    const state = this._state(pid);
    return html`<rs-list-row
      .icon=${missing ? "mdi:alert-circle-outline" : "mdi:account"}
      .variant=${missing ? "warn" : "default"}
      .iconColor=${!missing && state.home ? "var(--rs-ok)" : ""}
      .heading=${name}
      .secondary=${missing ? localize("presence.missing_entity_hint", l) : ""}
      .value=${missing ? "" : state.text}
    >
      <rs-icon-button
        slot="end"
        size="sm"
        icon="mdi:close"
        .label=${localize("common.remove_named", l, { name })}
        @click=${() => this._setPersons(this.selectedPresencePersons.filter((p) => p !== pid))}
      ></rs-icon-button>
    </rs-list-row>`;
  }

  private _renderViewMode() {
    const l = this.language;
    const reason = this._inactiveReason();
    if (reason || this.ignorePresence || this.selectedPresencePersons.length === 0) {
      const heading = reason
        ? "presence.room_inactive"
        : this.ignorePresence
          ? "presence.ignore_toggle"
          : "detail.presence.global";
      const secondary = reason
        ? reason
        : localize(this.ignorePresence ? "presence.tile_ignored" : this._allCountKey(), l);
      return html`<rs-list-row
        clickable
        chevron
        icon=${reason || this.ignorePresence ? "mdi:home-off-outline" : "mdi:home-account"}
        .heading=${localize(heading, l)}
        .secondary=${secondary}
        @row-click=${this._fireEdit}
      ></rs-list-row>`;
    }
    return this.selectedPresencePersons.map((pid) => {
      const missing = this._isMissing(pid);
      const state = this._state(pid);
      return html`<rs-list-row
        clickable
        chevron
        icon=${missing ? "mdi:alert-circle-outline" : "mdi:account"}
        .variant=${missing ? "warn" : "default"}
        .iconColor=${!missing && state.home ? "var(--rs-ok)" : ""}
        .heading=${this._name(pid)}
        .secondary=${missing ? localize("presence.missing_entity_hint", l) : ""}
        .value=${missing ? "" : state.text}
        @row-click=${this._fireEdit}
      ></rs-list-row>`;
    });
  }

  private _fireEdit(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }

  private _onSettingsClick(e: MouseEvent) {
    // Ctrl/Cmd/Shift/middle click keep the browser's "open in new tab".
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    this.dispatchEvent(
      new CustomEvent("open-settings", {
        detail: { category: "presence" },
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

  private _setPersons(next: string[]) {
    this._focusPersons = true;
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

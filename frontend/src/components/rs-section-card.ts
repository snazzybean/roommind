import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { infoIconStyles } from "../styles/info-icon-styles";
import "./shared/rs-badge";

const PENCIL_PATH =
  "M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z";

const CHECK_PATH =
  "M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";

@customElement("rs-section-card")
export class RsSectionCard extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public heading = "";
  @property({ type: Boolean }) public editable = false;
  @property({ type: Boolean }) public editing = false;
  @property({ type: String }) public doneLabel = "";
  @property({ type: String }) public badge = "";
  @property({ type: String }) public badgeHint = "";
  @property({ type: Boolean }) public hasInfo = false;
  @state() private _infoExpanded = false;

  static styles = [
    infoIconStyles,
    css`
      :host {
        display: block;
      }

      ha-card {
        overflow: hidden;
        min-width: 0;
      }

      .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 16px 20px 12px;
      }

      .section-icon {
        --mdc-icon-size: 18px;
        opacity: 0.7;
      }

      .section-title {
        font-size: 15px;
        font-weight: 500;
        color: var(--primary-text-color);
        margin: 0;
        flex: 1;
      }

      .edit-btn {
        --mdc-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        margin: -4px -8px -4px 0;
      }

      .done-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        background: none;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 16px;
        color: var(--primary-color);
        font-size: 12px;
        font-weight: 500;
        padding: 4px 12px 4px 8px;
        cursor: pointer;
        transition: background 0.15s;
        --mdc-icon-size: 14px;
      }

      .done-btn:hover {
        background: rgba(3, 169, 244, 0.05);
      }

      .section-info {
        padding: 0 20px 8px;
      }

      .section-body {
        padding: 0 20px 20px;
      }
    `,
  ];

  render() {
    return html`
      <ha-card>
        <div class="section-header">
          <ha-icon class="section-icon" icon=${this.icon}></ha-icon>
          <h3 class="section-title">${this.heading}</h3>
          ${this.badge
            ? html`<rs-badge .label=${this.badge} .hint=${this.badgeHint}></rs-badge>`
            : nothing}
          ${this.hasInfo
            ? html`
                <ha-icon
                  class="info-icon ${this._infoExpanded ? "info-active" : ""}"
                  icon="mdi:information-outline"
                  @click=${this._toggleInfo}
                ></ha-icon>
              `
            : nothing}
          ${this.editable && !this.editing
            ? html`
                <ha-icon-button
                  class="edit-btn"
                  .path=${PENCIL_PATH}
                  @click=${this._onEditClick}
                ></ha-icon-button>
              `
            : nothing}
          ${this.editable && this.editing
            ? html`
                <button class="done-btn" @click=${this._onDoneClick}>
                  <ha-icon-button
                    style="--mdc-icon-button-size: 20px; --mdc-icon-size: 14px; pointer-events: none;"
                    .path=${CHECK_PATH}
                  ></ha-icon-button>
                  ${this.doneLabel}
                </button>
              `
            : nothing}
        </div>
        ${this._infoExpanded
          ? html`<div class="section-info"><div class="info-panel"><slot name="info"></slot></div></div>`
          : nothing}
        <div class="section-body">
          <slot></slot>
        </div>
      </ha-card>
    `;
  }

  private _toggleInfo() {
    this._infoExpanded = !this._infoExpanded;
  }

  private _onEditClick() {
    this.dispatchEvent(
      new CustomEvent("edit-click", { bubbles: true, composed: true })
    );
  }

  private _onDoneClick() {
    this.dispatchEvent(
      new CustomEvent("done-click", { bubbles: true, composed: true })
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-section-card": RsSectionCard;
  }
}

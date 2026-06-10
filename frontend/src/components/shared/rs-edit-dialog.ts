import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

const CLOSE_PATH =
  "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z";
const INFO_PATH =
  "M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z";

@customElement("rs-edit-dialog")
export class RsEditDialog extends LitElement {
  @property({ type: Boolean, reflect: true }) public open = false;
  @property({ type: String }) public heading = "";
  @property({ type: String }) public icon = "";
  @property({ type: Boolean }) public hasInfo = false;

  @state() private _infoExpanded = false;

  private _onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && this.open) {
      e.stopPropagation();
      this._close();
    }
  };

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this._onKeyDown);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this._onKeyDown);
  }

  static styles = css`
    :host {
      display: contents;
    }

    .backdrop {
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgba(0, 0, 0, 0.55);
      backdrop-filter: blur(2px);
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 32px 16px;
      box-sizing: border-box;
      overflow-y: auto;
      animation: fade-in 0.18s ease-out;
    }

    @media (max-width: 600px) {
      .backdrop {
        padding: 0;
        align-items: stretch;
      }
    }

    .dialog {
      background: var(--card-background-color, #1c1c1c);
      color: var(--primary-text-color);
      border-radius: 14px;
      box-shadow: 0 24px 48px rgba(0, 0, 0, 0.5);
      width: 100%;
      max-width: 760px;
      display: flex;
      flex-direction: column;
      max-height: calc(100vh - 64px);
      animation: pop-in 0.18s ease-out;
    }

    @media (min-width: 1400px) {
      .dialog {
        max-width: 880px;
      }
    }

    @media (max-width: 600px) {
      .dialog {
        max-width: 100%;
        max-height: 100vh;
        border-radius: 0;
      }
    }

    .dialog-header {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--divider-color, rgba(255, 255, 255, 0.08));
    }

    .dialog-icon {
      --mdc-icon-size: 20px;
      opacity: 0.7;
      flex-shrink: 0;
      margin-right: 8px;
    }

    .dialog-title {
      flex: 1;
      font-size: 16px;
      font-weight: 500;
      margin: 0;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .info-btn {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      transition:
        color 0.15s,
        background 0.15s;
      border-radius: 50%;
    }

    .info-btn.active {
      color: var(--primary-color);
      background: rgba(3, 169, 244, 0.12);
    }

    .close-btn {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      margin: -6px -10px -6px 0;
    }

    .dialog-body {
      flex: 1;
      overflow-y: auto;
      padding: 20px 24px 24px;
    }

    .dialog-body ::slotted(*) {
      display: block;
    }

    .info-panel {
      margin-bottom: 16px;
      padding: 12px 14px;
      background: rgba(3, 169, 244, 0.06);
      border: 1px solid rgba(3, 169, 244, 0.18);
      border-radius: 10px;
      font-size: 13px;
      line-height: 1.6;
      color: var(--primary-text-color);
      animation: info-fade 0.18s ease-out;
    }

    .info-panel ::slotted(*) {
      display: block;
    }

    @keyframes fade-in {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }

    @keyframes pop-in {
      from {
        opacity: 0;
        transform: scale(0.97);
      }
      to {
        opacity: 1;
        transform: scale(1);
      }
    }

    @keyframes info-fade {
      from {
        opacity: 0;
        transform: translateY(-4px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `;

  render() {
    if (!this.open) return nothing;
    return html`
      <div class="backdrop" @click=${this._onBackdropClick} role="dialog" aria-modal="true">
        <div class="dialog" @click=${(e: Event) => e.stopPropagation()}>
          <div class="dialog-header">
            ${this.icon ? html`<ha-icon class="dialog-icon" icon=${this.icon}></ha-icon>` : nothing}
            <h3 class="dialog-title">${this.heading}</h3>
            ${this.hasInfo
              ? html`<ha-icon-button
                  class="info-btn ${this._infoExpanded ? "active" : ""}"
                  .path=${INFO_PATH}
                  @click=${this._toggleInfo}
                ></ha-icon-button>`
              : nothing}
            <ha-icon-button
              class="close-btn"
              .path=${CLOSE_PATH}
              @click=${this._close}
            ></ha-icon-button>
          </div>
          <div class="dialog-body">
            ${this.hasInfo && this._infoExpanded
              ? html`<div class="info-panel"><slot name="info"></slot></div>`
              : nothing}
            <slot></slot>
          </div>
        </div>
      </div>
    `;
  }

  private _onBackdropClick(e: Event) {
    if (e.target === e.currentTarget) {
      this._close();
    }
  }

  private _toggleInfo() {
    this._infoExpanded = !this._infoExpanded;
  }

  private _close() {
    this._infoExpanded = false;
    // Namespaced event: HA reserves the bare "dialog-closed" name for its own
    // dialog manager (read as `e.detail.dialog`). A composed event of that name
    // with a null detail bubbles up to <home-assistant> and crashes HA's
    // handler ("can't access property 'dialog', e.detail is null"), which broke
    // the room edit dialogs after HA 2026's dialog rework. Use a RoomMind-
    // specific name so it can never collide with HA's listener.
    this.dispatchEvent(new CustomEvent("rs-dialog-closed", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-edit-dialog": RsEditDialog;
  }
}

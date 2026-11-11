import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { localize, uiLanguage } from "../../utils/localize";
import { deepActiveElement, tabbables } from "../../utils/focus";
import type { RsIconButton } from "./rs-icon-button";
import "./rs-icon-button";

/**
 * The panel's modal dialog. Takes the focus on open (close button), keeps Tab inside and gives
 * the focus back to the opener when it closes or is removed. Not a native `<dialog>`: a modal one
 * makes everything outside inert, and HA picker overlays can render outside the dialog.
 */
@customElement("rs-edit-dialog")
export class RsEditDialog extends LitElement {
  @property({ type: Boolean, reflect: true }) public open = false;
  @property({ type: String }) public heading = "";
  @property({ type: String }) public icon = "";
  @property({ type: Boolean }) public hasInfo = false;

  @state() private _infoExpanded = false;

  private _opener: HTMLElement | null = null;

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
    // Callers remove the dialog on close instead of clearing `open`
    this._restoreFocus();
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("open") && this.open && !this._opener) this._opener = deepActiveElement();
  }

  protected updated(changed: PropertyValues<this>): void {
    if (!changed.has("open")) return;
    if (this.open) void this._focusClose();
    else this._restoreFocus();
  }

  private async _focusClose() {
    const btn = this.renderRoot.querySelector<RsIconButton>(".close-btn");
    if (!btn) return;
    await btn.updateComplete;
    btn.focusQuietly();
  }

  private _restoreFocus() {
    const opener = this._opener;
    this._opener = null;
    if (opener?.isConnected) opener.focus();
  }

  /** Focus left the dialog through one of the guards around it: wrap to the other end. */
  private _wrap(toStart: boolean) {
    const dialog = this.renderRoot.querySelector(".dialog");
    if (!dialog) return;
    const stops = tabbables(dialog);
    const target = toStart ? stops[0] : stops[stops.length - 1];
    if (target) target.focus();
    else void this._focusClose();
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

    .info-btn,
    .close-btn {
      --rs-icon-button-color: var(--secondary-text-color);
    }

    .info-btn.active {
      --rs-icon-button-color: var(--primary-color);
      --rs-icon-button-background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    }

    .close-btn {
      margin: -8px -12px -8px 0;
    }

    .guard {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      opacity: 0;
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
    const l = uiLanguage();
    return html`
      <div class="backdrop" @click=${this._onBackdropClick}>
        <span class="guard" tabindex="0" @focus=${() => this._wrap(false)}></span>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="title"
          @click=${(e: Event) => e.stopPropagation()}
        >
          <div class="dialog-header">
            ${this.icon ? html`<ha-icon class="dialog-icon" icon=${this.icon}></ha-icon>` : nothing}
            <h3 class="dialog-title" id="title">${this.heading}</h3>
            ${
              this.hasInfo
                ? html`<rs-icon-button
                    class="info-btn ${this._infoExpanded ? "active" : ""}"
                    size="sm"
                    icon="mdi:information-outline"
                    .label=${localize("common.help", l)}
                    .pressed=${this._infoExpanded}
                    @click=${this._toggleInfo}
                  ></rs-icon-button>`
                : nothing
            }
            <rs-icon-button
              class="close-btn"
              size="sm"
              icon="mdi:close"
              .label=${localize("common.close", l)}
              @click=${this._close}
            ></rs-icon-button>
          </div>
          <div class="dialog-body">
            ${
              this.hasInfo && this._infoExpanded
                ? html`<div class="info-panel"><slot name="info"></slot></div>`
                : nothing
            }
            <slot></slot>
          </div>
        </div>
        <span class="guard" tabindex="0" @focus=${() => this._wrap(true)}></span>
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

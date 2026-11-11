import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import { localize, uiLanguage } from "../../utils/localize";
import "./rs-edit-dialog";

/**
 * The panel's one confirmation for destructive actions, built on rs-edit-dialog (focus trap,
 * focus return, Esc closes only the top dialog, so it can open over another dialog).
 * `message` is the first paragraph, the default slot takes further notes, slot `extra` an
 * additional action on the left. Fires `confirm` and `cancel` (not composed); while `busy`
 * the buttons wait and closing is blocked. `error` shows inside the dialog.
 */
@customElement("rs-confirm-dialog")
export class RsConfirmDialog extends LitElement {
  @property({ type: Boolean }) public open = false;
  @property({ type: String }) public heading = "";
  @property({ type: String }) public icon = "mdi:alert-outline";
  @property({ type: String }) public message = "";
  @property({ type: String }) public confirmLabel = "";
  @property({ type: Boolean }) public destructive = true;
  @property({ type: Boolean }) public busy = false;
  @property({ type: String }) public error = "";

  static styles = [
    tokens,
    css`
      :host {
        display: contents;
      }

      p {
        margin: 0 0 var(--rs-space-3);
        font-size: var(--rs-font-md);
        line-height: 1.5;
      }

      ::slotted(p) {
        margin: 0 0 var(--rs-space-3) !important;
        font-size: var(--rs-font-md);
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .actions {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: flex-end;
        gap: var(--rs-space-2);
        margin-top: var(--rs-space-4);
      }

      .grow {
        flex: 1;
      }
    `,
  ];

  render() {
    if (!this.open) return nothing;
    const l = uiLanguage();
    return html`<rs-edit-dialog
      open
      .icon=${this.icon}
      .heading=${this.heading}
      .error=${this.error}
      @rs-dialog-closed=${this._onClosed}
    >
      ${this.message ? html`<p>${this.message}</p>` : nothing}
      <slot></slot>
      <div class="actions">
        <slot name="extra"></slot>
        <span class="grow"></span>
        <ha-button appearance="plain" ?disabled=${this.busy} @click=${this._cancel}
          >${localize("detail.cancel", l)}</ha-button
        >
        <ha-button
          variant=${this.destructive ? "danger" : "brand"}
          .loading=${this.busy}
          @click=${this._confirm}
          >${this.confirmLabel}</ha-button
        >
      </div>
    </rs-edit-dialog>`;
  }

  /** Stops the close event here: it is composed and would close a dialog around this one. */
  private _onClosed(e: Event) {
    e.stopPropagation();
    this._cancel();
  }

  private _cancel() {
    if (this.busy) return;
    this.dispatchEvent(new CustomEvent("cancel"));
  }

  private _confirm() {
    if (this.busy) return;
    this.dispatchEvent(new CustomEvent("confirm"));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-confirm-dialog": RsConfirmDialog;
  }
}

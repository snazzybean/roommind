import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import { floatingStyles } from "../../styles/floating-styles";
import { hideFromTopLayer, positionNear, showInTopLayer } from "../../utils/popover";
import "./rs-icon-button";

export interface RsMenuItem {
  value: string;
  label: string;
  icon?: string;
  disabled?: boolean;
}

/**
 * Overflow menu: a ⋮ button opening a list of actions in the top layer. Arrow keys move,
 * Enter picks, Esc/Tab/outside tap closes. Fires `menu-select` with `{ value }`.
 * With `text` the trigger is an outlined button with icon, text and chevron instead; the text
 * hides on narrow screens and stays the accessible name.
 */
@customElement("rs-menu")
export class RsMenu extends LitElement {
  @property({ attribute: false }) public items: RsMenuItem[] = [];
  /** Accessible name and tooltip of the trigger. */
  @property({ type: String }) public label = "";
  @property({ type: String }) public icon = "mdi:dots-vertical";
  @property({ type: String }) public size: "sm" | "md" = "sm";
  /** Visible text: turns the trigger into a labelled button. */
  @property({ type: String }) public text = "";
  @property({ type: Boolean, reflect: true }) public disabled = false;

  @state() private _open = false;

  static styles = [
    tokens,
    floatingStyles,
    css`
      :host {
        display: inline-flex;
        position: relative;
      }

      [role="menu"] {
        min-width: 200px;
        max-width: min(320px, calc(100vw - 16px));
        padding: 4px;
        display: flex;
        flex-direction: column;
      }

      [role="menu"]:popover-open {
        padding: 4px;
      }

      [role="menuitem"] {
        display: flex;
        align-items: center;
        gap: 12px;
        min-height: var(--rs-touch);
        padding: 0 12px;
        border: none;
        border-radius: 6px;
        background: none;
        color: var(--primary-text-color);
        font: inherit;
        font-size: var(--rs-font-md);
        text-align: left;
        cursor: pointer;
        --mdc-icon-size: 20px;
      }

      [role="menuitem"] ha-icon {
        color: var(--secondary-text-color);
      }

      [role="menuitem"]:hover:not(:disabled),
      [role="menuitem"]:focus-visible {
        background: var(--rs-fill-strong);
        outline: none;
      }

      [role="menuitem"]:disabled {
        opacity: 0.4;
        cursor: default;
      }

      .text-trigger {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 36px;
        padding: 0 10px 0 12px;
        border: 1px solid var(--rs-border);
        border-radius: 18px;
        background: none;
        color: var(--primary-text-color);
        font: inherit;
        font-size: 13px;
        font-weight: 500;
        white-space: nowrap;
        cursor: pointer;
        --mdc-icon-size: 18px;
        transition: background-color 0.15s ease;
      }

      @media (pointer: coarse) {
        .text-trigger {
          height: var(--rs-touch);
        }
      }

      .text-trigger ha-icon {
        color: var(--secondary-text-color);
      }

      .text-trigger .chevron {
        --mdc-icon-size: 16px;
      }

      .text-trigger:hover:not(:disabled) {
        background: var(--rs-fill);
      }

      .text-trigger:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      .text-trigger:disabled {
        opacity: 0.4;
        cursor: default;
      }

      @media (max-width: 600px) {
        .text-trigger {
          padding: 0 8px 0 10px;
        }
        .text-trigger .text {
          display: none;
        }
      }

      @media (prefers-reduced-motion: reduce) {
        .text-trigger {
          transition: none;
        }
      }
    `,
  ];

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._removeDocListeners();
    this._open = false;
  }

  render() {
    return html`
      ${
        this.text
          ? html`<button
              type="button"
              class="text-trigger"
              aria-label=${this.label || this.text}
              aria-haspopup="menu"
              aria-expanded=${this._open ? "true" : "false"}
              ?disabled=${this.disabled}
              @click=${this._toggle}
              @keydown=${this._onTriggerKey}
            >
              <ha-icon .icon=${this.icon} aria-hidden="true"></ha-icon>
              <span class="text">${this.text}</span>
              <ha-icon class="chevron" icon="mdi:chevron-down" aria-hidden="true"></ha-icon>
            </button>`
          : html`<rs-icon-button
              .icon=${this.icon}
              .label=${this.label}
              .size=${this.size}
              .disabled=${this.disabled}
              haspopup="menu"
              .expanded=${this._open}
              @click=${this._toggle}
              @keydown=${this._onTriggerKey}
            ></rs-icon-button>`
      }
      ${
        this._open
          ? html`<div
              class="floating"
              role="menu"
              aria-label=${this.label}
              @keydown=${this._onMenuKey}
              @click=${(e: Event) => e.stopPropagation()}
            >
              ${this.items.map(
                (item) =>
                  html`<button
                    type="button"
                    role="menuitem"
                    tabindex="-1"
                    ?disabled=${item.disabled}
                    @click=${() => this._select(item)}
                  >
                    ${item.icon ? html`<ha-icon .icon=${item.icon}></ha-icon>` : nothing}
                    <span>${item.label}</span>
                  </button>`,
              )}
            </div>`
          : nothing
      }
    `;
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has("disabled") && this.disabled) this.close();
    if (changed.has("_open") && this._open) {
      const menu = this.renderRoot.querySelector<HTMLElement>("[role=menu]");
      if (!menu) return;
      showInTopLayer(menu);
      positionNear(this, menu, "end");
      this._items()[0]?.focus();
    }
  }

  private _items(): HTMLButtonElement[] {
    return [
      ...this.renderRoot.querySelectorAll<HTMLButtonElement>("[role=menuitem]:not(:disabled)"),
    ];
  }

  private _toggle(e: Event) {
    e.stopPropagation();
    if (this.disabled) return;
    if (this._open) this.close();
    else this._openMenu();
  }

  private _openMenu() {
    this._open = true;
    document.addEventListener("pointerdown", this._onDocPointer, true);
    document.addEventListener("scroll", this._onViewportChange, true);
    window.addEventListener("resize", this._onViewportChange, true);
  }

  public close(refocus = false) {
    if (!this._open) return;
    hideFromTopLayer(this.renderRoot.querySelector<HTMLElement>("[role=menu]"));
    this._open = false;
    this._removeDocListeners();
    if (refocus) {
      this.renderRoot.querySelector("rs-icon-button")?.focusQuietly();
      this.renderRoot.querySelector<HTMLButtonElement>(".text-trigger")?.focus();
    }
  }

  private _select(item: RsMenuItem) {
    if (item.disabled) return;
    this.close(true);
    this.dispatchEvent(
      new CustomEvent("menu-select", {
        detail: { value: item.value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onTriggerKey(e: KeyboardEvent) {
    if (e.key === "ArrowDown" && !this._open && !this.disabled) {
      e.preventDefault();
      this._openMenu();
    }
  }

  private _onMenuKey(e: KeyboardEvent) {
    const items = this._items();
    const idx = items.indexOf(e.composedPath()[0] as HTMLButtonElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      items[(idx + step + items.length) % items.length]?.focus();
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      (e.key === "Home" ? items[0] : items[items.length - 1])?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      this.close(true);
    } else if (e.key === "Tab") {
      this.close();
    }
  }

  private _onDocPointer = (e: Event) => {
    if (!e.composedPath().includes(this)) this.close();
  };

  private _onViewportChange = (e: Event) => {
    // Scrolling inside the menu itself must not close it.
    if (e.type === "scroll" && e.composedPath().includes(this)) return;
    this.close();
  };

  private _removeDocListeners() {
    document.removeEventListener("pointerdown", this._onDocPointer, true);
    document.removeEventListener("scroll", this._onViewportChange, true);
    window.removeEventListener("resize", this._onViewportChange, true);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-menu": RsMenu;
  }
}

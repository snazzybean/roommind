import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { floatingStyles } from "../../styles/floating-styles";
import { hideFromTopLayer, positionNear, showInTopLayer } from "../../utils/popover";

const OPEN_DELAY_MS = 120;
const CLOSE_DELAY_MS = 150;

/**
 * The one tooltip of the panel. Wraps its trigger (default slot); text via `text` or the
 * `content` slot. Mouse hover and keyboard focus show it, Esc and a tap outside close it.
 *
 * - `mode="toggle"` (default): a click/tap on the trigger pins it open and a second one
 *   closes it; for info icons and hint chips. Stops the click so it never reaches a
 *   clickable parent.
 * - `mode="label"`: names an action button (icon buttons); the click is the button's,
 *   it only closes the tooltip.
 */
@customElement("rs-tooltip")
export class RsTooltip extends LitElement {
  @property({ type: String }) public text = "";
  @property({ type: String, reflect: true }) public mode: "toggle" | "label" = "toggle";
  @property({ type: Boolean }) public disabled = false;

  @state() private _open = false;
  private _pinned = false;
  private _openTimer?: ReturnType<typeof setTimeout>;
  private _closeTimer?: ReturnType<typeof setTimeout>;
  private _listening = false;

  static styles = [
    floatingStyles,
    css`
      :host {
        display: inline-flex;
        position: relative;
        vertical-align: middle;
        max-width: 100%;
        min-width: 0;
      }

      .trigger {
        display: inline-flex;
        max-width: 100%;
        min-width: 0;
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    this.addEventListener("pointerenter", this._onEnter);
    this.addEventListener("pointerleave", this._onLeave);
    this.addEventListener("focusin", this._onFocusIn);
    this.addEventListener("focusout", this._onFocusOut);
    this.addEventListener("click", this._onClick);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.removeEventListener("pointerenter", this._onEnter);
    this.removeEventListener("pointerleave", this._onLeave);
    this.removeEventListener("focusin", this._onFocusIn);
    this.removeEventListener("focusout", this._onFocusOut);
    this.removeEventListener("click", this._onClick);
    this._clearTimers();
    this._removeDocListeners();
    this._open = false;
    this._pinned = false;
  }

  /** Open state for parents that style their trigger (e.g. the info icon). */
  get open(): boolean {
    return this._open;
  }

  render() {
    return html`
      <span class="trigger"><slot></slot></span>
      ${
        this._open
          ? html`<div
              class="floating tooltip-surface"
              role="tooltip"
              @click=${(e: Event) => e.stopPropagation()}
            >
              ${this.text ? this.text : nothing}<slot name="content"></slot>
            </div>`
          : nothing
      }
    `;
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has("_open")) {
      const tip = this.renderRoot.querySelector<HTMLElement>(".floating");
      if (this._open && tip) {
        showInTopLayer(tip);
        positionNear(this, tip);
      }
      this.dispatchEvent(new CustomEvent("tooltip-toggle", { detail: { open: this._open } }));
    }
    if (changed.has("text") && this._open) {
      const tip = this.renderRoot.querySelector<HTMLElement>(".floating");
      if (tip) positionNear(this, tip);
    }
  }

  private _hasContent(): boolean {
    return !!this.text || !!this.querySelector(":scope > [slot='content']");
  }

  private _onEnter = (e: PointerEvent) => {
    if (e.pointerType !== "mouse" || this.disabled) return;
    clearTimeout(this._closeTimer);
    if (this._open) return;
    clearTimeout(this._openTimer);
    this._openTimer = setTimeout(() => this._show(), OPEN_DELAY_MS);
  };

  private _onLeave = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    clearTimeout(this._openTimer);
    if (this._pinned) return;
    clearTimeout(this._closeTimer);
    this._closeTimer = setTimeout(() => this.hide(), CLOSE_DELAY_MS);
  };

  private _onFocusIn = (e: FocusEvent) => {
    if (this.disabled) return;
    const target = e.composedPath()[0] as Element | undefined;
    // Only keyboard focus; a mouse or tap focus is followed by the click that decides.
    if (target?.matches?.(":focus-visible")) this._show();
  };

  private _onFocusOut = (e: FocusEvent) => {
    const next = e.relatedTarget as Node | null;
    if (next && (this.contains(next) || this.renderRoot.contains(next))) return;
    this.hide();
  };

  private _onClick = (e: MouseEvent) => {
    if (this.disabled) return;
    if (this.mode === "label") {
      this.hide();
      return;
    }
    e.stopPropagation();
    clearTimeout(this._openTimer);
    if (this._open && this._pinned) {
      this.hide();
    } else {
      this._pinned = true;
      this._show();
    }
  };

  private _show() {
    clearTimeout(this._closeTimer);
    if (!this._hasContent()) return;
    this._open = true;
    this._addDocListeners();
  }

  /** Close the tooltip (also used by parents, e.g. when their trigger starts an action). */
  public hide() {
    this._clearTimers();
    hideFromTopLayer(this.renderRoot?.querySelector<HTMLElement>(".floating"));
    this._open = false;
    this._pinned = false;
    this._removeDocListeners();
  }

  private _onDocPointer = (e: Event) => {
    if (!e.composedPath().includes(this)) this.hide();
  };

  private _onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      this.hide();
    }
  };

  private _onViewportChange = () => this.hide();

  private _addDocListeners() {
    if (this._listening) return;
    this._listening = true;
    document.addEventListener("pointerdown", this._onDocPointer, true);
    document.addEventListener("keydown", this._onKey, true);
    document.addEventListener("scroll", this._onViewportChange, true);
    window.addEventListener("resize", this._onViewportChange, true);
  }

  private _removeDocListeners() {
    if (!this._listening) return;
    this._listening = false;
    document.removeEventListener("pointerdown", this._onDocPointer, true);
    document.removeEventListener("keydown", this._onKey, true);
    document.removeEventListener("scroll", this._onViewportChange, true);
    window.removeEventListener("resize", this._onViewportChange, true);
  }

  private _clearTimers() {
    clearTimeout(this._openTimer);
    clearTimeout(this._closeTimer);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-tooltip": RsTooltip;
  }
}

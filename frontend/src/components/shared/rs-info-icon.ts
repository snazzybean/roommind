import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

@customElement("rs-info-icon")
export class RsInfoIcon extends LitElement {
  @property({ type: String }) public text = "";
  @property({ type: String }) public icon = "mdi:information-outline";

  @state() private _open = false;
  @state() private _style = "visibility: hidden;";

  private _onDocPointer = (e: Event) => {
    const path = e.composedPath();
    if (!path.includes(this)) {
      this._close();
    }
  };

  private _onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      this._close();
    }
  };

  private _onScroll = () => this._close();

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._removeListeners();
  }

  static styles = css`
    :host {
      display: inline-flex;
      position: relative;
      vertical-align: middle;
      line-height: 0;
    }

    button {
      background: none;
      border: none;
      padding: 2px;
      margin: 0;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--secondary-text-color);
      opacity: 0.65;
      transition:
        opacity 0.15s,
        color 0.15s,
        background 0.15s;
      border-radius: 50%;
      line-height: 0;
    }

    button:hover,
    button:focus-visible {
      opacity: 1;
      color: var(--primary-color);
      background: rgba(3, 169, 244, 0.1);
      outline: none;
    }

    button.open {
      opacity: 1;
      color: var(--primary-color);
      background: rgba(3, 169, 244, 0.12);
    }

    ha-icon {
      --mdc-icon-size: 16px;
    }

    .tooltip {
      position: fixed;
      z-index: 1100;
      max-width: 280px;
      min-width: 180px;
      width: max-content;
      padding: 10px 12px;
      background: var(--card-background-color, #1f1f1f);
      border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.12));
      border-radius: 8px;
      font-size: 12px;
      font-weight: 400;
      line-height: 1.5;
      letter-spacing: normal;
      text-transform: none;
      color: var(--primary-text-color);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      white-space: normal;
      pointer-events: auto;
      animation: tooltip-fade 0.15s ease-out;
    }

    @keyframes tooltip-fade {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }
  `;

  render() {
    return html`
      <button
        type="button"
        class=${this._open ? "open" : ""}
        @click=${this._toggle}
        aria-label="Info"
        aria-expanded=${this._open ? "true" : "false"}
      >
        <ha-icon .icon=${this.icon}></ha-icon>
      </button>
      ${
        this._open
          ? html`<div
              class="tooltip"
              role="tooltip"
              style=${this._style}
              @click=${(e: Event) => e.stopPropagation()}
            >
              ${this.text ? this.text : nothing}<slot></slot>
            </div>`
          : nothing
      }
    `;
  }

  private _toggle(e: MouseEvent) {
    e.stopPropagation();
    if (this._open) {
      this._close();
    } else {
      this._openTooltip();
    }
  }

  private _openTooltip() {
    this._open = true;
    this._style = "visibility: hidden;";
    requestAnimationFrame(() => {
      this._positionTooltip();
    });
    setTimeout(() => {
      document.addEventListener("pointerdown", this._onDocPointer, true);
      document.addEventListener("keydown", this._onKey, true);
      document.addEventListener("scroll", this._onScroll, true);
      window.addEventListener("resize", this._onScroll, true);
    }, 0);
  }

  private _positionTooltip() {
    const tooltip = this.renderRoot.querySelector(".tooltip") as HTMLElement | null;
    const btn = this.renderRoot.querySelector("button") as HTMLElement | null;
    if (!tooltip || !btn) return;

    const btnRect = btn.getBoundingClientRect();
    const tipRect = tooltip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 8;

    const spaceBelow = vh - btnRect.bottom;
    const spaceAbove = btnRect.top;

    let top: number;
    if (spaceBelow >= tipRect.height + margin) {
      top = btnRect.bottom + 6;
    } else if (spaceAbove >= tipRect.height + margin) {
      top = btnRect.top - tipRect.height - 6;
    } else {
      top = Math.max(margin, (vh - tipRect.height) / 2);
    }

    let left = btnRect.left + btnRect.width / 2 - tipRect.width / 2;
    left = Math.max(margin, Math.min(left, vw - tipRect.width - margin));

    this._style = `top: ${top}px; left: ${left}px;`;
  }

  private _close() {
    if (!this._open) return;
    this._open = false;
    this._style = "visibility: hidden;";
    this._removeListeners();
  }

  private _removeListeners() {
    document.removeEventListener("pointerdown", this._onDocPointer, true);
    document.removeEventListener("keydown", this._onKey, true);
    document.removeEventListener("scroll", this._onScroll, true);
    window.removeEventListener("resize", this._onScroll, true);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-info-icon": RsInfoIcon;
  }
}

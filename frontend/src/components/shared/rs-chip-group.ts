import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";

export interface ChipItem {
  id: string;
  label: string;
  icon?: string;
  /** Secondary text after the label (e.g. a room's temperature). */
  meta?: string;
  active?: boolean;
}

/**
 * Single choice as a row of chips (radio group): arrow keys move the focus, Space/Enter or a
 * click picks. Fires `chip-clicked` with the chip id. `scrollable` keeps the chips on one line
 * and scrolls them sideways, the active chip is brought into view.
 */
@customElement("rs-chip-group")
export class RsChipGroup extends LitElement {
  @property({ type: Array }) public chips: ChipItem[] = [];
  /** Accessible name of the group. */
  @property({ type: String }) public label = "";
  @property({ type: Boolean, reflect: true }) public scrollable = false;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: var(--rs-space-2);
      }

      :host([scrollable]) .chips {
        flex-wrap: nowrap;
        overflow-x: auto;
        overscroll-behavior-x: contain;
        scrollbar-width: thin;
        /* room for the focus ring, which overflow would clip */
        padding: 3px;
        margin: -3px;
      }

      @media (pointer: coarse) {
        :host([scrollable]) .chips {
          scrollbar-width: none;
        }
      }

      .chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        flex: none;
        max-width: 260px;
        height: 32px;
        box-sizing: border-box;
        padding: 0 12px;
        border: 1px solid var(--rs-border);
        border-radius: 16px;
        background: transparent;
        color: var(--primary-text-color);
        font: inherit;
        font-size: 13px;
        white-space: nowrap;
        cursor: pointer;
        touch-action: manipulation;
        transition:
          background-color 0.15s ease,
          border-color 0.15s ease;
      }

      :host([scrollable]) .chip {
        height: 36px;
        border-radius: 18px;
        padding: 0 12px 0 10px;
      }

      @media (pointer: coarse) {
        :host([scrollable]) .chip {
          height: var(--rs-touch);
          border-radius: 22px;
        }
      }

      .chip:hover {
        border-color: var(--rs-border-strong);
        background: var(--rs-fill);
      }

      .chip:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      .chip[aria-checked="true"] {
        border-color: var(--primary-color);
        color: var(--primary-color);
        background: var(--rs-fill-primary);
      }

      .chip ha-icon {
        --mdc-icon-size: 16px;
        flex: none;
      }

      :host([scrollable]) .chip ha-icon {
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
      }

      :host([scrollable]) .chip[aria-checked="true"] ha-icon {
        color: var(--primary-color);
      }

      .name {
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .meta {
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .chip[aria-checked="true"] .meta {
        color: inherit;
        opacity: 0.8;
      }

      @media (prefers-reduced-motion: reduce) {
        .chip {
          transition: none;
        }
      }
    `,
  ];

  render() {
    const focusId = this.chips.find((c) => c.active)?.id ?? this.chips[0]?.id;
    return html`
      <div class="chips" role="radiogroup" aria-label=${this.label} @keydown=${this._onKey}>
        ${this.chips.map(
          (chip) => html`
            <button
              type="button"
              role="radio"
              class="chip"
              data-id=${chip.id}
              aria-checked=${chip.active ? "true" : "false"}
              tabindex=${chip.id === focusId ? "0" : "-1"}
              @click=${() => this._onChipClick(chip.id)}
            >
              ${chip.icon ? html`<ha-icon .icon=${chip.icon} aria-hidden="true"></ha-icon>` : nothing}
              <span class="name">${chip.label}</span>
              ${chip.meta ? html`<span class="meta">${chip.meta}</span>` : nothing}
            </button>
          `,
        )}
      </div>
    `;
  }

  protected updated(changed: Map<string, unknown>) {
    if (this.scrollable && changed.has("chips")) this._revealActive();
  }

  /** Scrolls the row (never the page) so the active chip is visible. */
  private _revealActive() {
    const row = this.renderRoot.querySelector<HTMLElement>(".chips");
    const chip = this.renderRoot.querySelector<HTMLElement>('.chip[aria-checked="true"]');
    if (!row || !chip) return;
    const left =
      chip.getBoundingClientRect().left - row.getBoundingClientRect().left + row.scrollLeft;
    const right = left + chip.offsetWidth;
    if (left < row.scrollLeft) row.scrollLeft = left - 8;
    else if (right > row.scrollLeft + row.clientWidth) {
      row.scrollLeft = right - row.clientWidth + 8;
    }
  }

  private _onKey(e: KeyboardEvent) {
    const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const buttons = [...this.renderRoot.querySelectorAll<HTMLButtonElement>(".chip")];
    if (!buttons.length) return;
    e.preventDefault();
    const idx = buttons.indexOf(e.composedPath()[0] as HTMLButtonElement);
    const rtl = getComputedStyle(this).direction === "rtl";
    let next: number;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = buttons.length - 1;
    else {
      const forward =
        e.key === "ArrowDown" || (e.key !== "ArrowUp" && (e.key === "ArrowRight") !== rtl);
      next = (idx + (forward ? 1 : -1) + buttons.length) % buttons.length;
    }
    buttons.forEach((b, i) => (b.tabIndex = i === next ? 0 : -1));
    buttons[next].focus();
  }

  private _onChipClick(id: string) {
    this.dispatchEvent(
      new CustomEvent("chip-clicked", {
        detail: id,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-chip-group": RsChipGroup;
  }
}

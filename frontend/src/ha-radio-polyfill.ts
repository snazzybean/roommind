/**
 * Polyfill for `ha-radio`, removed in Home Assistant 2026.6.
 *
 * HA 2026.6 dropped the standalone `ha-radio` element in favour of the
 * Web Awesome based `ha-radio-group` + `ha-radio-option` components
 * (frontend component updates 2026.6). Custom panels that still render
 * `<ha-radio>` end up with an undefined element — the radio control simply
 * disappears, so option lists and settings toggles can no longer be chosen.
 *
 * This self-contained wrapper renders a native `<input type="radio">` and
 * preserves the small subset of the mwc-radio API that RoomMind uses
 * (checked, value, name, disabled). It re-emits a composed `change` event so
 * existing `<ha-radio @change>` listeners keep working. Every RoomMind radio
 * is a controlled control — `checked` is driven from component state and a
 * selection flows back through events + re-render — so no cross-element
 * single-selection coordination is needed.
 *
 * It is registered conditionally in `load-ha-elements.ts`, only when
 * `ha-radio` is missing, so older HA versions keep their native element.
 */
import { LitElement, html, css, type TemplateResult } from "lit";
import { property } from "lit/decorators.js";

export class HaRadioPolyfill extends LitElement {
  @property({ type: Boolean, reflect: true }) public checked = false;
  @property({ type: Boolean, reflect: true }) public disabled = false;
  @property({ type: String }) public name = "";
  @property({ type: String }) public value = "";

  static shadowRootOptions: ShadowRootInit = {
    mode: "open",
    delegatesFocus: true,
  };

  static styles = css`
    :host {
      display: inline-flex;
      align-items: center;
    }
    input {
      width: 18px;
      height: 18px;
      margin: 0;
      accent-color: var(--primary-color, #03a9f4);
      cursor: pointer;
    }
    input:disabled {
      cursor: default;
      opacity: 0.5;
    }
  `;

  protected override render(): TemplateResult {
    return html`
      <input
        type="radio"
        .checked=${this.checked}
        .value=${this.value}
        name=${this.name || undefined}
        ?disabled=${this.disabled}
        @change=${this._onChange}
      />
    `;
  }

  private _onChange(e: Event): void {
    this.checked = (e.target as HTMLInputElement).checked;
    // Native `change` does not cross the shadow boundary, so re-emit one from
    // the host. Listeners on `<ha-radio @change>` (e.g. rs-radio-group) then
    // fire with `target.checked` / `target.value` reading from this element.
    this.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

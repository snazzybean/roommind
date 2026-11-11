/**
 * Polyfill for `ha-textfield`, removed in Home Assistant 2026.5.
 *
 * HA 2026.5 dropped `ha-textfield` in favour of `ha-input`
 * (home-assistant/frontend#30349). Custom panels that still render
 * `<ha-textfield>` end up with empty 0-height elements — labels and hints
 * show, the input itself is invisible.
 *
 * This wrapper preserves the small subset of the mwc-textfield API that
 * RoomMind uses (value, label, placeholder, type, min/max/step, suffix,
 * disabled, inputMode) and forwards everything to `<ha-input>`. It is registered
 * conditionally in `load-ha-elements.ts`, only when `ha-textfield` is
 * missing AND `ha-input` is available, so older HA versions keep using
 * their native `ha-textfield`.
 */
import { LitElement, html, css, nothing, type TemplateResult } from "lit";
import { property, query } from "lit/decorators.js";

interface HaInputLike extends HTMLElement {
  value: string;
}

export class HaTextfieldPolyfill extends LitElement {
  @property({ type: String }) public value = "";
  @property({ type: String }) public type = "text";
  @property({ type: String }) public label = "";
  @property({ type: String }) public placeholder = "";
  @property({ type: String }) public suffix = "";
  @property({ type: String }) public prefix = "";
  @property({ type: String }) public helper = "";
  @property({ type: Boolean }) public disabled = false;
  @property({ type: Boolean }) public required = false;
  @property({ type: Boolean, reflect: true, attribute: "readonly" }) public readOnly = false;
  @property() public min: number | string = "";
  @property() public max: number | string = "";
  @property() public step: number | "any" | null = null;
  @property({ type: String }) public name = "";
  /** Shadows HTMLElement.inputMode so a change re-renders; ha-input names it `inputmode`. */
  @property({ type: String, attribute: "inputmode" }) public override inputMode = "";

  @query("ha-input") private _haInput?: HaInputLike;

  static shadowRootOptions: ShadowRootInit = {
    mode: "open",
    delegatesFocus: true,
  };

  static styles = css`
    :host {
      display: inline-flex;
      flex-direction: column;
      outline: none;
      width: 100%;
    }
    ha-input {
      --ha-input-padding-bottom: 0;
      width: 100%;
    }
    .prefix,
    .suffix {
      color: var(--secondary-text-color);
    }
  `;

  protected override render(): TemplateResult {
    return html`
      <ha-input
        .type=${this.type}
        .value=${this.value || ""}
        .label=${this.label}
        .placeholder=${this.placeholder}
        .disabled=${this.disabled}
        .required=${this.required}
        .readonly=${this.readOnly}
        .min=${this.min !== "" ? this.min : undefined}
        .max=${this.max !== "" ? this.max : undefined}
        .step=${this.step ?? undefined}
        .name=${this.name || undefined}
        .inputmode=${this.inputMode || undefined}
        .hint=${this.helper}
        .withoutSpinButtons=${this.type === "number"}
        @input=${this._sync}
        @change=${this._sync}
      >
        ${this.prefix ? html`<span class="prefix" slot="start">${this.prefix}</span>` : nothing}
        ${this.suffix ? html`<span class="suffix" slot="end">${this.suffix}</span>` : nothing}
      </ha-input>
    `;
  }

  private _sync(): void {
    this.value = this._haInput?.value ?? "";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ha-textfield": HaTextfieldPolyfill;
  }
}

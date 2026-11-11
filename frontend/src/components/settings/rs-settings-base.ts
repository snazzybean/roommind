/**
 * rs-settings-base – Shared base class for settings components.
 * Provides the common _fire() method and shared CSS classes. Toggles are `rs-list-row switch`,
 * small fixed choices `rs-segmented`; rows reach the card edge via `--rs-settings-inline`.
 */
import { LitElement, css } from "lit";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-row";

export class RsSettingsBase extends LitElement {
  protected _fire(key: string, value: unknown): void {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static settingsBaseStyles = [
    tokens,
    css`
      :host {
        display: block;
        /* layout follows the panel's own width, not the viewport (list beside it on wide screens) */
        container-type: inline-size;
      }

      /* Round HA's MDC-based inputs to match the rest of the design */
      ha-textfield,
      ha-select,
      ha-entity-picker,
      ha-combo-box {
        --mdc-shape-small: 8px;
        --mdc-shape-medium: 8px;
        --md-filled-text-field-container-shape: 8px;
        --md-outlined-text-field-container-shape: 8px;
        display: block;
        border-radius: 8px;
        overflow: hidden;
        isolation: isolate;
        clip-path: inset(0 round 8px);
      }

      ha-entity-picker {
        clip-path: inset(0 round 8px 8px 4px 4px);
      }

      .settings-section {
        padding: var(--rs-space-4) 0;
        border-top: 1px solid var(--divider-color);
      }
      .settings-section:first-child,
      .settings-section.first {
        border-top: none;
        padding-top: 0;
      }

      /* rows run to the card edge like in Home Assistant's settings, text stays aligned */
      rs-list-row {
        margin-inline: calc(-1 * var(--rs-settings-inline, 0px));
        --rs-list-row-padding: var(--rs-settings-inline, 16px);
      }

      .section-title {
        margin: 0 0 var(--rs-space-2);
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .field-label {
        display: block;
        margin-bottom: var(--rs-space-2);
        font-size: var(--rs-font-md);
        color: var(--primary-text-color);
      }

      .note {
        margin: 0;
        font-size: 13px;
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .stack {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-3);
      }

      .threshold-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--rs-space-4);
      }
      .threshold-field {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .threshold-field ha-textfield {
        width: 100%;
      }
      .field-hint {
        display: block;
        margin-top: var(--rs-space-1);
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
        line-height: 1.4;
      }

      @container (max-width: 520px) {
        .threshold-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];
}

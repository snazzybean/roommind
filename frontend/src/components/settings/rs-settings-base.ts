/**
 * rs-settings-base – Shared base class for settings components.
 * Provides the common _fire() method and shared CSS classes.
 */
import { LitElement, css } from "lit";

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

  static settingsBaseStyles = css`
    :host {
      display: block;
    }

    .settings-section {
      padding: 16px 0;
      border-top: 1px solid var(--divider-color);
    }
    .settings-section:first-child,
    .settings-section.first {
      border-top: none;
      padding-top: 0;
    }

    .toggle-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }
    .toggle-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }
    .toggle-label {
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .toggle-hint {
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.4;
    }

    .threshold-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .threshold-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .threshold-field ha-textfield {
      width: 100%;
    }
    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    @media (max-width: 600px) {
      .threshold-grid {
        grid-template-columns: 1fr;
      }
    }
  `;
}

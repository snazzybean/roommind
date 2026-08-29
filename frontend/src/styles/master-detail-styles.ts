import { css } from "lit";

/**
 * Shared styles for the master-detail edit pattern used by rs-device-section,
 * rs-covers-section, etc. Provides classes for:
 *   - .master / .master-list — left list container
 *   - .master-row + states (focused, in-room) — clickable list row
 *   - .master-info / .master-name-row / .master-name / .master-meta — row content
 *   - .type-pill / .meta-pill — small status pills
 *   - .detail-panel + .empty-detail — right detail container
 *   - .detail-head / .detail-title / .detail-entity-id — detail header
 *   - .detail-field / .detail-hint / .detail-toggle-row — detail form pieces
 *   - .block / .block-divider — full-width sections under master-detail
 */
export const masterDetailStyles = css`
  .master {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }

  .master-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .master-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 10px;
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s;
    border: 1px solid transparent;
    min-width: 0;
  }

  .master-row:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .master-row.focused {
    background: rgba(3, 169, 244, 0.08);
    border-color: rgba(3, 169, 244, 0.5);
  }

  .master-row ha-checkbox {
    flex-shrink: 0;
    margin-left: -8px;
  }

  .master-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .master-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .master-name {
    font-size: 14px;
    font-weight: 450;
    color: var(--primary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .master-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .type-pill,
  .meta-pill {
    display: inline-block;
    font-size: 10px;
    font-weight: 500;
    padding: 1px 8px;
    border-radius: 8px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    background: rgba(255, 255, 255, 0.05);
  }

  .type-pill {
    color: var(--primary-color);
    background: rgba(3, 169, 244, 0.12);
  }

  .external-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 500;
    color: var(--warning-color, #ff9800);
    background: rgba(255, 152, 0, 0.1);
    padding: 2px 8px;
    border-radius: 10px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    flex-shrink: 0;
  }

  .detail-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px 16px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.08));
    border-radius: 12px;
    min-width: 0;
    min-height: 200px;
  }

  .empty-detail {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    flex: 1;
    min-height: 180px;
    color: var(--secondary-text-color);
    font-size: 13px;
    font-style: italic;
    opacity: 0.7;
    text-align: center;
  }

  .empty-detail ha-icon {
    --mdc-icon-size: 28px;
    opacity: 0.6;
  }

  .detail-head {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--divider-color, rgba(255, 255, 255, 0.06));
  }

  .detail-title {
    font-size: 15px;
    font-weight: 500;
    color: var(--primary-text-color);
  }

  .detail-entity-id {
    font-family: var(--code-font-family, monospace);
    font-size: 11px;
    color: var(--secondary-text-color);
    opacity: 0.7;
  }

  .detail-field {
    display: flex;
    flex-direction: column;
  }

  .detail-field ha-select,
  .detail-field ha-textfield {
    width: 100%;
  }

  .detail-field.with-info {
    flex-direction: row;
    align-items: center;
    gap: 6px;
  }

  .detail-field.with-info ha-select,
  .detail-field.with-info ha-textfield {
    flex: 1;
    min-width: 0;
  }

  .detail-field.with-info rs-info-icon {
    flex-shrink: 0;
  }

  .detail-hint {
    font-size: 12px;
    color: var(--secondary-text-color);
    line-height: 1.5;
  }

  .detail-toggle-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 0;
  }

  .detail-toggle-row ha-checkbox {
    margin-top: -8px;
    margin-left: -8px;
  }

  .detail-toggle-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    color: var(--primary-text-color);
  }

  .detail-toggle-label ha-icon {
    --mdc-icon-size: 16px;
    color: var(--secondary-text-color);
  }

  .inline-hint {
    margin-top: 2px;
  }

  .block {
    margin-top: 4px;
  }

  .block-divider {
    height: 1px;
    background: var(--divider-color, rgba(255, 255, 255, 0.08));
    margin: 16px 0 8px;
  }

  .block-title {
    font-size: 12px;
    font-weight: 500;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-bottom: 8px;
  }

  .empty-list {
    color: var(--secondary-text-color);
    font-size: 13px;
    font-style: italic;
    padding: 12px 14px;
  }

  ha-entity-picker {
    width: 100%;
  }

  .picker-wrap {
    margin-top: 8px;
  }
`;

import { css } from "lit";

/**
 * Shared CSS for info-icon toggle pattern.
 * Used by rs-analytics (model stats) and rs-climate-mode-selector.
 */
export const infoIconStyles = css`
  .info-icon {
    --mdc-icon-size: 16px;
    color: var(--secondary-text-color);
    opacity: 0.3;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s, color 0.15s;
  }

  .info-icon:hover {
    opacity: 0.7;
  }

  .info-icon.info-active {
    opacity: 1;
    color: var(--primary-color);
  }

  .info-panel {
    padding: 12px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
    font-size: 13px;
    line-height: 1.6;
    color: var(--secondary-text-color);
  }

  .info-panel strong {
    display: block;
    margin-bottom: 4px;
    color: var(--primary-text-color);
    font-size: 13px;
  }

  .info-panel .yaml-block {
    background: var(--primary-background-color, #f5f5f5);
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 6px;
    padding: 10px 14px;
    margin: 8px 0;
    font-family: var(--code-font-family, monospace);
    font-size: 12px;
    line-height: 1.6;
    white-space: pre;
    overflow-x: auto;
    color: var(--primary-text-color);
  }
  .info-panel .yaml-key { color: #0550ae; }
  .info-panel .yaml-value { color: #0a3069; }
`;

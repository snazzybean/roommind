import { css } from "lit";

/**
 * Design tokens of the panel (docs: ui-design-system). Every new component lists this
 * first in `static styles`; values derive from Home Assistant's theme variables only.
 */
export const tokens = css`
  :host {
    --rs-radius: var(--ha-card-border-radius, 12px);
    --rs-radius-sm: 8px;
    --rs-fill: color-mix(in srgb, var(--secondary-text-color) 8%, transparent);
    --rs-fill-strong: color-mix(in srgb, var(--secondary-text-color) 14%, transparent);
    --rs-fill-primary: color-mix(in srgb, var(--primary-color) 10%, transparent);
    --rs-heat: var(--state-climate-heat-color, var(--warning-color));
    --rs-cool: var(--state-climate-cool-color, var(--info-color));
    --rs-ok: var(--success-color);
    --rs-warn: var(--warning-color);
    --rs-err: var(--error-color);
    --rs-border: var(--divider-color);
    --rs-border-strong: color-mix(in srgb, var(--primary-text-color) 22%, transparent);
    --rs-surface: var(--card-background-color, var(--ha-card-background));
    --rs-shadow-pop: 0 1px 3px rgb(0 0 0 / 12%), 0 8px 24px rgb(0 0 0 / 22%);
    --rs-shadow-lift: 0 2px 6px rgb(0 0 0 / 14%), 0 14px 36px rgb(0 0 0 / 25%);
    --rs-space-1: 4px;
    --rs-space-2: 8px;
    --rs-space-3: 12px;
    --rs-space-4: 16px;
    --rs-space-5: 20px;
    --rs-space-6: 24px;
    --rs-font-xs: 11px;
    --rs-font-sm: 12px;
    --rs-font-md: 14px;
    --rs-font-lg: 16px;
    --rs-font-xl: 20px;
    --rs-font-display: 48px;
    --rs-touch: 44px;
  }
`;

/** Visually hidden but read by screen readers (live regions, extra labels). */
export const srOnly = css`
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
`;

/** Error line where the user acts (inside the dialog or settings page), with role="alert". */
export const alertStyles = css`
  .rs-alert {
    margin: 0 0 var(--rs-space-4);
    padding: var(--rs-space-2) var(--rs-space-3);
    border-radius: var(--rs-radius-sm);
    background: color-mix(in srgb, var(--rs-err) 12%, transparent);
    color: var(--rs-err);
    font-size: var(--rs-font-md);
    line-height: 1.4;
  }
`;

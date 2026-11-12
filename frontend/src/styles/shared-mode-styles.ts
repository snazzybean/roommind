import { css } from "lit";

/**
 * Shared CSS for mode-pill and mode-dot styles used by
 * the dashboard card. Needs `tokens` in the host's styles (--rs-heat/--rs-cool).
 */
export const modeStyles = css`
  .mode-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 14px;
    border-radius: 16px;
  }

  .mode-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .mode-heating {
    color: var(--rs-heat-text);
    background: color-mix(in srgb, var(--rs-heat) 12%, transparent);
  }
  .mode-heating .mode-dot {
    background: var(--rs-heat);
  }

  .mode-cooling {
    color: var(--rs-cool-text);
    background: color-mix(in srgb, var(--rs-cool) 12%, transparent);
  }
  .mode-cooling .mode-dot {
    background: var(--rs-cool);
  }

  .mode-idle {
    color: var(--secondary-text-color, #757575);
    background: color-mix(in srgb, var(--secondary-text-color) 5%, transparent);
  }
  .mode-idle .mode-dot {
    background: var(--disabled-text-color, #bdbdbd);
  }

  .mode-other {
    color: var(--secondary-text-color);
    background: color-mix(in srgb, var(--secondary-text-color) 5%, transparent);
  }
  .mode-other .mode-dot {
    background: var(--secondary-text-color);
  }
`;

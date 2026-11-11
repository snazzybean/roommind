import { css } from "lit";

/**
 * Look of every floating layer (tooltip, menu): one surface so they read as one system.
 * Placement comes from `utils/popover.ts`; `.floating` resets the UA popover styles.
 * `.floating-surface` is the same look for a popup its parent positions itself.
 */
export const floatingStyles = css`
  .floating,
  .floating-surface {
    box-sizing: border-box;
    background: var(--card-background-color, var(--primary-background-color));
    border: 1px solid var(--divider-color);
    border-radius: 8px;
    color: var(--primary-text-color);
    box-shadow:
      0 1px 3px rgb(0 0 0 / 12%),
      0 8px 24px rgb(0 0 0 / 28%);
    animation: floating-fade 0.12s ease-out;
  }

  .floating {
    position: fixed;
    inset: auto;
    margin: 0;
    z-index: 1100;
  }

  .floating:popover-open {
    /* the UA popover style centres and pads the element; placement is ours */
    inset: auto;
    padding: 0;
    overflow: visible;
  }

  .tooltip-surface {
    width: max-content;
    max-width: min(280px, calc(100vw - 16px));
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.5;
    letter-spacing: normal;
    text-transform: none;
    text-align: left;
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .tooltip-surface:popover-open {
    padding: 8px 12px;
  }

  @keyframes floating-fade {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .floating,
    .floating-surface {
      animation: none;
    }
  }
`;

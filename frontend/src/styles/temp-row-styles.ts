import { css } from "lit";

/**
 * A target temperature row: icon and label on the left, rs-stepper on the right. Shared by the
 * temperatures dialog and the schedule block form so both look the same.
 */
export const tempRowStyles = css`
  .temp-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--rs-space-3);
    margin-top: var(--rs-space-3);
    font-size: var(--rs-font-md);
  }

  .temp-row > span {
    display: inline-flex;
    align-items: center;
    gap: var(--rs-space-2);
    flex: 1 1 auto;
    min-width: 0;
    line-height: 1.3;
  }

  .temp-row rs-stepper {
    flex: none;
  }

  .temp-row ha-icon {
    --mdc-icon-size: 18px;
    flex: none;
  }

  .temp-row.heat ha-icon {
    color: var(--rs-heat);
  }

  .temp-row.cool ha-icon {
    color: var(--rs-cool);
  }
`;

import { css } from "lit";

/**
 * Settings forms inside the room dialogs: groups under a short title (with an optional
 * info icon), plain notes, and rows that reach the edge of their container. The container
 * sets `--rs-form-inline` to its own inline padding so rows line up with the text.
 */
export const formStyles = css`
  .group {
    display: flex;
    flex-direction: column;
    gap: var(--rs-space-3);
    min-width: 0;
  }

  .group + .group {
    margin-top: var(--rs-space-6);
  }

  .group-title {
    display: flex;
    align-items: center;
    gap: var(--rs-space-1);
    margin: 0;
    /* a group heads its fields, so it is never smaller than their labels (rs-field, 14 px) */
    font-size: var(--rs-font-lg);
    font-weight: 500;
    color: var(--primary-text-color);
  }

  .note {
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
    color: var(--secondary-text-color);
  }

  .note.warn {
    display: flex;
    gap: var(--rs-space-2);
    align-items: flex-start;
    color: var(--primary-text-color);
  }

  .note.warn ha-icon {
    --mdc-icon-size: 18px;
    color: var(--rs-warn);
    flex: none;
  }

  .group rs-list-row {
    margin-inline: calc(-1 * var(--rs-form-inline, 16px));
    --rs-list-row-padding: var(--rs-form-inline, 16px);
  }

  ha-entity-picker,
  ha-select,
  ha-textfield {
    width: 100%;
  }
`;

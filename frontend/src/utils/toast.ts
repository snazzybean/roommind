import { localize } from "./localize";

const TOAST_MS = 8000;

/** HA's own toast (`hass-notification`), optionally with an Undo action. */
export function showToast(
  from: HTMLElement,
  message: string,
  language: string,
  undo?: () => void,
): void {
  from.dispatchEvent(
    new CustomEvent("hass-notification", {
      detail: {
        message,
        duration: TOAST_MS,
        ...(undo ? { action: { text: localize("common.undo", language), action: undo } } : {}),
      },
      bubbles: true,
      composed: true,
    }),
  );
}

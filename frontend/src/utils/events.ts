/**
 * Read the selected value from an ha-select @selected event.
 * HA 2026.3+ fires detail.value; older HA sets e.target.value synchronously.
 */
export function getSelectValue(e: Event): string {
  const detail = (e as CustomEvent).detail;
  return detail?.value ?? (e.target as HTMLElement & { value?: string }).value ?? "";
}

export function fireSaveStatus(element: HTMLElement, status: "saving" | "saved" | "error") {
  element.dispatchEvent(new CustomEvent("save-status", {
    detail: { status },
    bubbles: true,
    composed: true,
  }));
}

export function openEntityInfo(element: HTMLElement, entityId: string) {
  element.dispatchEvent(new CustomEvent("hass-more-info", {
    bubbles: true,
    composed: true,
    detail: { entityId },
  }));
}

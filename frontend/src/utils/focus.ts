/** Focus helpers that see through open shadow roots and slots (HA's controls are web components). */

/** The element that really has the focus, inside shadow roots. */
export function deepActiveElement(): HTMLElement | null {
  let el: Element | null = document.activeElement;
  while (el?.shadowRoot?.activeElement) el = el.shadowRoot.activeElement;
  return el instanceof HTMLElement ? el : null;
}

function isTabbable(el: HTMLElement): boolean {
  if (el.tabIndex < 0 || (el as HTMLElement & { disabled?: boolean }).disabled) return false;
  return typeof el.checkVisibility === "function"
    ? el.checkVisibility({ visibilityProperty: true })
    : el.getClientRects().length > 0;
}

function collect(el: Element, out: HTMLElement[]): void {
  if (el instanceof HTMLElement && (el.hidden || el.inert)) return;
  if (el instanceof HTMLElement && isTabbable(el)) out.push(el);
  let children: Element[];
  if (el instanceof HTMLSlotElement) {
    const assigned = el.assignedElements({ flatten: true });
    children = assigned.length ? assigned : [...el.children];
  } else {
    children = [...(el.shadowRoot ?? el).children];
  }
  for (const child of children) collect(child, out);
}

/** Tab stops inside `root` in document order (positive tabindex is not used in the panel). */
export function tabbables(root: Element): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const child of [...(root.shadowRoot ?? root).children]) collect(child, out);
  return out;
}

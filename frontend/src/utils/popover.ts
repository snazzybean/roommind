/**
 * Placement of floating layers (tooltips, menus) next to an anchor, kept inside the viewport.
 * Pure geometry plus the top-layer helpers shared by rs-tooltip and rs-menu.
 */

export interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const GAP = 6;
const MARGIN = 8;

/**
 * Below the anchor if it fits, else above, else vertically centred; horizontally centred on
 * the anchor (or aligned to its end with `align: "end"`), clamped to the viewport.
 */
export function placeNear(
  anchor: DOMRect | Box,
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  align: "center" | "end" = "center",
): { top: number; left: number } {
  const anchorBottom = anchor.top + anchor.height;
  let top: number;
  if (viewport.height - anchorBottom >= pop.height + GAP + MARGIN) {
    top = anchorBottom + GAP;
  } else if (anchor.top >= pop.height + GAP + MARGIN) {
    top = anchor.top - pop.height - GAP;
  } else {
    top = Math.max(MARGIN, (viewport.height - pop.height) / 2);
  }
  let left =
    align === "end"
      ? anchor.left + anchor.width - pop.width
      : anchor.left + anchor.width / 2 - pop.width / 2;
  left = Math.max(MARGIN, Math.min(left, viewport.width - pop.width - MARGIN));
  return { top: Math.round(top), left: Math.round(left) };
}

const popoverSupported =
  typeof HTMLElement !== "undefined" &&
  Object.prototype.hasOwnProperty.call(HTMLElement.prototype, "popover");

/**
 * Lift an element into the top layer so `overflow: hidden` and transformed ancestors can't
 * clip or offset it; browsers without the Popover API keep plain `position: fixed`.
 */
export function showInTopLayer(el: HTMLElement): void {
  if (!popoverSupported) return;
  if (!el.hasAttribute("popover")) el.setAttribute("popover", "manual");
  try {
    if (!el.matches(":popover-open")) el.showPopover();
  } catch {
    // Element not connected yet or already shown; fixed positioning still applies.
  }
}

export function hideFromTopLayer(el: HTMLElement | null | undefined): void {
  if (!el || !popoverSupported) return;
  try {
    if (el.matches(":popover-open")) el.hidePopover();
  } catch {
    // Already hidden.
  }
}

export function positionNear(
  anchorEl: Element,
  popEl: HTMLElement,
  align: "center" | "end" = "center",
): void {
  const pos = placeNear(
    anchorEl.getBoundingClientRect(),
    popEl.getBoundingClientRect(),
    { width: window.innerWidth, height: window.innerHeight },
    align,
  );
  popEl.style.top = `${pos.top}px`;
  popEl.style.left = `${pos.left}px`;
  popEl.style.visibility = "visible";
}

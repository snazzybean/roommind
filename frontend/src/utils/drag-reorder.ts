import type { ReactiveController, ReactiveControllerHost } from "lit";

/**
 * Pointer drag & drop for reordering items in a grid, as a Lit controller.
 *
 * DOM contract inside the host's render root:
 * - every item: `data-drag-id="<id>"` and `data-drag-group="<group>"` (reorder within a group)
 * - grab areas inside an item: `data-drag-handle`; `data-drag-handle="mouse"` only for a mouse
 *   (a whole card can't be the grab area on touch, the page would no longer scroll). Grab
 *   areas for touch need `touch-action: none`.
 * - one element with `data-drag-key` per item takes the arrow keys (keyboard fallback).
 * - while `dragging` is set the host renders the dragged item once more inside an element
 *   with `data-drag-ghost` (fixed, pointer-events none); the controller moves it.
 *
 * The host renders its items through `order()` so the preview order shows while dragging,
 * and marks `isPlaceholder(id)`. Nothing here moves DOM nodes Lit owns.
 */
export interface DragReorderOptions {
  /** Current ids of a group, in display order. */
  groupIds: (group: string) => string[];
  /** A drag or key move ended with a new order of the group. */
  onReorder: (group: string, ids: string[], movedId: string) => void;
  /** Text for the live region after a move, e.g. "Kitchen, position 3 of 5". */
  announce: (movedId: string, position: number, total: number) => string;
}

interface Pending {
  id: string;
  group: string;
  pointerId: number;
  startX: number;
  startY: number;
  item: HTMLElement;
}

interface Active {
  id: string;
  group: string;
  original: string[];
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
}

const START_DISTANCE_PX = 5;
const EDGE_PX = 80;
const MAX_SCROLL_STEP_PX = 18;
const FLIP_MS = 160;
const INTERACTIVE = "button, a, input, select, textarea, rs-menu, rs-icon-button, [data-no-drag]";

export class DragReorderController implements ReactiveController {
  /** Item being dragged (for the ghost and the placeholder), null otherwise. */
  public dragging: { id: string; group: string; width: number; height: number } | null = null;
  /** Last move, for an `aria-live` region. */
  public announcement = "";

  private _host: ReactiveControllerHost & HTMLElement;
  private _opts: DragReorderOptions;
  private _pending: Pending | null = null;
  private _active: Active | null = null;
  private _preview: string[] | null = null;
  private _x = 0;
  private _y = 0;
  private _raf = 0;
  private _scroller: Element | null = null;
  private _rects = new Map<string, DOMRect>();
  private _rectsScroll = 0;
  private _flipBefore: Map<string, DOMRect> | null = null;
  private _refocusId: string | null = null;

  constructor(host: ReactiveControllerHost & HTMLElement, opts: DragReorderOptions) {
    this._host = host;
    this._opts = opts;
    host.addController(this);
  }

  hostConnected(): void {
    this._host.addEventListener("pointerdown", this._onPointerDown);
    this._host.addEventListener("keydown", this._onKeyDown);
  }

  hostDisconnected(): void {
    this._host.removeEventListener("pointerdown", this._onPointerDown);
    this._host.removeEventListener("keydown", this._onKeyDown);
    this._endListeners();
    this._pending = null;
    this._active = null;
    this.dragging = null;
    this._preview = null;
  }

  /** `ids` in the preview order while that group is dragged, else unchanged. */
  order(group: string, ids: string[]): string[] {
    if (!this._active || this._active.group !== group || !this._preview) return ids;
    // Items may have appeared or gone since the drag started (poll): keep only known ones.
    const known = new Set(ids);
    const preview = this._preview.filter((id) => known.has(id));
    return [...preview, ...ids.filter((id) => !preview.includes(id))];
  }

  isPlaceholder(id: string): boolean {
    return this.dragging?.id === id;
  }

  /** Move an item by `delta` places (menu, keyboard) with the same animation and announcement. */
  moveBy(group: string, id: string, delta: number): boolean {
    const ids = this._opts.groupIds(group);
    const idx = ids.indexOf(id);
    const target = idx + delta;
    if (idx === -1 || target < 0 || target >= ids.length) return false;
    const next = [...ids];
    next.splice(idx, 1);
    next.splice(target, 0, id);
    this.animateNextUpdate();
    this._opts.onReorder(group, next, id);
    this._announce(id, target + 1, next.length);
    return true;
  }

  /** Call before the host changes the order itself; the next render animates to it. */
  animateNextUpdate(): void {
    this._flipBefore = this._measure();
  }

  hostUpdated(): void {
    const ghost = this._root().querySelector<HTMLElement>("[data-drag-ghost]");
    if (ghost && this._active) this._placeGhost(ghost);
    // Hit-test rects first: a running FLIP animation would shift them.
    if (this._active) this._cacheRects();
    if (this._flipBefore) {
      const before = this._flipBefore;
      this._flipBefore = null;
      this._animateFrom(before);
    }
    if (this._refocusId) {
      const id = this._refocusId;
      this._refocusId = null;
      this._item(id)?.querySelector<HTMLElement>("[data-drag-key]")?.focus();
      if (this._item(id)?.matches("[data-drag-key]")) this._item(id)?.focus();
    }
  }

  // ---------- pointer ----------

  private _onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0 || !e.isPrimary || this._active) return;
    const path = e.composedPath() as Element[];
    let handle: HTMLElement | null = null;
    for (const el of path) {
      if (!(el instanceof HTMLElement)) continue;
      if (el.hasAttribute("data-drag-handle")) {
        handle = el;
        break;
      }
      if (el.matches(INTERACTIVE)) return;
    }
    if (!handle) return;
    if (handle.getAttribute("data-drag-handle") === "mouse" && e.pointerType !== "mouse") return;
    const item = handle.closest<HTMLElement>("[data-drag-id]");
    if (!item) return;
    this._pending = {
      id: item.dataset.dragId!,
      group: item.dataset.dragGroup ?? "",
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      item,
    };
    if (e.pointerType === "mouse") e.preventDefault(); // no text selection while dragging
    window.addEventListener("pointermove", this._onPointerMove, true);
    window.addEventListener("pointerup", this._onPointerUp, true);
    window.addEventListener("pointercancel", this._onPointerCancel, true);
    window.addEventListener("keydown", this._onDragKey, true);
  };

  private _onPointerMove = (e: PointerEvent) => {
    const p = this._pending;
    if (!p || e.pointerId !== p.pointerId) return;
    this._x = e.clientX;
    this._y = e.clientY;
    if (!this._active) {
      if (Math.hypot(e.clientX - p.startX, e.clientY - p.startY) < START_DISTANCE_PX) return;
      this._start(p);
    }
    e.preventDefault();
    const ghost = this._root().querySelector<HTMLElement>("[data-drag-ghost]");
    if (ghost) this._placeGhost(ghost);
    this._hitTest();
  };

  private _onPointerUp = (e: PointerEvent) => {
    if (!this._pending || e.pointerId !== this._pending.pointerId) return;
    const active = this._active;
    this._endListeners();
    this._pending = null;
    if (!active) return;
    // The click after a real drag must not open the room or press a button.
    const swallow = (ev: Event) => {
      ev.stopPropagation();
      ev.preventDefault();
    };
    window.addEventListener("click", swallow, { capture: true, once: true });
    setTimeout(() => window.removeEventListener("click", swallow, true), 0);
    this._finish(true);
  };

  private _onPointerCancel = (e: PointerEvent) => {
    if (!this._pending || e.pointerId !== this._pending.pointerId) return;
    this.cancel();
  };

  private _onDragKey = (e: KeyboardEvent) => {
    if (e.key === "Escape" && this._active) {
      e.preventDefault();
      e.stopPropagation();
      this.cancel();
    }
  };

  /** Abort a drag in progress; the order stays as it was. */
  cancel(): void {
    this._endListeners();
    this._pending = null;
    if (this._active) this._finish(false);
  }

  private _start(p: Pending) {
    const rect = p.item.getBoundingClientRect();
    const original = this._opts.groupIds(p.group);
    this._active = {
      id: p.id,
      group: p.group,
      original,
      offsetX: p.startX - rect.left,
      offsetY: p.startY - rect.top,
      width: rect.width,
      height: rect.height,
    };
    this._preview = [...original];
    this.dragging = { id: p.id, group: p.group, width: rect.width, height: rect.height };
    this._scroller = findScrollParent(this._host);
    this._host.requestUpdate();
    this._raf = requestAnimationFrame(this._autoScroll);
  }

  private _finish(commit: boolean) {
    const active = this._active!;
    const preview = this._preview ?? active.original;
    cancelAnimationFrame(this._raf);
    this.animateNextUpdate();
    this._active = null;
    this._preview = null;
    this.dragging = null;
    const changed = preview.join("\n") !== active.original.join("\n");
    if (commit && changed) {
      this._opts.onReorder(active.group, preview, active.id);
      this._announce(active.id, preview.indexOf(active.id) + 1, preview.length);
    }
    this._host.requestUpdate();
  }

  private _hitTest() {
    const a = this._active;
    if (!a || !this._preview) return;
    const dy = this._scrollTop() - this._rectsScroll;
    let over: string | null = null;
    for (const [id, r] of this._rects) {
      const top = r.top - dy;
      if (this._x >= r.left && this._x <= r.right && this._y >= top && this._y <= top + r.height) {
        over = id;
        break;
      }
    }
    if (!over || over === a.id) return;
    const from = this._preview.indexOf(a.id);
    const to = this._preview.indexOf(over);
    if (from === -1 || to === -1) return;
    const next = [...this._preview];
    next.splice(from, 1);
    next.splice(to, 0, a.id);
    this.animateNextUpdate();
    this._preview = next;
    this._host.requestUpdate();
  }

  private _autoScroll = () => {
    if (!this._active) return;
    const view =
      this._scroller && this._scroller !== document.scrollingElement
        ? this._scroller.getBoundingClientRect()
        : { top: 0, bottom: window.innerHeight };
    let step = 0;
    if (this._y < view.top + EDGE_PX) step = -((view.top + EDGE_PX - this._y) / EDGE_PX);
    else if (this._y > view.bottom - EDGE_PX) step = (this._y - (view.bottom - EDGE_PX)) / EDGE_PX;
    if (step) {
      const px = Math.round(Math.max(-1, Math.min(1, step)) * MAX_SCROLL_STEP_PX);
      const target = this._scroller ?? document.scrollingElement;
      if (target) target.scrollTop += px;
      this._hitTest();
    }
    this._raf = requestAnimationFrame(this._autoScroll);
  };

  private _endListeners() {
    window.removeEventListener("pointermove", this._onPointerMove, true);
    window.removeEventListener("pointerup", this._onPointerUp, true);
    window.removeEventListener("pointercancel", this._onPointerCancel, true);
    window.removeEventListener("keydown", this._onDragKey, true);
    cancelAnimationFrame(this._raf);
  }

  // ---------- keyboard ----------

  private _onKeyDown = (e: KeyboardEvent) => {
    if (this._active) return;
    const target = e.composedPath()[0] as HTMLElement | undefined;
    if (!target?.hasAttribute?.("data-drag-key")) return;
    const delta =
      e.key === "ArrowUp" || e.key === "ArrowLeft"
        ? -1
        : e.key === "ArrowDown" || e.key === "ArrowRight"
          ? 1
          : 0;
    if (!delta) return;
    const item = target.closest<HTMLElement>("[data-drag-id]");
    if (!item) return;
    e.preventDefault();
    const id = item.dataset.dragId!;
    if (this.moveBy(item.dataset.dragGroup ?? "", id, delta)) this._refocusId = id;
  };

  // ---------- helpers ----------

  private _root(): ParentNode {
    return (this._host as unknown as { renderRoot?: ParentNode }).renderRoot ?? this._host;
  }

  private _item(id: string): HTMLElement | null {
    return this._root().querySelector<HTMLElement>(`[data-drag-id="${CSS.escape(id)}"]`);
  }

  private _measure(): Map<string, DOMRect> {
    const map = new Map<string, DOMRect>();
    for (const el of this._root().querySelectorAll<HTMLElement>("[data-drag-id]")) {
      if (el.closest("[data-drag-ghost]")) continue;
      map.set(el.dataset.dragId!, el.getBoundingClientRect());
    }
    return map;
  }

  private _cacheRects() {
    const a = this._active;
    this._rects.clear();
    if (!a) return;
    for (const el of this._root().querySelectorAll<HTMLElement>("[data-drag-id]")) {
      if (el.closest("[data-drag-ghost]") || (el.dataset.dragGroup ?? "") !== a.group) continue;
      this._rects.set(el.dataset.dragId!, el.getBoundingClientRect());
    }
    this._rectsScroll = this._scrollTop();
  }

  private _scrollTop(): number {
    return (this._scroller ?? document.scrollingElement)?.scrollTop ?? 0;
  }

  private _placeGhost(ghost: HTMLElement) {
    const a = this._active!;
    ghost.style.width = `${a.width}px`;
    ghost.style.height = `${a.height}px`;
    ghost.style.transform = `translate(${Math.round(this._x - a.offsetX)}px, ${Math.round(
      this._y - a.offsetY,
    )}px)`;
  }

  private _animateFrom(before: Map<string, DOMRect>) {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    for (const el of this._root().querySelectorAll<HTMLElement>("[data-drag-id]")) {
      if (el.closest("[data-drag-ghost]")) continue;
      const id = el.dataset.dragId!;
      if (this.dragging?.id === id) continue;
      const a = before.get(id);
      if (!a) continue;
      const b = el.getBoundingClientRect();
      const dx = a.left - b.left;
      const dy = a.top - b.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], {
        duration: FLIP_MS,
        easing: "ease-out",
      });
    }
  }

  private _announce(id: string, position: number, total: number) {
    this.announcement = this._opts.announce(id, position, total);
    this._host.requestUpdate();
  }
}

/** First scrollable ancestor across shadow roots, else the document's scrolling element. */
export function findScrollParent(start: Element): Element | null {
  let node: Node | null = start;
  while (node) {
    if (node instanceof Element) {
      const style = getComputedStyle(node);
      if (/(auto|scroll|overlay)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
        return node;
      }
    }
    node = node.parentNode ?? (node instanceof ShadowRoot ? node.host : null);
  }
  return document.scrollingElement;
}

/**
 * One `roommind/rooms/list` poll for every RoomMind card on the page, paused while
 * the page is hidden and stopped when no card is shown.
 */
import type { HomeAssistant, RoomConfig } from "../types";

export interface RoomsFeed {
  rooms: Record<string, RoomConfig>;
  climate_control_active: boolean;
}

type Listener = (feed: RoomsFeed | null, error: string) => void;

export const POLL_INTERVAL_MS = 10_000;

const listeners = new Set<Listener>();
let hass: HomeAssistant | null = null;
let timer: ReturnType<typeof setInterval> | undefined;
let inflight: Promise<void> | null = null;
let last: RoomsFeed | null = null;
let lastError = "";

export function setFeedHass(next: HomeAssistant): void {
  const first = !hass;
  hass = next;
  if (first && listeners.size) void refreshRooms();
}

export function subscribeRooms(listener: Listener): () => void {
  listeners.add(listener);
  if (last || lastError) listener(last, lastError);
  if (listeners.size === 1) start();
  return () => {
    listeners.delete(listener);
    if (!listeners.size) stop();
  };
}

/**
 * `fresh` after a change: a request already running may have been answered before the
 * change landed, so queue a new one behind it instead of sharing it.
 */
export function refreshRooms(fresh = false): Promise<void> {
  if (!hass) return Promise.resolve();
  if (inflight) return fresh ? inflight.then(() => refreshRooms(true)) : inflight;
  const conn = hass;
  inflight = conn
    .callWS<RoomsFeed>({ type: "roommind/rooms/list" })
    .then((result) => {
      last = {
        rooms: result.rooms ?? {},
        climate_control_active: result.climate_control_active ?? true,
      };
      lastError = "";
    })
    .catch((err: unknown) => {
      lastError =
        err instanceof Error ? err.message : String((err as { message?: string })?.message ?? err);
    })
    .finally(() => {
      inflight = null;
      for (const l of listeners) l(last, lastError);
    });
  return inflight;
}

function onVisibility(): void {
  if (!document.hidden) void refreshRooms();
}

function start(): void {
  void refreshRooms();
  timer = setInterval(() => {
    if (!document.hidden) void refreshRooms();
  }, POLL_INTERVAL_MS);
  document.addEventListener("visibilitychange", onVisibility);
}

function stop(): void {
  if (timer) clearInterval(timer);
  timer = undefined;
  document.removeEventListener("visibilitychange", onVisibility);
}

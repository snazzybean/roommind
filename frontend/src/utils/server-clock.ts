/**
 * The server's clock, learned from every rooms/list answer. Countdowns compare server
 * timestamps (override end, compressor protection, coil dry) with it, so a device clock that
 * is off does not shift them. Card and panel bundles each keep their own copy.
 */
let offsetMs = 0;

export function noteServerTime(serverS: number | null | undefined): void {
  if (typeof serverS === "number" && Number.isFinite(serverS))
    offsetMs = serverS * 1000 - Date.now();
}

/** Now on the server's clock, in milliseconds. */
export function serverNow(): number {
  return Date.now() + offsetMs;
}

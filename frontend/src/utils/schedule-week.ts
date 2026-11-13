/**
 * Week model of a Home Assistant schedule helper for the schedule editor. Pure functions only:
 * times as minutes of the day (0-1440), one sorted block list per weekday, block `data` kept
 * as it came from Home Assistant so keys RoomMind does not know survive every edit.
 */

/** Same order and names as Home Assistant's schedule config (and `_WEEKDAYS` in the backend). */
export const WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

export type Weekday = (typeof WEEKDAYS)[number];

export const DAY_MINUTES = 1440;
export const SNAP_MINUTES = 15;
/** Shortest block the editor creates or resizes to. */
export const MIN_BLOCK_MINUTES = SNAP_MINUTES;

export type BlockData = Record<string, string | number | boolean>;

export interface ScheduleBlock {
  start: number;
  end: number;
  data?: BlockData;
}

/** Seven sorted day lists, Monday first. */
export type Week = ScheduleBlock[][];

/** One time range as Home Assistant stores it. */
export interface HaTimeRange {
  from: string;
  to: string;
  data?: BlockData;
}

export type HaWeek = Record<Weekday, HaTimeRange[]>;

/** Block data keys that carry a target temperature (backend `_BLOCK_TEMP_FIELDS`). */
export const TEMP_KEYS = ["temperature", "heat_temperature", "cool_temperature"] as const;

export function emptyWeek(): Week {
  return WEEKDAYS.map(() => []);
}

/**
 * "HH:MM", "HH:MM:SS" or "HH:MM:SS.ffffff" to minutes. Home Assistant hands out a day end as
 * "24:00:00" (storage) or as time.max "23:59:59.999999" (get_schedule), both are 1440.
 */
export function parseTime(value: string): number {
  const [h = "0", m = "0", s = "0"] = String(value).split(":");
  const seconds = Number(h) * 3600 + Number(m) * 60 + Number(s);
  if (!Number.isFinite(seconds)) return 0;
  if (seconds >= DAY_MINUTES * 60 - 1) return DAY_MINUTES;
  return Math.max(0, Math.min(DAY_MINUTES, Math.round(seconds / 60)));
}

/** Minutes to "HH:MM:SS"; 1440 becomes "24:00:00", which Home Assistant accepts as day end. */
export function formatTime(minutes: number): string {
  return `${hm(minutes)}:00`;
}

/** Minutes to "HH:MM" (1440 = "24:00"). */
export function hm(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function sortDay(day: ScheduleBlock[]): ScheduleBlock[] {
  return [...day].sort((a, b) => a.start - b.start);
}

/** Home Assistant's day lists to the week model (missing days are empty). */
export function parseWeek(source: Partial<Record<string, unknown>>): Week {
  return WEEKDAYS.map((name) => {
    const raw = source[name];
    if (!Array.isArray(raw)) return [];
    return sortDay(
      raw
        .filter((r): r is HaTimeRange => !!r && typeof r === "object" && "from" in r && "to" in r)
        .map((r) => {
          const block: ScheduleBlock = { start: parseTime(r.from), end: parseTime(r.to) };
          if (r.data && typeof r.data === "object" && Object.keys(r.data).length > 0) {
            block.data = { ...r.data };
          }
          return block;
        }),
    );
  });
}

/** The week model as Home Assistant's day lists: all seven days, sorted, `data` only if set. */
export function serializeWeek(week: Week): HaWeek {
  const out = {} as HaWeek;
  WEEKDAYS.forEach((name, d) => {
    out[name] = sortDay(week[d] ?? []).map((b) => {
      const range: HaTimeRange = { from: formatTime(b.start), to: formatTime(b.end) };
      if (b.data && Object.keys(b.data).length > 0) range.data = { ...b.data };
      return range;
    });
  });
  return out;
}

/** Problems Home Assistant would reject: a block ending before it starts, or two overlapping. */
export function dayIsValid(day: ScheduleBlock[]): boolean {
  const sorted = sortDay(day);
  for (let i = 0; i < sorted.length; i++) {
    const b = sorted[i];
    if (b.start < 0 || b.end > DAY_MINUTES || b.start >= b.end) return false;
    if (i > 0 && sorted[i - 1].end > b.start) return false;
  }
  return true;
}

export function weekIsValid(week: Week): boolean {
  return week.length === 7 && week.every(dayIsValid);
}

export function weeksEqual(a: Week, b: Week): boolean {
  return JSON.stringify(serializeWeek(a)) === JSON.stringify(serializeWeek(b));
}

export function snap(minutes: number, step = SNAP_MINUTES): number {
  return Math.max(0, Math.min(DAY_MINUTES, Math.round(minutes / step) * step));
}

/** Free space around `index` in a sorted day: from the previous block's end to the next start. */
export function neighbourLimits(day: ScheduleBlock[], index: number): { min: number; max: number } {
  return {
    min: index > 0 ? day[index - 1].end : 0,
    max: index < day.length - 1 ? day[index + 1].start : DAY_MINUTES,
  };
}

/** The gap containing `minute` (start inclusive), or null when a block covers it. */
export function gapAt(day: ScheduleBlock[], minute: number): { min: number; max: number } | null {
  let min = 0;
  for (const b of sortDay(day)) {
    if (minute >= b.start && minute < b.end) return null;
    if (b.end <= minute) min = b.end;
    else return { min, max: b.start };
  }
  return { min, max: DAY_MINUTES };
}

function replaceBlock(week: Week, dayIndex: number, index: number, block: ScheduleBlock): Week {
  return week.map((day, d) =>
    d === dayIndex ? sortDay(day.map((b, i) => (i === index ? block : b))) : day,
  );
}

/** Move a block to `start` keeping its length, stopped by its neighbours and the day edges. */
export function moveBlock(week: Week, dayIndex: number, index: number, start: number): Week {
  const day = week[dayIndex];
  const block = day[index];
  if (!block) return week;
  const length = block.end - block.start;
  const { min, max } = neighbourLimits(day, index);
  const clamped = Math.max(min, Math.min(start, max - length));
  if (clamped === block.start) return week;
  return replaceBlock(week, dayIndex, index, { ...block, start: clamped, end: clamped + length });
}

/** Move one edge of a block, at least MIN_BLOCK_MINUTES long, stopped by its neighbours. */
export function resizeBlock(
  week: Week,
  dayIndex: number,
  index: number,
  edge: "start" | "end",
  minute: number,
): Week {
  const day = week[dayIndex];
  const block = day[index];
  if (!block) return week;
  const { min, max } = neighbourLimits(day, index);
  const next =
    edge === "start"
      ? { ...block, start: Math.max(min, Math.min(minute, block.end - MIN_BLOCK_MINUTES)) }
      : { ...block, end: Math.min(max, Math.max(minute, block.start + MIN_BLOCK_MINUTES)) };
  if (next.start === block.start && next.end === block.end) return week;
  return replaceBlock(week, dayIndex, index, next);
}

/**
 * Set both times of a block (block form). Returns null when the range is empty or reaches
 * into another block of that day.
 */
export function setBlockTimes(
  week: Week,
  dayIndex: number,
  index: number,
  start: number,
  end: number,
): Week | null {
  const day = week[dayIndex];
  const block = day[index];
  if (!block || start >= end || start < 0 || end > DAY_MINUTES) return null;
  const others = day.filter((_, i) => i !== index);
  if (others.some((b) => b.start < end && start < b.end)) return null;
  return replaceBlock(week, dayIndex, index, { ...block, start, end });
}

/**
 * New block from `a` to `b` (either order) inside the gap at `a`, at least MIN_BLOCK_MINUTES.
 * Returns the week and the new block's index, or null when `a` lies in a block or the gap is
 * too small.
 */
export function createBlock(
  week: Week,
  dayIndex: number,
  a: number,
  b: number,
  data?: BlockData,
): { week: Week; index: number } | null {
  const day = week[dayIndex];
  const gap = gapAt(day, Math.min(Math.max(a, 0), DAY_MINUTES - 1));
  if (!gap || gap.max - gap.min < MIN_BLOCK_MINUTES) return null;
  let start = Math.max(gap.min, Math.min(a, b));
  let end = Math.min(gap.max, Math.max(a, b));
  if (end - start < MIN_BLOCK_MINUTES) {
    if (start + MIN_BLOCK_MINUTES <= gap.max) {
      end = start + MIN_BLOCK_MINUTES;
    } else {
      end = gap.max;
      start = end - MIN_BLOCK_MINUTES;
    }
  }
  const block: ScheduleBlock = { start, end };
  if (data && Object.keys(data).length > 0) block.data = { ...data };
  const next = sortDay([...day, block]);
  return {
    week: week.map((d, i) => (i === dayIndex ? next : d)),
    index: next.indexOf(block),
  };
}

/**
 * Where "add block" puts a new block: two hours after the last block if that fits, else the
 * largest gap (at most two hours of it). Null when the day has no room for 15 minutes.
 */
export function suggestBlock(day: ScheduleBlock[]): { start: number; end: number } | null {
  const sorted = sortDay(day);
  if (sorted.length === 0) return { start: 8 * 60, end: 10 * 60 };
  const last = sorted[sorted.length - 1];
  if (DAY_MINUTES - last.end >= 120) return { start: last.end, end: last.end + 120 };
  let best: { start: number; end: number } | null = null;
  let prevEnd = 0;
  for (const b of [...sorted, { start: DAY_MINUTES, end: DAY_MINUTES }]) {
    const size = b.start - prevEnd;
    if (size >= MIN_BLOCK_MINUTES && (!best || size > best.end - best.start)) {
      best = { start: prevEnd, end: b.start };
    }
    prevEnd = Math.max(prevEnd, b.end);
  }
  if (!best) return null;
  return { start: best.start, end: Math.min(best.end, best.start + 120) };
}

export function removeBlock(week: Week, dayIndex: number, index: number): Week {
  return week.map((day, d) => (d === dayIndex ? day.filter((_, i) => i !== index) : day));
}

export function clearDay(week: Week, dayIndex: number): Week {
  return week.map((day, d) => (d === dayIndex ? [] : day));
}

/** The source day's blocks (with their data) replace the blocks of every target day. */
export function copyDay(week: Week, from: number, targets: number[]): Week {
  const source = week[from] ?? [];
  return week.map((day, d) =>
    d !== from && targets.includes(d)
      ? source.map((b) => ({ ...b, ...(b.data ? { data: { ...b.data } } : {}) }))
      : day,
  );
}

/**
 * A block from `start` past midnight to `endNextDay` on the following day becomes two: `start`
 * to 24:00 and 00:00 to `endNextDay` on the next day (Sunday wraps to Monday). Both keep the
 * block's data. Null when one of the two parts would overlap another block.
 */
export function splitOverMidnight(
  week: Week,
  dayIndex: number,
  index: number,
  start: number,
  endNextDay: number,
): Week | null {
  const block = week[dayIndex]?.[index];
  if (!block || endNextDay <= 0 || start >= DAY_MINUTES) return null;
  const nextDay = (dayIndex + 1) % 7;
  const today = week[dayIndex].filter((_, i) => i !== index);
  if (today.some((b) => b.end > start)) return null;
  if (week[nextDay].some((b) => b.start < endNextDay)) return null;
  const copy = (s: number, e: number): ScheduleBlock => ({
    start: s,
    end: e,
    ...(block.data ? { data: { ...block.data } } : {}),
  });
  return week.map((day, d) => {
    if (d === dayIndex) return sortDay([...today, copy(start, DAY_MINUTES)]);
    if (d === nextDay) return sortDay([...day, copy(0, endNextDay)]);
    return day;
  });
}

// ─── Block temperatures ──────────────────────────────────────────────

export interface BlockTemps {
  /** Own temperature as Home Assistant stores it (HA unit system), or undefined. */
  heat?: number;
  cool?: number;
  /** Plain `temperature` key: one value for both sides. */
  single?: number;
}

function num(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return undefined;
}

export function blockTemps(block: ScheduleBlock): BlockTemps {
  const data = block.data ?? {};
  return {
    heat: num(data.heat_temperature),
    cool: num(data.cool_temperature),
    single: num(data.temperature),
  };
}

/** A block without any temperature key uses the room's comfort target. */
export function usesComfort(block: ScheduleBlock): boolean {
  const t = blockTemps(block);
  return t.heat === undefined && t.cool === undefined && t.single === undefined;
}

/**
 * Block data with new own temperatures. `null` means comfort: every temperature key goes.
 * Otherwise only the given sides are written (`heat_temperature`/`cool_temperature`); a side not
 * given keeps its key. A plain `temperature` is dropped, its value moves to every needed side
 * that is neither given nor set already, so that side keeps the value it had. Other keys stay.
 */
export function withTemps(
  data: BlockData | undefined,
  temps: { heat?: number; cool?: number } | null,
  sides: { heat: boolean; cool: boolean } = { heat: true, cool: true },
): BlockData | undefined {
  const next: BlockData = { ...(data ?? {}) };
  if (temps === null) {
    for (const key of TEMP_KEYS) delete next[key];
  } else {
    const single = num(next.temperature);
    delete next.temperature;
    if (single !== undefined) {
      if (sides.heat && temps.heat === undefined && num(next.heat_temperature) === undefined) {
        next.heat_temperature = single;
      }
      if (sides.cool && temps.cool === undefined && num(next.cool_temperature) === undefined) {
        next.cool_temperature = single;
      }
    }
    if (temps.heat !== undefined) next.heat_temperature = temps.heat;
    if (temps.cool !== undefined) next.cool_temperature = temps.cool;
  }
  return Object.keys(next).length > 0 ? next : undefined;
}

/** Round to the temperature step (0.5 °C, 1 °F) without float noise. */
export function roundToStep(value: number, step: number): number {
  const rounded = Math.round(value / step) * step;
  return Number(rounded.toFixed(2));
}

// ─── Cover position ──────────────────────────────────────────────────

/** HA cover position: 0 = closed, 100 = open. */
export const COVER_CLOSED = 0;
export const COVER_OPEN = 100;

/** Position of a cover schedule block, undefined when the block has none. */
export function blockPosition(block: ScheduleBlock): number | undefined {
  const raw = block.data?.position;
  if (raw === undefined || raw === "" || typeof raw === "boolean") return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.max(COVER_CLOSED, Math.min(COVER_OPEN, value)) : undefined;
}

/** Block data with a new position; other keys stay. */
export function withPosition(data: BlockData | undefined, position: number): BlockData {
  const value = Math.round(Math.max(COVER_CLOSED, Math.min(COVER_OPEN, position)));
  return { ...(data ?? {}), position: value };
}

/**
 * Every block of a cover schedule gets an explicit position. The cover logic reads a block
 * without one as closed (and logs it every cycle), so new blocks from any path (drag, add,
 * split, copy, template) and blocks made in Home Assistant without one are written as closed:
 * the same behaviour, now visible. Returns the same week when nothing was missing.
 */
export function withPositions(week: Week): Week {
  if (week.every((day) => day.every((b) => blockPosition(b) !== undefined))) return week;
  return week.map((day) =>
    day.map((b) =>
      blockPosition(b) !== undefined ? b : { ...b, data: withPosition(b.data, COVER_CLOSED) },
    ),
  );
}

/** Whether any block carries a position (a cover schedule made elsewhere). */
export function hasPositions(week: Week): boolean {
  return week.some((day) => day.some((b) => b.data?.position !== undefined));
}

// ─── Templates ───────────────────────────────────────────────────────

export interface WeekTemplate {
  id: "split" | "day" | "home" | "night";
  make: () => Week;
}

function day(...ranges: Array<[string, string]>): ScheduleBlock[] {
  return ranges.map(([from, to]) => ({ start: parseTime(from), end: parseTime(to) }));
}

const weekdays = (fn: () => ScheduleBlock[]) => [0, 1, 2, 3, 4].map(fn);

/** Starting points for a new schedule; labels come from the locale files (`schedule_editor.tpl_*`). */
export const TEMPLATES: WeekTemplate[] = [
  {
    id: "split",
    make: () => [
      ...weekdays(() => day(["06:00", "08:30"], ["17:00", "22:30"])),
      day(["08:00", "23:00"]),
      day(["08:00", "23:00"]),
    ],
  },
  { id: "day", make: () => WEEKDAYS.map(() => day(["07:00", "22:00"])) },
  {
    id: "home",
    make: () => [
      ...weekdays(() => day(["07:00", "22:00"])),
      day(["08:00", "23:00"]),
      day(["08:00", "23:00"]),
    ],
  },
];

/** Starting points for a new cover schedule: closed through the night. */
export const COVER_TEMPLATES: WeekTemplate[] = [
  {
    id: "night",
    make: () =>
      WEEKDAYS.map(() =>
        day(["00:00", "07:00"], ["22:00", "24:00"]).map((b) => ({
          ...b,
          data: { position: COVER_CLOSED },
        })),
      ),
  },
];

/** Day groups for "copy day to…". */
export const DAY_GROUPS = {
  weekdays: [0, 1, 2, 3, 4],
  weekend: [5, 6],
  all: [0, 1, 2, 3, 4, 5, 6],
} as const;

/** Weekday (0 = Monday) and minute of the day in a time zone, for the "now" marker. */
export function nowInZone(
  timeZone: string | undefined,
  date = new Date(),
): {
  day: number;
  minute: number;
} {
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date);
  } catch {
    parts = new Intl.DateTimeFormat("en-US", {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date);
  }
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return {
    day: Math.max(0, names.indexOf(get("weekday"))),
    minute: (Number(get("hour")) % 24) * 60 + Number(get("minute")),
  };
}

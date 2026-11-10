/**
 * What set a room's target besides its schedule, as recorded with the history
 * (backend TARGET_REASON_* plus the mold boost). The analytics chart marks the target
 * line per group; a new reason needs an entry here and its locale keys.
 */
import type { AnalyticsDataPoint } from "../types";
import type { TranslationKey } from "./localize";

export type TargetReason = "override" | "vacation" | "away" | "vacant" | "mold" | "price";

export interface TargetReasonGroup {
  id: string;
  color: string;
  label: TranslationKey;
  reasons: readonly TargetReason[];
}

export const TARGET_REASON_GROUPS: readonly TargetReasonGroup[] = [
  {
    id: "override",
    color: "rgb(233, 30, 99)",
    label: "analytics.reason_group.override",
    reasons: ["override"],
  },
  {
    id: "absence",
    color: "rgb(96, 125, 139)",
    label: "analytics.reason_group.absence",
    reasons: ["vacation", "away", "vacant"],
  },
  {
    id: "mold",
    color: "rgb(121, 85, 72)",
    label: "analytics.reason_group.mold",
    reasons: ["mold"],
  },
  // No group for the price: the price has its own plot below, a gold line on the target
  // repeated it and confused (owner 2026-11-10); the tooltip still names it
];

export const REASON_LABELS: Record<TargetReason, TranslationKey> = {
  override: "analytics.reason.override",
  vacation: "analytics.reason.vacation",
  away: "analytics.reason.away",
  vacant: "analytics.reason.vacant",
  mold: "analytics.reason.mold",
  price: "analytics.reason.price",
};

const isReason = (value: string | undefined): value is TargetReason =>
  value != null && value in REASON_LABELS;

/** Reasons in force for a sample; mold boost and price shift add to what else set the target. */
export function targetReasons(p: AnalyticsDataPoint): TargetReason[] {
  const reasons: TargetReason[] = isReason(p.target_reason) ? [p.target_reason] : [];
  if (p.price_shift) reasons.push("price");
  if ((p.mold_boost ?? 0) > 0) reasons.push("mold");
  return reasons;
}

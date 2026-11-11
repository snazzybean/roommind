import type { TranslationKey } from "../../utils/localize";

/**
 * Categories of the settings page. Pure data: the panel needs the titles for its toolbar
 * (narrow subpage), rs-settings renders the list and the selected panel.
 */
export type SettingsCategoryId =
  | "orphans"
  | "general"
  | "vacation"
  | "presence"
  | "control"
  | "sensors"
  | "price"
  | "learning"
  | "mold"
  | "valve"
  | "compressor"
  | "coil_dry"
  | "notifications"
  | "reset";

export interface SettingsCategory {
  id: SettingsCategoryId;
  icon: string;
  title: TranslationKey;
  /** One sentence in the panel header: what the category does. */
  intro: TranslationKey;
}

export interface SettingsGroup {
  label: TranslationKey;
  categories: SettingsCategory[];
}

export const SETTINGS_GROUPS: SettingsGroup[] = [
  {
    label: "settings.group.attention",
    categories: [
      {
        id: "orphans",
        icon: "mdi:home-remove-outline",
        title: "settings.orphans_title",
        intro: "settings.intro.orphans",
      },
    ],
  },
  {
    label: "settings.group.operation",
    categories: [
      {
        id: "general",
        icon: "mdi:power",
        title: "settings.general_title",
        intro: "settings.intro.general",
      },
      {
        id: "vacation",
        icon: "mdi:airplane",
        title: "vacation.title",
        intro: "settings.intro.vacation",
      },
      {
        id: "presence",
        icon: "mdi:home-account",
        title: "presence.title",
        intro: "settings.intro.presence",
      },
    ],
  },
  {
    label: "settings.group.control",
    categories: [
      {
        id: "control",
        icon: "mdi:tune-variant",
        title: "settings.control_title",
        intro: "settings.intro.control",
      },
      {
        id: "sensors",
        icon: "mdi:thermometer",
        title: "settings.sensors_title",
        intro: "settings.intro.sensors",
      },
      {
        id: "price",
        icon: "mdi:cash-clock",
        title: "settings.price_title",
        intro: "settings.intro.price",
      },
      {
        id: "learning",
        icon: "mdi:brain",
        title: "settings.learning_title",
        intro: "settings.intro.learning",
      },
    ],
  },
  {
    label: "settings.group.protection",
    categories: [
      { id: "mold", icon: "mdi:water-alert", title: "mold.title", intro: "settings.intro.mold" },
      {
        id: "valve",
        icon: "mdi:shield-refresh",
        title: "valve_protection.title",
        intro: "settings.intro.valve",
      },
      {
        id: "compressor",
        icon: "mdi:heat-pump-outline",
        title: "compressor.title",
        intro: "settings.intro.compressor",
      },
      {
        id: "coil_dry",
        icon: "mdi:air-filter",
        title: "coil_dry.title",
        intro: "settings.intro.coil_dry",
      },
    ],
  },
  {
    label: "settings.group.more",
    categories: [
      {
        id: "notifications",
        icon: "mdi:bell-outline",
        title: "notifications.title",
        intro: "settings.intro.notifications",
      },
      {
        id: "reset",
        icon: "mdi:restart",
        title: "settings.reset_title",
        intro: "settings.intro.reset",
      },
    ],
  },
];

const BY_ID = new Map(SETTINGS_GROUPS.flatMap((g) => g.categories).map((c) => [c.id, c]));

/** Shown on wide screens when nothing (or something unknown) is selected. */
export const DEFAULT_SETTINGS_CATEGORY: SettingsCategoryId = "general";

export function getSettingsCategory(id: string): SettingsCategory | undefined {
  return BY_ID.get(id as SettingsCategoryId);
}

/**
 * The category to show for a requested id: unknown ids, and "orphans" without resting rooms,
 * fall back to the default on wide screens and to the list ("") on narrow ones.
 */
export function resolveSettingsCategory(
  requested: string,
  hasOrphans: boolean,
  wide: boolean,
): SettingsCategoryId | "" {
  const known = BY_ID.has(requested as SettingsCategoryId);
  if (known && (requested !== "orphans" || hasOrphans)) return requested as SettingsCategoryId;
  return wide ? DEFAULT_SETTINGS_CATEGORY : "";
}

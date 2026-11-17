/**
 * Core type definitions for RoomMind frontend.
 */

export type ClimateMode = "auto" | "heat_only" | "cool_only";

export type RoomMode = "idle" | "heating" | "cooling";

export type OverrideType = "boost" | "eco" | "custom";

export interface NotificationTarget {
  entity_id: string;
  person_entity: string;
  notify_when: "always" | "home_only";
}

export interface ScheduleEntry {
  entity_id: string;
}

export interface CoverScheduleEntry {
  entity_id: string;
  mode?: "force" | "gate";
}

export interface RoomLiveData {
  current_temp: number | null;
  current_humidity: number | null;
  target_temp: number | null;
  heat_target: number | null;
  cool_target: number | null;
  mode: RoomMode;
  heating_power: number; // 0-100
  device_setpoint: number | null; // Device target temp in Full Control mode
  override_active: boolean;
  override_type: OverrideType | null;
  override_heat: number | null;
  override_cool: number | null;
  override_until: number | null;
  override_suppressed: boolean;
  active_schedule_index: number;
  window_open: boolean;
  confidence: number | null;
  mpc_active: boolean;
  presence_away: boolean;
  occupancy_vacant?: boolean;
  /** Air quality readings (#267), null without sensor or reading. */
  co2?: number | null;
  voc?: number | null;
  air_quality_bad?: boolean;
  air_quality_reason?: "co2" | "voc" | null;
  /** RoomMind runs the room's ventilation entity for bad air. */
  ventilation_active?: boolean;
  mold_risk_level: "ok" | "warning" | "critical";
  mold_surface_rh: number | null;
  mold_surface_temp: number | null;
  mold_prevention_active: boolean;
  /** Applied electricity price shift per side (K), 0 when none. */
  price_shift_heat?: number;
  price_shift_cool?: number;
  price_level?: "cheap" | "normal" | "expensive" | null;
  /** Stricter target a running pre-heat (pre-cool) aims at and when it starts (Unix s). */
  preheat?: { mode: "heating" | "cooling"; target: number; at: number } | null;
  /** Devices kept on at their setback target while the room is idle; `until` = earliest switch-off (Unix s). */
  setback?: { devices: string[]; until: number | null } | null;
  mold_prevention_delta: number;
  blind_position: number | null;
  cover_auto_paused: boolean;
  cover_override_until?: number | null;
  cover_forced_reason: string;
  cover_reason?: string;
  active_cover_schedule_index: number;
  active_heat_sources: string | null;
  learning_paused_reason: "outdoor_unavailable" | null;
  /** Model updates so far (one per ~3 min of learning). */
  n_observations?: number;
  /** `n_observations` when "learn faster" was last used, null if never (counts the fade). */
  boost_applied_at?: number | null;
  compressor_protection_active: boolean;
  compressor_protection_reason: "min_off" | "min_run" | null;
  compressor_protection_until: number | null;
  coil_dry_active: boolean;
  coil_dry_phase: "drain" | "blow" | null;
  coil_dry_until: number | null;
  coil_dry_entities: string[];
  schedule_temp_warnings: ScheduleTempWarning[];
  /** Last 6 h of room temperature, `[unix_ts, temp, target]`, oldest first (dashboard cards). */
  recent_temps?: [number, number | null, number | null][];
}

/** A schedule block temperature the backend discarded as implausible (#395). */
export interface ScheduleTempWarning {
  day: string; // lowercase English weekday, e.g. "monday"
  from: string; // "HH:MM:SS"
  field: "temperature" | "heat_temperature" | "cool_temperature";
  value: string; // the offending raw value; may not be numeric
}

export type DeviceType = "trv" | "ac";
export type DeviceRole = "primary" | "secondary" | "auto";

export interface DeviceConfig {
  entity_id: string;
  type: DeviceType;
  role: DeviceRole;
  heating_system_type?: string;
  idle_action?: "off" | "fan_only" | "setback" | "low"; // default "off"
  idle_fan_mode?: string; // default "low"
  setback_auto_off?: boolean; // setback ends in off after an hour without demand, default off (#255)
  setpoint_mode?: "proportional" | "direct"; // default "proportional"
  setpoint_offset?: number; // °C added to the room target in direct mode, default 0
  coil_dry?: "inherit" | "on" | "off"; // default "inherit"
  coil_dry_minutes?: number; // 0 = inherit global
  coil_dry_mode?: "" | "fan_only" | "dry"; // "" = inherit global
  coil_dry_fan_mode?: string; // "" = inherit global, "__keep__" = keep current
  valve_opening_entity?: string; // number entity for direct valve opening degree (0-100%)
  valve_closing_entity?: string; // number entity for direct valve closing degree (0-100%)
  valve_closing_mode?: "closing_degree" | "idle_opening"; // idle_opening: the second entity is the opening while idle (SONOFF TRV-ZBT)
}

export type ConflictResolution =
  "heating_priority" | "cooling_priority" | "majority" | "outdoor_temp";

/** A stored room whose Home Assistant area was deleted; it rests until the area is back (#494). */
export interface RoomWithoutArea {
  area_id: string;
  display_name: string;
}

export interface CompressorGroup {
  id: string;
  name: string;
  members: string[];
  min_run_minutes: number;
  min_off_minutes: number;
  master_entity: string;
  conflict_resolution: ConflictResolution;
  action_script: string;
  enforce_uniform_mode: boolean;
}

export interface RoomConfig {
  area_id: string;
  thermostats: string[];
  acs: string[];
  devices?: DeviceConfig[];
  temperature_sensor: string;
  humidity_sensor: string;
  occupancy_sensors?: string[];
  occupancy_eco_enabled?: boolean;
  occupancy_eco_delay?: number;
  co2_sensor?: string;
  /** ppm; good again below 80 % of it. */
  co2_threshold?: number;
  voc_sensor?: string;
  /** In the VOC sensor's unit; null = shown, not judged. */
  voc_threshold?: number | null;
  /** fan.*, switch.* or input_boolean.* RoomMind switches on for bad air. */
  ventilation_entity?: string;
  preheat_enabled?: boolean;
  /** K the schedule target may move with the electricity price, 0 = off. */
  price_shift?: number;
  follow_device_setpoint?: boolean;
  window_sensors: string[];
  window_open_delay: number;
  window_close_delay: number;
  climate_mode: ClimateMode;
  schedules: ScheduleEntry[];
  schedule_selector_entity: string;
  comfort_temp?: number;
  eco_temp?: number;
  comfort_heat: number;
  comfort_cool: number;
  eco_heat: number;
  eco_cool: number;
  override_heat?: number | null;
  override_cool?: number | null;
  override_until?: number | null;
  override_type?: OverrideType | null;
  presence_persons?: string[];
  display_name?: string;
  heating_system_type?: string;
  covers?: string[];
  covers_auto_enabled?: boolean;
  covers_deploy_threshold?: number;
  covers_min_position?: number;
  covers_override_minutes?: number;
  cover_schedules?: CoverScheduleEntry[];
  cover_schedule_selector_entity?: string;
  cover_orientations?: Record<string, number>;
  covers_outdoor_min_temp?: number | null;
  covers_night_close?: boolean;
  covers_night_position?: number;
  covers_night_close_elevation?: number;
  covers_night_close_offset_minutes?: number;
  covers_snap_deploy?: boolean;
  covers_window_hold?: boolean;
  cover_min_positions?: Record<string, number>;
  ignore_presence?: boolean;
  is_outdoor?: boolean;
  valve_protection_exclude?: string[];
  heat_source_orchestration?: boolean;
  heat_source_primary_delta?: number;
  heat_source_outdoor_threshold?: number;
  heat_source_ac_min_outdoor?: number;
  /** Orchestration: expensive electricity prefers the primary source, cheap the AC. */
  heat_source_price_aware?: boolean;
  climate_control_enabled?: boolean;
  tou_store_enabled?: boolean;
  tou_heat_min?: number | null;
  tou_heat_max?: number | null;
  tou_cool_min?: number | null;
  tou_cool_max?: number | null;
  tou_swing?: number | null;
  tou_store_gap?: number | null;
  /** Tariff rule rows: thin references into the shared library. */
  tou_overrides?: TouOverrideRow[];
  /** Gates the whole tariff schedule section on this room's card. */
  tou_schedule_enabled?: boolean;
  live?: RoomLiveData;
}

/** Normalized tariff tier used by the Time-of-Use module. */
export type TouTier = "peak" | "mid" | "off" | "ultra_low";

/** Which source class answers the current tier ("auto" = legacy cascade). */
export type TouTierSource = "auto" | "period" | "rate" | "flags";

/** Which source provides the future-tier timeline ("auto" = calendars, then
 * next-change; "next_change_rate" = classify the provider's next-period rate
 * with the cost thresholds; "none" = shape only, no pre-conditioning/coasting
 * planning). */
export type TouLookahead = "auto" | "calendar" | "next_change_rate" | "next_change" | "none";

/** Binding of one tariff calendar: which calendar entity carries which tier. */
export interface TouCalendarBinding {
  entity_id: string;
  tier: TouTier;
}

/** Manual tariff-window row: a rate applied between two wall-clock times on
 * the chosen weekdays. Empty days list = every day; an end not after the
 * start wraps past midnight. Maps to a tier through the cost thresholds. */
export interface TouRateWindow {
  id: string;
  rate: number;
  start: string;
  end: string;
  days: string[];
}

/**
 * Global store limits (Settings -> Energy price fine-tune): the consent band
 * per side, the max deviation from the schedule and the price-gap ratio that
 * must justify storing. Effective values reach rooms via the `tou_limits`
 * view on rooms/list; defaults live in const.py (DEFAULT_TOU_*).
 */
export interface TouLimits {
  heat_min: number;
  heat_max: number;
  cool_min: number;
  cool_max: number;
  swing: number;
  store_gap: number;
}

/**
 * A room's optional overrides of the global limits. A null/missing key means
 * "inherit the global value" — the same semantics TouManager.make_adjuster
 * applies server-side (room value else settings value else default).
 */
export type TouRoomLimits = Partial<Record<keyof TouLimits, number | null>>;

/**
 * One sensor-driven energy tier (settings["tou_extra_tiers"]): an on-site
 * source the grid tariff cannot describe. While its sensor evidence holds,
 * the tier overrides the grid tariff — state, price and rule anchoring.
 * List order = priority (the first holding entry wins).
 */
export interface TouExtraTier {
  id: string;
  name: string;
  entity_id: string;
  kind: "binary_on" | "numeric_above" | "numeric_below" | "state";
  threshold?: number;
  states?: string[];
  for_seconds?: number;
  /** Price per kWh in the household unit: 0 = free (self-consumed solar),
   * negative = export credit, null/absent = unpriced (economically neutral). */
  cost?: number | null;
  unit?: string;
  enabled?: boolean;
}

/** What a tariff rule row does at its anchor (const.py TOU_ROW_ACTIONS). */
export type TouOverrideAction = "set" | "raise" | "lower" | "arrive";

/** How long a card row's window stays in force (TOU_ROW_UNTILS). */
export type TouOverrideUntil = "tier_window" | "minutes" | "clock";

/**
 * A card-authored rule definition: an action anchored to a tier boundary.
 * heat/cool hold a °C target for set/arrive and a Δ for raise/lower; a blank
 * side skips that mode. The library owns ids, so definitions never carry one
 * (websocket_api._TOU_RULE_DEF_FIELDS mirrors this shape).
 */
export interface TouRuleDef {
  name: string;
  tier: TouTier | "any";
  edge: "start" | "end";
  action: TouOverrideAction;
  heat?: number | "comfort" | "eco" | null;
  cool?: number | "comfort" | "eco" | null;
  until: TouOverrideUntil;
  minutes?: number;
  clock?: string;
  days?: string[];
  between?: { from: string; to: string } | null;
}

/** One entry of the shared rule library (settings["tou_rules"]). */
export type TouRule = TouRuleDef & { id: string };

/**
 * A tariff row on the room card: a thin reference into the library with a
 * per-row toggle. `definition` rides along only while the card stages a
 * create/edit; the server upserts it and stores the reference stripped.
 */
export interface TouOverrideRow {
  id: string;
  rule_id: string;
  enabled?: boolean;
  definition?: TouRuleDef;
}

/** Per-tier confirmation data from the bound tariff sources (see
 * TouManager.tier_info): the price the sources know for that tier and the
 * raw period vocabulary that resolves to it. Kind marks where the number
 * came from: live now, provider's next-period price, persisted last known
 * (source currently down), manual window, or configured cutoff. */
export interface TouTierInfoTier {
  rate: number | null;
  kind: "live" | "next" | "last" | "window" | "cutoff" | "source" | null;
  min?: number | null;
  max?: number | null;
  count?: number;
  ts?: number | null;
  /** Display name of an extra tier; null on the grid four (i18n names). */
  label?: string | null;
  names: string[];
  current: boolean;
}

export interface TouTierInfo {
  unit: string;
  tiers: Record<string, TouTierInfoTier>;
  unmapped: { state: string; count: number }[];
  current: { tier: TouTier; rate: number; stale: boolean } | null;
  next: { ts: number | null; tier: TouTier; rate: number | null; stale: boolean } | null;
  /** Why the future view is incomplete while its sensors are bound:
   * "no_tier" (nothing says which period follows), "no_time" (the change
   * sensor is not a timestamp), "no_price" (no price for the coming tier). */
  next_hint?: "no_tier" | "no_time" | "no_price" | "";
}

export interface GlobalSettings {
  outdoor_temp_sensor: string;
  outdoor_humidity_sensor: string;
  outdoor_cooling_min?: number;
  outdoor_heating_max?: number;
  control_mode?: "mpc" | "bangbang";
  comfort_weight?: number;
  weather_entity?: string;
  outdoor_unavailable_notify?: boolean;
  climate_control_active?: boolean;
  learning_disabled_rooms?: string[];
  hidden_rooms?: string[];
  prediction_enabled?: boolean;
  vacation_temp?: number;
  vacation_until?: number | null;
  presence_enabled?: boolean;
  presence_persons?: string[];
  presence_away_action?: "eco" | "off";
  presence_clears_override?: boolean;
  schedule_off_action?: "eco" | "off";
  valve_protection_enabled?: boolean;
  valve_protection_interval_days?: number;
  coil_dry_enabled?: boolean;
  coil_dry_minutes?: number;
  coil_dry_mode?: "fan_only" | "dry";
  coil_dry_fan_mode?: string;
  coil_dry_min_cooling_minutes?: number;
  coil_dry_drain_minutes?: number;
  mold_detection_enabled?: boolean;
  mold_humidity_threshold?: number;
  mold_f_rsi?: number;
  mold_sustained_minutes?: number;
  mold_notification_cooldown?: number;
  mold_notifications_enabled?: boolean;
  mold_notification_targets?: NotificationTarget[];
  mold_prevention_enabled?: boolean;
  mold_prevention_intensity?: "light" | "medium" | "strong";
  mold_prevention_notify_enabled?: boolean;
  mold_prevention_notify_targets?: NotificationTarget[];
  compressor_groups?: CompressorGroup[];
  room_order?: string[];
  group_by_floor?: boolean;
  boost_applied_at?: Record<string, number>;
  /** Time-of-Use tariff awareness (managers/tou_manager.py). */
  tou_enabled?: boolean;
  /** Shared tariff rule library, so cards resolve row rule_id -> definition. */
  tou_rules?: TouRule[];
  /** Sensor-driven energy tier registry (S6): drives the rule tier selects. */
  tou_extra_tiers?: TouExtraTier[];
  tou_tier_source?: TouTierSource;
  tou_lookahead?: TouLookahead;
  tou_rate_entity?: string;
  tou_period_entity?: string;
  tou_next_change_entity?: string;
  tou_next_rate_entity?: string;
  tou_next_period_entity?: string;
  tou_next_change_tier?: TouTier | "";
  tou_calendar_entities?: TouCalendarBinding[];
  tou_rate_windows?: TouRateWindow[];
  tou_flag_entities?: Partial<Record<TouTier, string>>;
  tou_price_weighting?: boolean;
  tou_peak_threshold?: number | null;
  tou_mid_threshold?: number | null;
  tou_ultra_threshold?: number | null;
  tou_heat_min?: number;
  tou_heat_max?: number;
  tou_cool_min?: number;
  tou_cool_max?: number;
  tou_swing?: number;
  tou_store_gap?: number;
  tou_coast_max_minutes?: number;
  tou_period_aliases?: Record<string, string>;
}

// HA types for panel integration
export interface HassConnection {
  addEventListener(event: string, callback: () => void): void;
  removeEventListener(event: string, callback: () => void): void;
}

export interface HomeAssistant {
  callWS: <T>(msg: Record<string, unknown>) => Promise<T>;
  callService: (domain: string, service: string, data?: Record<string, unknown>) => Promise<void>;
  states: Record<string, HassEntity>;
  areas: Record<string, HassArea>;
  floors?: Record<string, HassFloor>;
  entities: Record<string, HassEntityRegistryEntry>;
  devices: Record<string, HassDeviceRegistryEntry>;
  language: string;
  config: { unit_system: { temperature: string }; time_zone?: string };
  user?: { is_admin: boolean; name?: string };
  connection?: HassConnection;
  /** Translated state as Home Assistant shows it (e.g. "Heizen"); missing in old releases. */
  formatEntityState?: (stateObj: HassEntity) => string;
  formatEntityAttributeValue?: (stateObj: HassEntity, attribute: string, value?: unknown) => string;
  /** HA's own light/dark choice (may differ from the OS). */
  themes?: { darkMode?: boolean };
}

export interface HassArea {
  area_id: string;
  name: string;
  picture: string | null;
  floor_id: string | null;
  icon?: string | null;
}

export interface HassFloor {
  floor_id: string;
  name: string;
  level: number | null;
}

export interface HassEntityRegistryEntry {
  entity_id: string;
  area_id: string | null;
  device_id: string | null;
  platform: string;
}

export interface HassDeviceRegistryEntry {
  id: string;
  area_id: string | null;
  name?: string | null;
  name_by_user?: string | null;
}

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
  last_updated?: string;
}

export interface AnalyticsDataPoint {
  ts: number;
  room_temp: number | null;
  outdoor_temp: number | null;
  target_temp: number | null;
  mode: string;
  predicted_temp: number | null;
  window_open: boolean;
  heating_power: number | null;
  solar_irradiance: number | null;
  blind_position?: number | null;
  cover_reason?: string;
  device_setpoint?: number | null;
  humidity?: number | null;
  /** Room CO2 in ppm (#267). */
  co2?: number | null;
  heat_target?: number | null;
  cool_target?: number | null;
  /** What set the target: "" schedule, else a TargetReason. */
  target_reason?: string;
  mold_boost?: number | null;
  price?: number | null;
  price_level?: string;
  /** Heat-side shift the electricity price applied (cool side moves the other way). */
  price_shift?: number | null;
}

export interface RunOvershoot {
  runs: number;
  mean: number;
  max: number;
}

export interface AnalyticsStats {
  hours: number;
  heating_hours: number;
  cooling_hours: number;
  window_hours: number;
  heating_starts: number;
  cooling_starts: number;
  /** How far past the target the room went after the runs, null without runs. */
  heat_overshoot?: RunOvershoot | null;
  /** Run hours by price level, null without a price source. */
  price?: {
    heating_hours: Partial<Record<"cheap" | "normal" | "expensive", number>>;
    cooling_hours: Partial<Record<"cheap" | "normal" | "expensive", number>>;
    shifted_hours: number;
  } | null;
  cool_overshoot?: RunOvershoot | null;
  comfort: {
    below_pct: number;
    within_pct: number;
    above_pct: number;
    mean_deviation: number;
    /** Mean distance while off target, null when the room never was. */
    miss_deviation: number | null;
  } | null;
}

export interface RhythmDay {
  date: string;
  heat: Array<number | null>;
  cool: Array<number | null>;
  window: Array<number | null>;
  deviation: Array<number | null>;
  /** Share of the judged time too cold / too warm, same tolerance as the period figures. */
  below: Array<number | null>;
  above: Array<number | null>;
  temp: Array<number | null>;
  humidity: Array<number | null>;
  outdoor: Array<number | null>;
  /** The day's judged share on target, null without judged samples. */
  within: number | null;
}

export interface AnalyticsRhythm {
  days: RhythmDay[];
}

export interface ModelDay {
  /** Local date, YYYY-MM-DD. */
  date: string;
  confidence: number;
  mpc_active: boolean;
  /** Mean absolute error of the ~3-min forecast that day (K), null without measurements. */
  error: number | null;
  error_steps: number;
}

export interface AnalyticsData {
  detail: AnalyticsDataPoint[];
  history: AnalyticsDataPoint[];
  forecast?: AnalyticsDataPoint[];
  stats?: AnalyticsStats;
  rhythm?: AnalyticsRhythm | null;
  /** Unit of the price source (ct/kWh, EUR/kWh, ...), empty for a switch or none. */
  price_unit?: string;
  model: {
    confidence: number;
    /** One entry per local day, oldest first. */
    daily_history?: ModelDay[];
    model: {
      C: number;
      U: number;
      Q_heat: number;
      Q_cool: number;
      Q_solar: number;
      Q_occupancy: number;
      Q_fast?: number;
    };
    n_samples: number;
    n_observations: number;
    /** Unix time of the model's last learning step, null before the first or from an older store */
    last_update_at?: number | null;
    n_heating: number;
    n_cooling: number;
    applicable_modes: string[];
    mpc_active: boolean;
    sigma_e: number;
    prediction_std_idle: number;
    prediction_std_heating: number;
    has_occupancy_sensors: boolean;
    /** Sun / occupancy were in the data (variance below its start), else the gain is the start guess */
    solar_learned?: boolean;
    occupancy_learned?: boolean;
    solar_gain_now?: number;
    solar_gain_today_max?: number;
    /** Radiator rooms: rise a regular run's stored heat gives after the stop (°C), its decay time */
    afterglow_k?: number;
    afterglow_minutes?: number;
    afterglow_learned?: boolean;
    /** The model one hour ahead on this range (backend model_backtest), null without a model. */
    backtest?: ModelBacktest | null;
  };
}

export interface BacktestFigures {
  /** Hours (overlapping, one per recorded point) that went into the figure. */
  n: number;
  /** Mean absolute deviation after the horizon (°C), null below the minimum of hours. */
  mae: number | null;
  /** Mean signed deviation: model minus measured, negative = room warmer than the model says. */
  bias: number | null;
}

export interface ModelBacktest {
  horizon_minutes: number;
  idle: BacktestFigures;
  /** Hours with heating or cooling. */
  active: BacktestFigures;
}

export type TimeRange = "12h" | "24h" | "2d" | "7d" | "14d" | "30d" | "90d";

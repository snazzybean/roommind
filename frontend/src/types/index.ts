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
}

export interface RoomLiveData {
  current_temp: number | null;
  current_humidity: number | null;
  target_temp: number | null;
  heat_target: number | null;
  cool_target: number | null;
  mode: RoomMode;
  heating_power: number; // 0-100
  trv_setpoint: number | null; // TRV target temp when heating (Full Control)
  override_active: boolean;
  override_type: OverrideType | null;
  override_temp: number | null;
  override_until: number | null;
  active_schedule_index: number;
  window_open: boolean;
  confidence: number | null;
  mpc_active: boolean;
  presence_away: boolean;
  mold_risk_level: "ok" | "warning" | "critical";
  mold_surface_rh: number | null;
  mold_prevention_active: boolean;
  mold_prevention_delta: number;
  blind_position: number | null;
  cover_auto_paused: boolean;
  cover_forced_reason: string;
  active_cover_schedule_index: number;
}

export interface RoomConfig {
  area_id: string;
  thermostats: string[];
  acs: string[];
  temperature_sensor: string;
  humidity_sensor: string;
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
  override_temp?: number | null;
  override_until?: number | null;
  override_type?: OverrideType | null;
  presence_persons?: string[];
  display_name?: string;
  heating_system_type?: string;
  covers?: string[];
  covers_auto_enabled?: boolean;
  covers_deploy_threshold?: number;
  covers_min_position?: number;
  covers_outdoor_min_temp?: number | null;
  covers_override_minutes?: number;
  cover_schedules?: CoverScheduleEntry[];
  cover_schedule_selector_entity?: string;
  covers_night_close?: boolean;
  covers_night_position?: number;
  live?: RoomLiveData;
}

export interface GlobalSettings {
  outdoor_temp_sensor: string;
  outdoor_humidity_sensor: string;
  outdoor_cooling_min?: number;
  outdoor_heating_max?: number;
  control_mode?: "mpc" | "bangbang";
  comfort_weight?: number;
  weather_entity?: string;
  climate_control_active?: boolean;
  learning_disabled_rooms?: string[];
  hidden_rooms?: string[];
  prediction_enabled?: boolean;
  vacation_temp?: number;
  vacation_until?: number | null;
  presence_enabled?: boolean;
  presence_persons?: string[];
  presence_away_action?: "eco" | "off";
  schedule_off_action?: "eco" | "off";
  valve_protection_enabled?: boolean;
  valve_protection_interval_days?: number;
  mold_detection_enabled?: boolean;
  mold_humidity_threshold?: number;
  mold_sustained_minutes?: number;
  mold_notification_cooldown?: number;
  mold_notifications_enabled?: boolean;
  mold_notification_targets?: NotificationTarget[];
  mold_prevention_enabled?: boolean;
  mold_prevention_intensity?: "light" | "medium" | "strong";
  mold_prevention_notify_enabled?: boolean;
  mold_prevention_notify_targets?: NotificationTarget[];
  room_order?: string[];
  group_by_floor?: boolean;
  boost_applied_at?: Record<string, number>;
}

// HA types for panel integration
export interface HomeAssistant {
  callWS: <T>(msg: Record<string, unknown>) => Promise<T>;
  callService: (
    domain: string,
    service: string,
    data?: Record<string, unknown>
  ) => Promise<void>;
  states: Record<string, HassEntity>;
  areas: Record<string, HassArea>;
  floors?: Record<string, HassFloor>;
  entities: Record<string, HassEntityRegistryEntry>;
  devices: Record<string, HassDeviceRegistryEntry>;
  language: string;
  config: { unit_system: { temperature: string } };
}

export interface HassArea {
  area_id: string;
  name: string;
  picture: string | null;
  floor_id: string | null;
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
}

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
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
  blind_position?: number | null;
}

export interface AnalyticsData {
  detail: AnalyticsDataPoint[];
  history: AnalyticsDataPoint[];
  forecast?: AnalyticsDataPoint[];
  model: {
    confidence: number;
    model: { C: number; U: number; Q_heat: number; Q_cool: number; Q_solar: number };
    n_samples: number;
    n_observations: number;
    n_heating: number;
    n_cooling: number;
    applicable_modes: string[];
    mpc_active: boolean;
    sigma_e: number;
    prediction_std_idle: number;
    prediction_std_heating: number;
  };
}

export type TimeRange = "12h" | "24h" | "2d" | "7d" | "14d" | "30d" | "90d";

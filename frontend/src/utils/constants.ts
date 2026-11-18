/** Far-future sentinel timestamp (year 3000): vacation active indefinitely. */
export const VACATION_SENTINEL = 32503680000;

/** Minutes until an empty room drops to eco; mirrors DEFAULT_OCCUPANCY_ECO_DELAY_MINUTES (#180). */
export const DEFAULT_OCCUPANCY_ECO_DELAY = 15;
/** Lower bound of the delay; mirrors MIN_OCCUPANCY_ECO_DELAY_MINUTES. */
export const MIN_OCCUPANCY_ECO_DELAY = 5;

/** CO2 threshold in ppm and its bounds; mirror DEFAULT/MIN/MAX_CO2_THRESHOLD (#267). */
export const DEFAULT_CO2_THRESHOLD = 1000;
export const MIN_CO2_THRESHOLD = 800;
export const MAX_CO2_THRESHOLD = 5000;

/** Humidity limits in % RH; mirror DEFAULT/MIN/MAX_HUMIDITY_* and HUMIDITY_LIMIT_GAP (#518, #526). */
export const DEFAULT_HUMIDITY_MAX = 60;
export const DEFAULT_HUMIDITY_MIN = 40;
export const MIN_HUMIDITY_MAX = 40;
export const MAX_HUMIDITY_MAX = 90;
export const MIN_HUMIDITY_MIN = 20;
export const MAX_HUMIDITY_MIN = 60;
export const HUMIDITY_LIMIT_GAP = 10;
/** Air counts as good again below this share of the threshold; mirrors AIR_QUALITY_CLEAR_FACTOR. */
export const AIR_QUALITY_CLEAR_FACTOR = 0.8;

/** Slider default; mirrors DEFAULT_COMFORT_WEIGHT. At and above it pre-heating is not limited. */
export const DEFAULT_COMFORT_WEIGHT = 70;
/** Longest pre-heat lead; mirrors PREHEAT_MAX_LEAD_HOURS (mpc_optimizer). */
export const PREHEAT_MAX_LEAD_HOURS = 12;

/** Pre-heat lead in hours the slider allows; mirrors preheat_max_blocks() (5-min blocks). */
export function preheatLeadHours(comfortWeight: number): number {
  const hours =
    (PREHEAT_MAX_LEAD_HOURS * Math.min(Math.max(comfortWeight, 0), DEFAULT_COMFORT_WEIGHT)) /
    DEFAULT_COMFORT_WEIGHT;
  return (Math.floor((hours * 60) / 5) * 5) / 60;
}

/** MPC data gate; mirror MIN_IDLE_UPDATES, MIN_ACTIVE_UPDATES and MPC_MAX_PREDICTION_STD (mpc_controller). */
export const MPC_MIN_IDLE_SAMPLES = 60;
export const MPC_MIN_ACTIVE_SAMPLES = 20;
export const MPC_MAX_PREDICTION_STD = 0.5;

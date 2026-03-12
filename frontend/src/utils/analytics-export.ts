/**
 * Analytics data export utilities (CSV and diagnostics).
 */
import type { AnalyticsData } from "../types";
import type { RoomConfig, HomeAssistant } from "../types";

export function buildCsvString(data: AnalyticsData): string | null {
  const points = [...data.history, ...data.detail];
  if (points.length === 0) return null;

  const header =
    "timestamp,datetime,room_temp,outdoor_temp,target_temp,mode,predicted_temp,window_open,heating_power,solar_irradiance,blind_position,device_setpoint";
  const rows = points.map((p) => {
    const dt = new Date(p.ts * 1000).toISOString();
    const rt = p.room_temp ?? "";
    const ot = p.outdoor_temp ?? "";
    const tt = p.target_temp ?? "";
    const pt = p.predicted_temp ?? "";
    const hp = p.heating_power ?? "";
    const si = p.solar_irradiance ?? "";
    const bp = p.blind_position ?? "";
    const ds = p.device_setpoint ?? "";
    return `${p.ts},${dt},${rt},${ot},${tt},${p.mode},${pt},${p.window_open},${hp},${si},${bp},${ds}`;
  });

  return [header, ...rows].join("\n");
}

export function buildDiagnosticsString(
  areaId: string,
  data: AnalyticsData,
  room: RoomConfig | undefined,
  controlMode: string,
): string | null {
  if (!areaId || !data) return null;

  const points = [...(data.history ?? []), ...(data.detail ?? [])];
  const lastPoint = points.length > 0 ? points[points.length - 1] : null;

  const payload = {
    version: "0.2.0",
    area_id: areaId,
    room_config: {
      climate_mode: room?.climate_mode,
      has_thermostats: (room?.thermostats?.length || 0) > 0,
      has_acs: (room?.acs?.length || 0) > 0,
      has_temp_sensor: !!room?.temperature_sensor,
      has_window_sensors: (room?.window_sensors?.length || 0) > 0,
    },
    live: room?.live || {},
    model: data.model || {},
    settings: {
      control_mode: controlMode,
    },
    outdoor: {
      temp: lastPoint?.outdoor_temp ?? null,
    },
  };

  return JSON.stringify(payload, null, 2);
}

export function downloadString(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function buildExportFilename(
  hass: HomeAssistant,
  rooms: Record<string, RoomConfig>,
  selectedRoom: string,
  rangeStart: number,
  rangeEnd: number,
  suffix: string,
  ext: string,
): string {
  const area = hass?.areas?.[selectedRoom];
  const roomConfig = rooms[selectedRoom];
  const name = (roomConfig?.display_name || area?.name || selectedRoom)
    .replace(/\s+/g, "_")
    .toLowerCase();
  if (suffix) {
    return `roommind_${suffix}_${name}.${ext}`;
  }
  const from = new Date(rangeStart).toISOString().slice(0, 10);
  const to = new Date(rangeEnd).toISOString().slice(0, 10);
  return `roommind_${name}_${from}_${to}.${ext}`;
}

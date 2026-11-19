import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomFanMode, RoomLiveData } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize, type TranslationKey } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";
import { formatMinutes, formatNumber, formatPercent } from "../utils/format";
import { tokens } from "../styles/tokens";
import { inputStyles } from "../styles/input-styles";
import { formStyles } from "../styles/form-styles";
import {
  DEFAULT_CO2_THRESHOLD,
  DEFAULT_HUMIDITY_MAX,
  DEFAULT_HUMIDITY_MIN,
  DEFAULT_OCCUPANCY_ECO_DELAY,
  HUMIDITY_LIMIT_GAP,
  MAX_CO2_THRESHOLD,
  MAX_HUMIDITY_MAX,
  MAX_HUMIDITY_MIN,
  MIN_CO2_THRESHOLD,
  MIN_HUMIDITY_MAX,
  MIN_HUMIDITY_MIN,
  MIN_OCCUPANCY_ECO_DELAY,
} from "../utils/constants";
import "./shared/rs-field";
import "./shared/rs-number-field";
import "./shared/rs-icon-button";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";
import "./shared/rs-segmented";

type SensorKind =
  | "temp"
  | "humidity"
  | "occupancy"
  | "window"
  | "co2"
  | "voc"
  | "ventilation"
  | "dehumidifier"
  | "humidifier"
  | "room_fan"
  | "sun";
type SingleKind = Exclude<SensorKind, "occupancy" | "window">;

const OCCUPANCY_CLASSES = ["occupancy", "motion", "presence"];
const WINDOW_CLASSES = ["window", "door", "opening"];
// VOC sensors report an index, ppb or µg/m³; ESPHome's SGP4x index comes as aqi or without a class
const VOC_CLASSES = ["volatile_organic_compounds", "volatile_organic_compounds_parts", "aqi"];
const VENTILATION_DOMAINS = ["fan", "switch", "input_boolean"];
const HUMIDITY_DEVICE_DOMAINS = ["humidifier", "switch", "input_boolean"];
type SunKind = "irradiance" | "illuminance" | "percent";

/** What a sun sensor measures; same rule as the backend (solar_sensor_manager.solar_sensor_kind). */
function sunKind(attrs: Record<string, unknown>): SunKind | null {
  const dc = attrs.device_class as string | undefined;
  const unit = attrs.unit_of_measurement as string | undefined;
  if (dc === "irradiance" || unit === "W/m²") return "irradiance";
  if (dc === "illuminance" || unit === "lx") return "illuminance";
  if (unit === "%" && !dc) return "percent";
  return null;
}
const SINGLE_KEYS: Record<SingleKind, string> = {
  temp: "temperature_sensor",
  humidity: "humidity_sensor",
  co2: "co2_sensor",
  voc: "voc_sensor",
  ventilation: "ventilation_entity",
  dehumidifier: "dehumidifier_entity",
  humidifier: "humidifier_entity",
  room_fan: "room_fan_entity",
  sun: "solar_sensor",
};

/** What an empty single-entity group says instead of "none assigned". */
const EMPTY_KEYS: Partial<Record<SensorKind, TranslationKey>> = {
  ventilation: "sensors.no_ventilation",
  dehumidifier: "sensors.no_dehumidifier",
  humidifier: "sensors.no_humidifier",
  room_fan: "sensors.no_room_fan",
};

const ROOM_FAN_MODES: { value: RoomFanMode; key: TranslationKey }[] = [
  { value: "heat", key: "sensors.room_fan_heat" },
  { value: "cool", key: "sensors.room_fan_cool" },
  { value: "both", key: "sensors.room_fan_both" },
];

@customElement("rs-sensor-section")
export class RsSensorSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public area!: HassArea;
  @property({ type: String }) public temperatureSensor = "";
  @property({ type: String }) public humiditySensor = "";
  @property({ attribute: false }) public occupancySensors: Set<string> = new Set();
  @property({ type: Boolean }) public occupancyEcoEnabled = false;
  @property({ type: Number }) public occupancyEcoDelay = DEFAULT_OCCUPANCY_ECO_DELAY;
  @property({ attribute: false }) public windowSensors: Set<string> = new Set();
  @property({ type: Number }) public windowOpenDelay = 0;
  @property({ type: Number }) public windowCloseDelay = 0;
  @property({ type: String }) public co2Sensor = "";
  @property({ type: Number }) public co2Threshold = DEFAULT_CO2_THRESHOLD;
  @property({ type: String }) public vocSensor = "";
  @property({ attribute: false }) public vocThreshold: number | null = null;
  @property({ type: String }) public ventilationEntity = "";
  /** Humidity limits in % RH, null = that side not regulated (#518, #526). */
  @property({ attribute: false }) public humidityMax: number | null = null;
  @property({ attribute: false }) public humidityMin: number | null = null;
  @property({ type: String }) public dehumidifierEntity = "";
  @property({ type: String }) public humidifierEntity = "";
  /** Sunlight on the room (#303). */
  @property({ type: String }) public solarSensor = "";
  /** Ceiling or standing fan RoomMind runs while the room heats or cools (#266). */
  @property({ type: String }) public roomFanEntity = "";
  @property({ type: String }) public roomFanMode: RoomFanMode = "both";
  /** The room can heat and cool: the fan's heat/cool/both choice is offered. */
  @property({ type: Boolean }) public roomFanChoice = false;
  /** An AC may dry the room past the upper humidity limit (#440). */
  @property({ type: Boolean }) public acDryEnabled = true;
  /** The room has an AC that can dry (see rs-room-detail `_acDryChoice`): the switch is offered. */
  @property({ type: Boolean }) public acDryChoice = false;
  /** Live state of the room: air quality judgement and whether RoomMind runs the ventilation. */
  @property({ attribute: false }) public live?: RoomLiveData;
  @property({ type: String }) public heatingSystemType = "";
  @property({ type: Boolean }) public editing = false;
  /** Outdoor area: only temperature and humidity, nothing that controls. */
  @property({ type: Boolean }) public outdoor = false;
  @property() public language = "en";

  /** Kind whose entity picker is open. */
  @state() private _pickerFor: SensorKind | null = null;
  private _focusKind: SensorKind | null = null;
  private _areaIds = new Set<string>();

  static styles = [
    tokens,
    inputStyles,
    formStyles,
    css`
      :host {
        display: block;
        --rs-form-inline: var(--rs-space-4);
        container-type: inline-size;
      }

      .group-title ha-icon {
        --mdc-icon-size: 18px;
        margin-inline-end: var(--rs-space-1);
      }

      .rows {
        display: flex;
        flex-direction: column;
      }

      .picker {
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .picker ha-entity-picker {
        flex: 1;
        min-width: 0;
      }

      .pair {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--rs-space-3);
      }

      @container (max-width: 520px) {
        .pair {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  render() {
    if (!this.editing) {
      return this._renderViewMode();
    }
    return this._renderEditMode();
  }

  // ─── View mode ───

  private _renderViewMode() {
    const l = this.hass.language;
    const delays = [
      this.windowOpenDelay
        ? `${localize("devices.window_open_delay", l)}: ${this.windowOpenDelay} s`
        : "",
      this.windowCloseDelay
        ? `${localize("devices.window_close_delay", l)}: ${this.windowCloseDelay} s`
        : "",
    ].filter(Boolean);
    const occupancyNote =
      this.occupancyEcoEnabled && this.occupancySensors.size > 0
        ? localize("devices.occupancy_eco_view", l, {
            time: formatMinutes(this.occupancyEcoDelay, l),
          })
        : "";

    return html`
      ${
        this.temperatureSensor
          ? this._row(
              this.temperatureSensor,
              "mdi:thermometer",
              this.temperatureSensor.startsWith("climate.")
                ? `${localize("detail.sensors.temperature", l)} · ${localize("sensors.device_sensor", l)}`
                : localize("detail.sensors.temperature", l),
              this._tempValue(this.temperatureSensor),
            )
          : html`<rs-list-row
              clickable
              chevron
              icon="mdi:thermometer-off"
              .heading=${localize("detail.sensors.temperature", l)}
              .secondary=${localize(
                this.outdoor ? "sensors.outdoor_no_temperature" : "detail.sensors.no_temperature",
                l,
              )}
              @row-click=${this._fireEdit}
            ></rs-list-row>`
      }
      ${
        this.humiditySensor
          ? this._row(
              this.humiditySensor,
              "mdi:water-percent",
              localize("detail.sensors.humidity", l),
              this._humidityValue(this.humiditySensor),
            )
          : nothing
      }
      ${this.outdoor ? nothing : this._renderControlRows(delays, occupancyNote)}
      ${this.outdoor ? nothing : this._renderHumidityRows()}
      ${this.outdoor ? nothing : this._renderAirRows()}
      ${this.outdoor || !this.roomFanEntity ? nothing : this._renderRoomFanRow()}
      ${this.outdoor || !this.solarSensor ? nothing : this._renderSunRow()}
      <rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:plus"
        .heading=${localize("detail.sensors.add", l)}
        @row-click=${this._fireEdit}
      ></rs-list-row>
    `;
  }

  /** Window and occupancy rows; they only matter where RoomMind controls. */
  private _renderControlRows(delays: string[], occupancyNote: string) {
    const l = this.hass.language;
    return html`
      ${[...this.windowSensors].map((id) => {
        const open = this.hass.states[id]?.state === "on";
        return this._row(
          id,
          open ? "mdi:window-open-variant" : "mdi:window-closed-variant",
          [localize("detail.sensors.window", l), ...delays].join(" · "),
          this._binaryValue(id, "detail.sensors.open", "detail.sensors.closed"),
          open ? "var(--rs-warn)" : "",
        );
      })}
      ${[...this.occupancySensors].map((id) => {
        const on = this.hass.states[id]?.state === "on";
        return this._row(
          id,
          "mdi:motion-sensor",
          [localize("detail.sensors.occupancy", l), occupancyNote].filter(Boolean).join(" · "),
          this._binaryValue(id, "detail.sensors.occupied", "detail.sensors.free"),
          on ? "var(--rs-ok)" : "",
        );
      })}
    `;
  }

  /** The humidity limits and the devices RoomMind runs past them (#518, #526). */
  private _renderHumidityRows() {
    if (!this.humiditySensor || (this.humidityMax == null && this.humidityMin == null)) {
      return nothing;
    }
    const l = this.hass.language;
    const live = this.live;
    const range = [
      this.humidityMax != null
        ? localize("sensors.humidity_range_high", l, { value: this.humidityMax })
        : "",
      this.humidityMin != null
        ? localize("sensors.humidity_range_low", l, { value: this.humidityMin })
        : "",
    ].filter(Boolean);
    const past = live?.humidity_high ? "high" : live?.humidity_low ? "low" : null;
    const running = localize("sensors.ventilation_running_humidity", l);
    return html`
      <rs-list-row
        clickable
        chevron
        icon="mdi:water-sync"
        .iconColor=${past ? "var(--rs-warn)" : ""}
        .heading=${localize("detail.sensors.humidity_control", l)}
        .secondary=${range.join(" · ")}
        .value=${localize(
          past === "high"
            ? "sensors.humidity_too_high"
            : past === "low"
              ? "sensors.humidity_too_low"
              : "sensors.humidity_in_range",
          l,
        )}
        @row-click=${this._fireEdit}
      ></rs-list-row>
      ${
        this.dehumidifierEntity && this.humidityMax != null
          ? this._row(
              this.dehumidifierEntity,
              "mdi:water-minus",
              [localize("detail.sensors.dehumidifier", l), live?.dehumidifier_active ? running : ""]
                .filter(Boolean)
                .join(" · "),
              this._onOffValue(this.dehumidifierEntity),
              live?.dehumidifier_active ? "var(--rs-ok)" : "",
            )
          : nothing
      }
      ${
        this.humidifierEntity && this.humidityMin != null
          ? this._row(
              this.humidifierEntity,
              "mdi:water-plus",
              [localize("detail.sensors.humidifier", l), live?.humidifier_active ? running : ""]
                .filter(Boolean)
                .join(" · "),
              this._onOffValue(this.humidifierEntity),
              live?.humidifier_active ? "var(--rs-ok)" : "",
            )
          : nothing
      }
    `;
  }

  /** CO2, VOC and the ventilation entity (#267); a humidity limit runs it too (#526). */
  private _renderAirRows() {
    const l = this.hass.language;
    const reason = this.live?.air_quality_bad ? this.live.air_quality_reason : null;
    const vocNote = this.vocThreshold == null ? localize("sensors.voc_not_judged", l) : "";
    return html`
      ${
        this.co2Sensor
          ? this._row(
              this.co2Sensor,
              "mdi:molecule-co2",
              [
                localize("detail.sensors.co2", l),
                reason === "co2" ? localize("sensors.air_bad", l) : "",
              ]
                .filter(Boolean)
                .join(" · "),
              this._numberValue(this.co2Sensor),
              reason === "co2" ? "var(--rs-warn)" : "",
            )
          : nothing
      }
      ${
        this.vocSensor
          ? this._row(
              this.vocSensor,
              "mdi:air-filter",
              [
                localize("detail.sensors.voc", l),
                reason === "voc" ? localize("sensors.air_bad", l) : vocNote,
              ]
                .filter(Boolean)
                .join(" · "),
              this._numberValue(this.vocSensor),
              reason === "voc" ? "var(--rs-warn)" : "",
            )
          : nothing
      }
      ${
        this.ventilationEntity && (this.co2Sensor || this.vocSensor || this._ventsForHumidity)
          ? this._row(
              this.ventilationEntity,
              "mdi:fan",
              [
                localize("detail.sensors.ventilation", l),
                this.live?.ventilation_active
                  ? localize(
                      this.live.humidity_ventilate && !this.live.air_quality_bad
                        ? "sensors.ventilation_running_humidity"
                        : "sensors.ventilation_running",
                      l,
                    )
                  : "",
              ]
                .filter(Boolean)
                .join(" · "),
              this._onOffValue(this.ventilationEntity),
              this.live?.ventilation_active ? "var(--rs-ok)" : "",
            )
          : nothing
      }
    `;
  }

  /** The upper humidity limit also runs the ventilation (#526). */
  private get _ventsForHumidity(): boolean {
    return !!this.humiditySensor && this.humidityMax != null;
  }

  /** The room fan: when it runs (only shown where the room can heat and cool) and whether RoomMind runs it now. */
  private _renderRoomFanRow() {
    const l = this.hass.language;
    const active = !!this.live?.room_fan_active;
    const when = ROOM_FAN_MODES.find((m) => m.value === this.roomFanMode) ?? ROOM_FAN_MODES[2];
    return this._row(
      this.roomFanEntity,
      "mdi:ceiling-fan",
      [
        localize("detail.sensors.room_fan", l),
        this.roomFanChoice || this.roomFanMode !== "both" ? localize(when.key, l) : "",
        active ? localize("sensors.room_fan_running", l) : "",
      ]
        .filter(Boolean)
        .join(" · "),
      this._onOffValue(this.roomFanEntity),
      active ? "var(--rs-ok)" : "",
    );
  }

  /** Sun sensor with what RoomMind makes of it: learning its scale, or the forecast while it has no reading. */
  private _renderSunRow() {
    const l = this.hass.language;
    const state = this.live?.solar_sensor?.state;
    const note =
      state === "learning"
        ? localize("sensors.sun_learning", l)
        : state === "unavailable"
          ? localize("sensors.sun_fallback", l)
          : "";
    return this._row(
      this.solarSensor,
      "mdi:white-balance-sunny",
      [localize("detail.sensors.sun", l), note].filter(Boolean).join(" · "),
      this._numberValue(this.solarSensor),
    );
  }

  private _row(entityId: string, icon: string, secondary: string, value: string, color = "") {
    const name =
      (this.hass.states[entityId]?.attributes?.friendly_name as string | undefined) || entityId;
    return html`<rs-list-row
      clickable
      chevron
      .icon=${icon}
      .iconColor=${color}
      icon-label=${localize("detail.more_info", this.hass.language)}
      .heading=${name}
      .secondary=${secondary}
      .value=${value}
      @row-click=${this._fireEdit}
      @icon-click=${() => openEntityInfo(this, entityId)}
    ></rs-list-row>`;
  }

  /** Reading of a temperature sensor or climate entity, already in Home Assistant's unit. */
  private _tempValue(entityId: string): string {
    const st = this.hass.states[entityId];
    const raw = entityId.startsWith("climate.") ? st?.attributes?.current_temperature : st?.state;
    const num = Number(raw);
    if (raw == null || raw === "" || !Number.isFinite(num)) {
      return st ? localize("detail.devices.unavailable", this.hass.language) : "";
    }
    return `${formatNumber(num, this.hass, 1)}\u00a0${tempUnit(this.hass)}`;
  }

  private _humidityValue(entityId: string): string {
    const st = this.hass.states[entityId];
    const num = Number(st?.state);
    if (st?.state != null && st.state !== "" && Number.isFinite(num))
      return formatPercent(num, this.hass);
    return st ? localize("detail.devices.unavailable", this.hass.language) : "";
  }

  /** A CO2/VOC reading with the sensor's own unit. */
  private _numberValue(entityId: string): string {
    const st = this.hass.states[entityId];
    const num = Number(st?.state);
    if (st?.state == null || st.state === "" || !Number.isFinite(num)) {
      return st ? localize("detail.devices.unavailable", this.hass.language) : "";
    }
    const unit = st.attributes?.unit_of_measurement as string | undefined;
    return [formatNumber(num, this.hass, 0, Math.abs(num) < 10 ? 2 : 0), unit]
      .filter(Boolean)
      .join("\u00a0");
  }

  private _onOffValue(entityId: string): string {
    const state = this.hass.states[entityId]?.state;
    if (state === "on") return localize("detail.on", this.hass.language);
    if (state === "off") return localize("detail.off", this.hass.language);
    return localize("detail.devices.unavailable", this.hass.language);
  }

  private _binaryValue(
    entityId: string,
    onKey: "detail.sensors.open" | "detail.sensors.occupied",
    offKey: "detail.sensors.closed" | "detail.sensors.free",
  ): string {
    const state = this.hass.states[entityId]?.state;
    if (state === "on") return localize(onKey, this.hass.language);
    if (state === "off") return localize(offKey, this.hass.language);
    return localize("detail.devices.unavailable", this.hass.language);
  }

  private _fireEdit(e: Event) {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent("edit-click", { bubbles: true, composed: true }));
  }

  // ─── Edit mode ───

  /** The pressed row or button is gone after an add or remove: keep the focus in its section. */
  protected updated(changed: PropertyValues): void {
    if (changed.has("_pickerFor") && changed.get("_pickerFor") !== undefined) {
      this._focusPicker(changed.get("_pickerFor") as SensorKind | null);
    }
    if (!this._focusKind || !this.editing) return;
    const lists = [
      "temperatureSensor",
      "humiditySensor",
      "occupancySensors",
      "windowSensors",
      "co2Sensor",
      "vocSensor",
      "ventilationEntity",
      "dehumidifierEntity",
      "humidifierEntity",
      "roomFanEntity",
      "solarSensor",
    ];
    if (!lists.some((p) => changed.has(p))) return;
    const section = this.renderRoot.querySelector(`section[data-kind="${this._focusKind}"]`);
    this._focusKind = null;
    const target = section?.querySelector<HTMLElement & { updateComplete?: Promise<unknown> }>(
      "rs-list-row[clickable], rs-icon-button",
    );
    void target?.updateComplete?.then(() => target.focus());
  }

  /** Entities a kind accepts: the area candidates and the picker use the same rule. */
  private _accepts(kind: SensorKind, entityId: string): boolean {
    const attrs = this.hass.states[entityId]?.attributes ?? {};
    const domain = entityId.split(".")[0];
    const dc = attrs.device_class as string | undefined;
    switch (kind) {
      case "temp":
        return (
          (domain === "sensor" && dc === "temperature") ||
          (domain === "climate" && attrs.current_temperature != null) ||
          (domain === "input_number" && attrs.unit_of_measurement !== "%")
        );
      case "humidity":
        return (
          (domain === "sensor" && dc === "humidity") ||
          (domain === "input_number" && attrs.unit_of_measurement === "%")
        );
      case "occupancy":
        return (
          (domain === "binary_sensor" && OCCUPANCY_CLASSES.includes(dc ?? "")) ||
          domain === "input_boolean"
        );
      case "window":
        return domain === "binary_sensor" && WINDOW_CLASSES.includes(dc ?? "");
      case "co2":
        return domain === "sensor" && dc === "carbon_dioxide";
      case "voc":
        return (
          domain === "sensor" && (VOC_CLASSES.includes(dc ?? "") || (!dc && /voc/i.test(entityId)))
        );
      case "ventilation":
      case "room_fan":
        return VENTILATION_DOMAINS.includes(domain);
      // A humidifier entity's device class tells its direction; plugs and helpers fit both
      case "dehumidifier":
        return HUMIDITY_DEVICE_DOMAINS.includes(domain) && dc !== "humidifier";
      case "humidifier":
        return HUMIDITY_DEVICE_DOMAINS.includes(domain) && dc !== "dehumidifier";
      case "sun":
        return domain === "sensor" && sunKind(attrs) !== null;
    }
  }

  private _single(kind: SingleKind): string {
    return {
      temp: this.temperatureSensor,
      humidity: this.humiditySensor,
      co2: this.co2Sensor,
      voc: this.vocSensor,
      ventilation: this.ventilationEntity,
      dehumidifier: this.dehumidifierEntity,
      humidifier: this.humidifierEntity,
      room_fan: this.roomFanEntity,
      sun: this.solarSensor,
    }[kind];
  }

  private _assigned(kind: SensorKind): string[] {
    if (kind === "occupancy" || kind === "window") {
      return [...(kind === "occupancy" ? this.occupancySensors : this.windowSensors)];
    }
    const id = this._single(kind);
    return id ? [id] : [];
  }

  private _renderEditMode() {
    const areaIds = getEntitiesForArea(this.area.area_id, this.hass?.entities, this.hass?.devices)
      .map((e) => e.entity_id)
      .filter((id) => !id.substring(id.indexOf(".") + 1).startsWith("roommind_"));
    this._areaIds = new Set(areaIds);
    // Candidates as before: input_number helpers only through the picker. Climate devices
    // measure next to the radiator or at the air inlet: pickable, but never suggested
    const inArea = (kind: SensorKind) =>
      this.hass?.states
        ? areaIds.filter(
            (id) =>
              !id.startsWith("input_number.") &&
              !id.startsWith("climate.") &&
              ((kind !== "ventilation" && kind !== "room_fan") || id.startsWith("fan.")) &&
              ((kind !== "dehumidifier" && kind !== "humidifier") ||
                id.startsWith("humidifier.")) &&
              (kind !== "sun" || sunKind(this.hass.states[id]?.attributes ?? {}) !== "percent") &&
              this._accepts(kind, id),
          )
        : [];
    const l = this.hass.language;

    return html`
      ${this._renderKind("temp", inArea("temp"), nothing, this._renderTempNote(l))}
      ${this._renderKind("humidity", inArea("humidity"), nothing)}
      ${
        this.outdoor
          ? nothing
          : html`${this._renderHumidityControl(l, inArea)}
            ${this._renderKind("window", inArea("window"), this._renderWindowSettings(l))}
            ${this._renderKind("occupancy", inArea("occupancy"), this._renderOccupancySettings(l))}
            ${this._renderKind("co2", inArea("co2"), this._renderCo2Settings(l))}
            ${this._renderKind("voc", inArea("voc"), this._renderVocSettings(l))}
            ${
              this.co2Sensor || this.vocSensor || this.ventilationEntity || this._ventsForHumidity
                ? this._renderKind(
                    "ventilation",
                    inArea("ventilation"),
                    nothing,
                    html`<p class="note">${localize("sensors.ventilation_note", l)}</p>
                      ${
                        this._ventsForHumidity
                          ? html`<p class="note">
                              ${localize("sensors.ventilation_humidity_note", l)}
                            </p>`
                          : nothing
                      }`,
                  )
                : nothing
            }
            ${this._renderKind(
              "room_fan",
              inArea("room_fan"),
              this._renderRoomFanSettings(l),
              html`<p class="note">${localize("sensors.room_fan_note", l)}</p>`,
            )}
            ${this._renderKind("sun", inArea("sun"), nothing, this._renderSunNote(l))}`
      }
    `;
  }

  /** Opened: focus the picker; closed with its button: back to the row that opened it. */
  private _focusPicker(previous: SensorKind | null) {
    type Focusable = HTMLElement & { updateComplete?: Promise<unknown>; open?: () => void };
    const kind = this._pickerFor ?? previous;
    if (!kind || this._focusKind) return;
    const section = this.renderRoot.querySelector(`section[data-kind="${kind}"]`);
    const target = section?.querySelector<Focusable>(
      this._pickerFor ? "ha-entity-picker" : "rs-list-row[variant=primary]",
    );
    // HA's picker opens its search list itself; older releases only take the focus
    void target?.updateComplete?.then(() =>
      typeof target.open === "function" ? target.open() : target.focus(),
    );
  }

  private _kindMeta(kind: SensorKind) {
    switch (kind) {
      case "temp":
        return {
          icon: "mdi:thermometer",
          title: "detail.sensors.temperature",
          info: "sensors.temp_info",
        } as const;
      case "humidity":
        return {
          icon: "mdi:water-percent",
          title: "detail.sensors.humidity",
          info: "sensors.humidity_info",
        } as const;
      case "window":
        return {
          icon: "mdi:window-open-variant",
          title: "detail.sensors.window",
          info: "sensors.window_info",
        } as const;
      case "occupancy":
        return {
          icon: "mdi:motion-sensor",
          title: "detail.sensors.occupancy",
          info: "sensors.occupancy_info",
        } as const;
      case "co2":
        return {
          icon: "mdi:molecule-co2",
          title: "detail.sensors.co2",
          info: "sensors.co2_info",
        } as const;
      case "voc":
        return {
          icon: "mdi:air-filter",
          title: "detail.sensors.voc",
          info: "sensors.voc_info",
        } as const;
      case "ventilation":
        return {
          icon: "mdi:fan",
          title: "detail.sensors.ventilation",
          info: "sensors.ventilation_info",
        } as const;
      case "dehumidifier":
        return {
          icon: "mdi:water-minus",
          title: "detail.sensors.dehumidifier",
          info: "sensors.dehumidifier_info",
        } as const;
      case "humidifier":
        return {
          icon: "mdi:water-plus",
          title: "detail.sensors.humidifier",
          info: "sensors.humidifier_info",
        } as const;
      case "room_fan":
        return {
          icon: "mdi:ceiling-fan",
          title: "detail.sensors.room_fan",
          info: "sensors.room_fan_info",
        } as const;
      case "sun":
        return {
          icon: "mdi:white-balance-sunny",
          title: "detail.sensors.sun",
          info: "sensors.sun_info",
        } as const;
    }
  }

  private _renderKind(
    kind: SensorKind,
    areaCandidates: string[],
    settings: unknown,
    note: unknown = nothing,
  ) {
    const l = this.hass.language;
    const meta = this._kindMeta(kind);
    const assigned = this._assigned(kind);
    const single = kind !== "occupancy" && kind !== "window";
    const suggestions = areaCandidates.filter((id) => !assigned.includes(id));
    return html`<section class="group" data-kind=${kind}>
      <h4 class="group-title">
        <ha-icon .icon=${meta.icon} aria-hidden="true"></ha-icon>
        ${localize(meta.title, l)}
        <rs-info-icon .text=${localize(meta.info, l)}></rs-info-icon>
      </h4>
      ${note}
      <div class="rows">
        ${assigned.map((id) => this._renderAssigned(kind, id, this._areaIds.has(id)))}
        ${
          !assigned.length && kind !== "temp"
            ? html`<p class="note">${localize(EMPTY_KEYS[kind] ?? "sensors.none_assigned", l)}</p>`
            : nothing
        }
        ${suggestions.map(
          (id) =>
            html`<rs-list-row
              clickable
              plain-icon
              icon="mdi:plus"
              .heading=${this._entityName(id)}
              .secondary=${localize(
                single && assigned.length ? "sensors.use_instead" : "detail.devices.add_suggestion",
                l,
              )}
              .value=${this._kindValue(kind, id)}
              @row-click=${() => this._add(kind, id)}
            ></rs-list-row>`,
        )}
        ${this._renderPicker(kind)}
      </div>
      ${settings}
    </section>`;
  }

  private _renderAssigned(kind: SensorKind, entityId: string, inArea: boolean) {
    const l = this.hass.language;
    const name = this._entityName(entityId);
    const on = this.hass.states[entityId]?.state === "on";
    const color =
      kind === "window" && on ? "var(--rs-warn)" : kind === "occupancy" && on ? "var(--rs-ok)" : "";
    const icon =
      kind === "window"
        ? on
          ? "mdi:window-open-variant"
          : "mdi:window-closed-variant"
        : this._kindMeta(kind).icon;
    return html`<rs-list-row
      single-line
      .icon=${icon}
      .iconColor=${color}
      icon-label=${localize("detail.more_info", l)}
      .heading=${name}
      .secondary=${[
        entityId,
        kind === "temp" && entityId.startsWith("climate.")
          ? localize("sensors.device_sensor", l)
          : "",
        inArea ? "" : localize("devices.other_area", l),
      ]
        .filter(Boolean)
        .join(" · ")}
      .value=${this._kindValue(kind, entityId)}
      @icon-click=${() => openEntityInfo(this, entityId)}
    >
      <rs-icon-button
        slot="end"
        size="sm"
        icon="mdi:close"
        .label=${localize("common.remove_named", l, { name })}
        @click=${() => this._remove(kind, entityId)}
      ></rs-icon-button>
    </rs-list-row>`;
  }

  private _renderPicker(kind: SensorKind) {
    const l = this.hass.language;
    const label = localize(
      this._assigned(kind).length ? "sensors.choose_other" : "sensors.choose",
      l,
    );
    if (this._pickerFor !== kind) {
      return html`<rs-list-row
        clickable
        plain-icon
        variant="primary"
        icon="mdi:magnify"
        .heading=${label}
        @row-click=${() => {
          this._pickerFor = kind;
        }}
      ></rs-list-row>`;
    }
    const domains = {
      temp: ["sensor", "climate", "input_number"],
      humidity: ["sensor", "input_number"],
      occupancy: ["binary_sensor", "input_boolean"],
      window: ["binary_sensor"],
      co2: ["sensor"],
      voc: ["sensor"],
      ventilation: VENTILATION_DOMAINS,
      dehumidifier: HUMIDITY_DEVICE_DOMAINS,
      humidifier: HUMIDITY_DEVICE_DOMAINS,
      room_fan: VENTILATION_DOMAINS,
      sun: ["sensor"],
    }[kind];
    return html`<div class="picker">
      <ha-entity-picker
        .hass=${this.hass}
        .includeDomains=${domains}
        .entityFilter=${(e: { entity_id: string }) =>
          !e.entity_id.substring(e.entity_id.indexOf(".") + 1).startsWith("roommind_") &&
          !this._assigned(kind).includes(e.entity_id) &&
          this._accepts(kind, e.entity_id)}
        .value=${""}
        .autofocus=${true}
        .label=${label}
        @value-changed=${(e: CustomEvent) => {
          const id = e.detail?.value as string;
          (e.target as HTMLElement & { value: string }).value = "";
          if (id) this._add(kind, id);
        }}
      ></ha-entity-picker>
      <rs-icon-button
        size="sm"
        icon="mdi:close"
        .label=${localize("common.close", l)}
        @click=${() => {
          this._pickerFor = null;
        }}
      ></rs-icon-button>
    </div>`;
  }

  private _kindValue(kind: SensorKind, entityId: string): string {
    if (kind === "temp") return this._tempValue(entityId);
    if (kind === "humidity") return this._humidityValue(entityId);
    if (kind === "co2" || kind === "voc" || kind === "sun") return this._numberValue(entityId);
    if (
      kind === "ventilation" ||
      kind === "dehumidifier" ||
      kind === "humidifier" ||
      kind === "room_fan"
    ) {
      return this._onOffValue(entityId);
    }
    return kind === "window"
      ? this._binaryValue(entityId, "detail.sensors.open", "detail.sensors.closed")
      : this._binaryValue(entityId, "detail.sensors.occupied", "detail.sensors.free");
  }

  private _entityName(entityId: string): string {
    return (
      (this.hass.states[entityId]?.attributes?.friendly_name as string | undefined) || entityId
    );
  }

  private _renderTempNote(l: string) {
    const key = this.outdoor
      ? "sensors.outdoor_note"
      : !this.temperatureSensor
        ? "detail.sensors.no_temperature"
        : this.temperatureSensor.startsWith("climate.")
          ? "sensors.device_sensor_note"
          : "sensors.full_control_note";
    return html`<p class="note">${localize(key, l)}</p>`;
  }

  /** What the chosen sun sensor measures, and that the forecast stays in use until its scale is learned. */
  private _renderSunNote(l: string) {
    if (!this.solarSensor) return nothing;
    const kind = sunKind(this.hass.states[this.solarSensor]?.attributes ?? {});
    const lines = [
      localize(kind ? `sensors.sun_kind_${kind}` : "sensors.sun_kind_unsupported", l),
      kind && [undefined, "learning"].includes(this.live?.solar_sensor?.state)
        ? localize("sensors.sun_learning_note", l)
        : "",
    ].filter(Boolean);
    return html`<p class="note">${lines.join(" ")}</p>`;
  }

  /** Heating, cooling or both; only where the room can do both, else the fan simply follows what it does. */
  private _renderRoomFanSettings(l: string) {
    // A choice left from before the room lost one direction stays visible, or the fan would never run
    if (!this.roomFanEntity || (!this.roomFanChoice && this.roomFanMode === "both")) return nothing;
    return html`<rs-field
      .label=${localize("sensors.room_fan_when", l)}
      .info=${localize("sensors.room_fan_when_info", l)}
    >
      <rs-segmented
        wrap
        .label=${localize("sensors.room_fan_when", l)}
        .options=${ROOM_FAN_MODES.map((m) => ({ value: m.value, label: localize(m.key, l) }))}
        .value=${this.roomFanMode}
        @value-changed=${(e: CustomEvent<{ value: string }>) =>
          this._fireSensorChanged("room_fan_mode", e.detail.value)}
      ></rs-segmented>
    </rs-field>`;
  }

  private _renderWindowSettings(l: string) {
    if (this.windowSensors.size === 0) return nothing;
    return html`
      <div class="pair">
        <rs-number-field
          .label=${localize("devices.window_open_delay", l)}
          .info=${localize("sensors.window_open_delay_info", l)}
          suffix="s"
          .min=${0}
          .value=${this.windowOpenDelay}
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._fireSensorChanged("window_open_delay", e.detail.value)}
        ></rs-number-field>
        <rs-number-field
          .label=${localize("devices.window_close_delay", l)}
          .info=${localize("sensors.window_close_delay_info", l)}
          suffix="s"
          .min=${0}
          .value=${this.windowCloseDelay}
          @value-changed=${(e: CustomEvent<{ value: number }>) =>
            this._fireSensorChanged("window_close_delay", e.detail.value)}
        ></rs-number-field>
      </div>
      ${
        this.heatingSystemType === "underfloor" && this.windowOpenDelay < 300
          ? html`<p class="note warn">
              <ha-icon icon="mdi:information-outline" aria-hidden="true"></ha-icon>
              <span>${localize("devices.underfloor_delay_hint", l)}</span>
            </p>`
          : nothing
      }
    `;
  }

  private _renderOccupancySettings(l: string) {
    if (this.occupancySensors.size === 0) return nothing;
    return html`
      <rs-list-row
        switch
        wrap
        .heading=${localize("devices.occupancy_eco", l)}
        .checked=${this.occupancyEcoEnabled}
        @toggle-changed=${(e: CustomEvent<boolean>) =>
          this._fireSensorChanged("occupancy_eco_enabled", e.detail)}
      >
        <rs-info-icon slot="end" .text=${localize("sensors.occupancy_eco_info", l)}></rs-info-icon>
      </rs-list-row>
      ${
        this.occupancyEcoEnabled
          ? html`<rs-number-field
              .label=${localize("devices.occupancy_eco_delay", l)}
              .info=${localize("sensors.occupancy_eco_delay_info", l)}
              suffix="min"
              .min=${MIN_OCCUPANCY_ECO_DELAY}
              .max=${240}
              .value=${this.occupancyEcoDelay}
              @value-changed=${(e: CustomEvent<{ value: number }>) =>
                this._fireSensorChanged("occupancy_eco_delay", e.detail.value)}
            ></rs-number-field>`
          : nothing
      }
    `;
  }

  /**
   * Humidity limits (#518, #526): one switch per direction, its limit and its device. The
   * ventilation group further down runs for the upper limit too.
   */
  private _renderHumidityControl(l: string, inArea: (kind: SensorKind) => string[]) {
    if (!this.humiditySensor) return nothing;
    const high = this.humidityMax != null;
    const low = this.humidityMin != null;
    return html`<section class="group" data-kind="humidity_control">
        <h4 class="group-title">
          <ha-icon icon="mdi:water-sync" aria-hidden="true"></ha-icon>
          ${localize("detail.sensors.humidity_control", l)}
          <rs-info-icon .text=${localize("sensors.humidity_control_info", l)}></rs-info-icon>
        </h4>
        <rs-list-row
          switch
          wrap
          .heading=${localize("sensors.humidity_lower_high", l)}
          .checked=${high}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fireSensorChanged(
              "humidity_max",
              e.detail
                ? Math.min(
                    MAX_HUMIDITY_MAX,
                    Math.max(DEFAULT_HUMIDITY_MAX, (this.humidityMin ?? 0) + HUMIDITY_LIMIT_GAP),
                  )
                : null,
            )}
        >
          <rs-info-icon
            slot="end"
            .text=${localize("sensors.humidity_lower_high_info", l)}
          ></rs-info-icon>
        </rs-list-row>
        ${
          high
            ? html`<rs-number-field
                .label=${localize("sensors.humidity_max", l)}
                .info=${localize("sensors.humidity_max_info", l)}
                suffix="%"
                .min=${Math.max(MIN_HUMIDITY_MAX, (this.humidityMin ?? 0) + HUMIDITY_LIMIT_GAP)}
                .max=${MAX_HUMIDITY_MAX}
                .value=${this.humidityMax}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._fireSensorChanged("humidity_max", e.detail.value)}
              ></rs-number-field>`
            : nothing
        }
        ${
          high && this.acDryChoice
            ? html`<rs-list-row
                switch
                wrap
                .heading=${localize("sensors.ac_dry", l)}
                .checked=${this.acDryEnabled}
                @toggle-changed=${(e: CustomEvent<boolean>) =>
                  this._fireSensorChanged("ac_dry_enabled", e.detail)}
              >
                <rs-info-icon slot="end" .text=${localize("sensors.ac_dry_info", l)}></rs-info-icon>
              </rs-list-row>`
            : nothing
        }
        <rs-list-row
          switch
          wrap
          .heading=${localize("sensors.humidity_raise_low", l)}
          .checked=${low}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fireSensorChanged(
              "humidity_min",
              e.detail
                ? Math.max(
                    MIN_HUMIDITY_MIN,
                    Math.min(DEFAULT_HUMIDITY_MIN, (this.humidityMax ?? 100) - HUMIDITY_LIMIT_GAP),
                  )
                : null,
            )}
        >
          <rs-info-icon
            slot="end"
            .text=${localize("sensors.humidity_raise_low_info", l)}
          ></rs-info-icon>
        </rs-list-row>
        ${
          low
            ? html`<rs-number-field
                .label=${localize("sensors.humidity_min", l)}
                .info=${localize("sensors.humidity_min_info", l)}
                suffix="%"
                .min=${MIN_HUMIDITY_MIN}
                .max=${Math.min(MAX_HUMIDITY_MIN, (this.humidityMax ?? 100) - HUMIDITY_LIMIT_GAP)}
                .value=${this.humidityMin}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._fireSensorChanged("humidity_min", e.detail.value)}
              ></rs-number-field>`
            : nothing
        }
        ${
          high || low
            ? html`<p class="note">${localize("sensors.humidity_device_note", l)}</p>`
            : nothing
        }
      </section>
      ${
        high || this.dehumidifierEntity
          ? this._renderKind("dehumidifier", inArea("dehumidifier"), nothing)
          : nothing
      }
      ${
        low || this.humidifierEntity
          ? this._renderKind("humidifier", inArea("humidifier"), nothing)
          : nothing
      }`;
  }

  /** Occupancy and window hold a list, every other kind one entity (a new one replaces it). */
  private _add(kind: SensorKind, entityId: string) {
    this._pickerFor = null;
    this._focusKind = kind;
    if (kind === "occupancy") this._onOccupancyToggle(entityId, true);
    else if (kind === "window") this._onWindowToggle(entityId, true);
    else this._onSensorSelected(entityId, kind);
  }

  private _remove(kind: SensorKind, entityId: string) {
    this._focusKind = kind;
    if (kind === "occupancy") this._onOccupancyToggle(entityId, false);
    else if (kind === "window") this._onWindowToggle(entityId, false);
    else this._onSensorSelected("", kind);
  }

  private _onSensorSelected(entityId: string, kind: SingleKind) {
    const key = SINGLE_KEYS[kind];
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key, value: entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onOccupancyToggle(entityId: string, checked: boolean) {
    const next = new Set(this.occupancySensors);
    if (checked) next.add(entityId);
    else next.delete(entityId);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "occupancy_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindowToggle(entityId: string, checked: boolean) {
    const next = new Set(this.windowSensors);
    if (checked) next.add(entityId);
    else next.delete(entityId);
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key: "window_sensors", value: [...next] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _renderCo2Settings(l: string) {
    if (!this.co2Sensor) return nothing;
    return html`<rs-number-field
      .label=${localize("sensors.air_threshold", l)}
      .info=${localize("sensors.co2_threshold_info", l)}
      suffix="ppm"
      .min=${MIN_CO2_THRESHOLD}
      .max=${MAX_CO2_THRESHOLD}
      .step=${50}
      .value=${this.co2Threshold}
      @value-changed=${(e: CustomEvent<{ value: number }>) =>
        this._fireSensorChanged("co2_threshold", e.detail.value)}
    ></rs-number-field>`;
  }

  /** In the sensor's own unit: VOC sensors report an index, ppb or µg/m³, no default fits all. */
  private _renderVocSettings(l: string) {
    if (!this.vocSensor) return nothing;
    const unit =
      (this.hass.states[this.vocSensor]?.attributes?.unit_of_measurement as string | undefined) ??
      "";
    return html`<rs-number-field
      .label=${localize("sensors.air_threshold", l)}
      .info=${localize("sensors.voc_threshold_info", l)}
      .hint=${this.vocThreshold == null ? localize("sensors.voc_not_judged", l) : ""}
      .suffix=${unit}
      allow-empty
      .min=${0.1}
      .max=${1000000}
      .step=${0.1}
      .value=${this.vocThreshold}
      @value-changed=${(e: CustomEvent<{ value: number | null }>) =>
        this._fireSensorChanged("voc_threshold", e.detail.value)}
    ></rs-number-field>`;
  }

  private _fireSensorChanged(key: string, value: boolean | number | string | null) {
    this.dispatchEvent(
      new CustomEvent("sensor-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-sensor-section": RsSensorSection;
  }
}

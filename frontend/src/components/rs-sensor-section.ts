import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, HassArea, RoomLiveData } from "../types";
import { getEntitiesForArea } from "../utils/room-state";
import { localize } from "../utils/localize";
import { openEntityInfo } from "../utils/events";
import { tempUnit } from "../utils/temperature";
import { formatMinutes, formatNumber, formatPercent } from "../utils/format";
import { tokens } from "../styles/tokens";
import { inputStyles } from "../styles/input-styles";
import { formStyles } from "../styles/form-styles";
import {
  DEFAULT_CO2_THRESHOLD,
  DEFAULT_OCCUPANCY_ECO_DELAY,
  MAX_CO2_THRESHOLD,
  MIN_CO2_THRESHOLD,
  MIN_OCCUPANCY_ECO_DELAY,
} from "../utils/constants";
import "./shared/rs-field";
import "./shared/rs-number-field";
import "./shared/rs-icon-button";
import "./shared/rs-info-icon";
import "./shared/rs-list-row";

type SensorKind = "temp" | "humidity" | "occupancy" | "window" | "co2" | "voc" | "ventilation";
type SingleKind = "temp" | "humidity" | "co2" | "voc" | "ventilation";

const OCCUPANCY_CLASSES = ["occupancy", "motion", "presence"];
const WINDOW_CLASSES = ["window", "door", "opening"];
// VOC sensors report an index, ppb or µg/m³; ESPHome's SGP4x index comes as aqi or without a class
const VOC_CLASSES = ["volatile_organic_compounds", "volatile_organic_compounds_parts", "aqi"];
const VENTILATION_DOMAINS = ["fan", "switch", "input_boolean"];
const SINGLE_KEYS: Record<SingleKind, string> = {
  temp: "temperature_sensor",
  humidity: "humidity_sensor",
  co2: "co2_sensor",
  voc: "voc_sensor",
  ventilation: "ventilation_entity",
};

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
      ${this.outdoor ? nothing : this._renderAirRows()}
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

  /** CO2, VOC and the ventilation entity (#267). */
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
        this.ventilationEntity && (this.co2Sensor || this.vocSensor)
          ? this._row(
              this.ventilationEntity,
              "mdi:fan",
              [
                localize("detail.sensors.ventilation", l),
                this.live?.ventilation_active ? localize("sensors.ventilation_running", l) : "",
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
        return VENTILATION_DOMAINS.includes(domain);
    }
  }

  private _single(kind: SingleKind): string {
    return {
      temp: this.temperatureSensor,
      humidity: this.humiditySensor,
      co2: this.co2Sensor,
      voc: this.vocSensor,
      ventilation: this.ventilationEntity,
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
              (kind !== "ventilation" || id.startsWith("fan.")) &&
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
          : html`${this._renderKind("window", inArea("window"), this._renderWindowSettings(l))}
            ${this._renderKind("occupancy", inArea("occupancy"), this._renderOccupancySettings(l))}
            ${this._renderKind("co2", inArea("co2"), this._renderCo2Settings(l))}
            ${this._renderKind("voc", inArea("voc"), this._renderVocSettings(l))}
            ${
              this.co2Sensor || this.vocSensor || this.ventilationEntity
                ? this._renderKind(
                    "ventilation",
                    inArea("ventilation"),
                    nothing,
                    html`<p class="note">${localize("sensors.ventilation_note", l)}</p>`,
                  )
                : nothing
            }`
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
            ? html`<p class="note">
                ${localize(kind === "ventilation" ? "sensors.no_ventilation" : "sensors.none_assigned", l)}
              </p>`
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
    if (kind === "co2" || kind === "voc") return this._numberValue(entityId);
    if (kind === "ventilation") return this._onOffValue(entityId);
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

  private _fireSensorChanged(key: string, value: boolean | number | null) {
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

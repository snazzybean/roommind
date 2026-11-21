import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-row";
import "../shared/rs-radio-group";

/** Threshold the manual slider starts from when the automatic one is switched off. */
const DEFAULT_MANUAL_THRESHOLD = 0.5;

/** "12 %" in the user's locale for a share between 0 and 1. */
export function thresholdLabel(share: number, language: string): string {
  return new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 0 }).format(
    share,
  );
}

/** "76 h" per week in the user's locale. */
export function comfortHoursLabel(hours: number, language: string): string {
  return localize("detail.learned.hours_value", language, {
    hours: new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(hours),
  });
}

/**
 * Content of the room's learned occupancy dialog: Area Occupancy Detection as the source of the
 * room's comfort window instead of its schedule (opt-in), the area it reads, and the comfort
 * threshold, automatic or set by hand, with what it gives right now. Fires
 * `learned-schedule-changed` (`{ value: boolean }`), `learned-area-changed` (`{ value: string }`)
 * and `learned-threshold-changed` (`{ value: number | null }`, null = automatic).
 */
@customElement("rs-learned-occupancy")
export class RsLearnedOccupancy extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  /** The room takes its window from Area Occupancy (stored opt-in). */
  @property({ type: Boolean }) public enabled = false;
  /** Area Occupancy area the room reads, empty before one is picked. */
  @property({ type: String }) public areaId = "";
  /** Stored threshold (0..1), null = automatic. */
  @property({ attribute: false }) public threshold: number | null = null;
  /** Area Occupancy Detection is installed (its get_time_priors service exists). */
  @property({ type: Boolean }) public available = false;
  /** Areas Area Occupancy learns. */
  @property({ attribute: false }) public areas: string[] = [];
  /** Threshold in force from the room's live data, null while the schedule applies. */
  @property({ attribute: false }) public liveThreshold: number | null = null;
  /** Comfort hours per week the threshold in force gives, null while the schedule applies. */
  @property({ attribute: false }) public comfortHours: number | null = null;
  /** Occupancy eco with sensors is on, so the window is checked against them. */
  @property({ type: Boolean }) public occupancyEco = false;

  /** Slider position while it is dragged (0..1), null otherwise. */
  @state() private _dragThreshold: number | null = null;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
      }

      .intro,
      .note {
        margin: 0 0 var(--rs-space-4);
        font-size: var(--rs-font-md);
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .label {
        margin: var(--rs-space-4) 0 var(--rs-space-2);
        font-size: var(--rs-font-md);
      }

      .slider-row {
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .slider-row input[type="range"] {
        flex: 1;
        accent-color: var(--primary-color);
      }

      .slider-value {
        min-width: 4ch;
        text-align: end;
        font-size: var(--rs-font-md);
      }

      rs-list-row {
        --rs-list-row-padding: 0;
      }

      .threshold,
      .status {
        margin-top: var(--rs-space-4);
      }
    `,
  ];

  render() {
    const l = this.hass.language;
    return html`
      <p class="intro">${localize("detail.learned.intro", l)}</p>
      ${this.available ? nothing : html`<p class="note">${localize("detail.learned.unavailable", l)}</p>`}
      <rs-list-row
        switch
        wrap
        icon="mdi:account-clock"
        .heading=${localize("detail.learned.use", l)}
        .secondary=${localize("detail.learned.use_sub", l)}
        .checked=${this.enabled}
        .disabled=${!this.available && !this.enabled}
        @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("learned-schedule-changed", e.detail)}
      ></rs-list-row>
      ${this.enabled ? this._renderSettings() : nothing}
    `;
  }

  private _renderSettings() {
    const l = this.hass.language;
    const areas =
      this.areaId && !this.areas.includes(this.areaId) ? [this.areaId, ...this.areas] : this.areas;
    return html`
      <div class="label">${localize("detail.learned.area_label", l)}</div>
      ${
        areas.length
          ? html`<rs-radio-group
              .options=${areas.map((id) => ({ value: id, label: this.hass.areas?.[id]?.name ?? id }))}
              .selected=${this.areaId}
              @selected-changed=${(e: CustomEvent<string>) => {
                e.stopPropagation();
                this._fire("learned-area-changed", e.detail);
              }}
            ></rs-radio-group>`
          : html`<p class="note">${localize("detail.learned.no_areas", l)}</p>`
      }
      <rs-list-row
        class="threshold"
        switch
        wrap
        icon="mdi:auto-fix"
        .heading=${localize("detail.learned.auto_threshold", l)}
        .secondary=${localize("detail.learned.auto_threshold_sub", l)}
        .checked=${this.threshold === null}
        @toggle-changed=${(e: CustomEvent<boolean>) =>
          this._fire("learned-threshold-changed", e.detail ? null : this._manualStart())}
      ></rs-list-row>
      ${this.threshold === null ? nothing : this._renderSlider()}
      <div class="status">
        <rs-list-row
          icon="mdi:percent-outline"
          .heading=${localize("detail.learned.threshold_now", l)}
          .value=${
            this.liveThreshold === null
              ? localize("detail.learned.schedule_applies", l)
              : thresholdLabel(this.liveThreshold, l)
          }
        ></rs-list-row>
        ${
          this.comfortHours === null
            ? nothing
            : html`<rs-list-row
                icon="mdi:sofa"
                .heading=${localize("detail.learned.comfort_hours", l)}
                .value=${comfortHoursLabel(this.comfortHours, l)}
              ></rs-list-row>`
        }
      </div>
      <p class="note">
        ${localize(this.occupancyEco ? "detail.learned.sensors_on" : "detail.learned.sensors_off", l)}
      </p>
    `;
  }

  private _renderSlider() {
    const l = this.hass.language;
    const shown = this._dragThreshold ?? this.threshold ?? DEFAULT_MANUAL_THRESHOLD;
    return html`
      <div class="label" aria-hidden="true">${localize("detail.learned.threshold_label", l)}</div>
      <div class="slider-row">
        <input
          type="range"
          aria-label=${localize("detail.learned.threshold_label", l)}
          min="1"
          max="99"
          step="1"
          .value=${String(Math.round(shown * 100))}
          @input=${(e: Event) => {
            const percent = parseInt((e.target as HTMLInputElement).value, 10);
            this._dragThreshold = isNaN(percent) ? null : percent / 100;
          }}
          @change=${(e: Event) => {
            const percent = parseInt((e.target as HTMLInputElement).value, 10);
            this._dragThreshold = null;
            if (!isNaN(percent)) this._fire("learned-threshold-changed", percent / 100);
          }}
        />
        <span class="slider-value">${thresholdLabel(shown, l)}</span>
      </div>
    `;
  }

  /** The automatic threshold in force is the natural start for a manual one. */
  private _manualStart(): number {
    return this.liveThreshold ?? DEFAULT_MANUAL_THRESHOLD;
  }

  private _fire(name: string, value: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail: { value }, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-learned-occupancy": RsLearnedOccupancy;
  }
}

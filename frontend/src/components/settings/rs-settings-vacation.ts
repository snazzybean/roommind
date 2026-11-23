/**
 * rs-settings-vacation – Vacation mode settings.
 */
import { css, html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-info-icon";
import { numberRow } from "../shared/number-row";

@customElement("rs-settings-vacation")
export class RsSettingsVacation extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ type: Number }) public vacationTemp = 15;
  @property({ type: String }) public vacationUntil = "";
  /** Time picked before a date; used once the date is set. */
  @state() private _time = "00:00";

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("vacation.switch", l)}
          .checked=${this.vacationActive}
          @toggle-changed=${(e: CustomEvent<boolean>) => {
            const active = e.detail;
            this._fire("vacationActive", active);
            if (!active) this._fire("vacationUntil", "");
          }}
        >
          <rs-info-icon slot="end" .text=${localize("vacation.hint", l)}></rs-info-icon>
        </rs-list-row>
      </div>

      ${
        this.vacationActive
          ? html`
              <div class="settings-section">
                <h3 class="section-title">${localize("vacation.section_during", l)}</h3>
                ${numberRow({
                  hass: this.hass,
                  kind: "temperature",
                  label: localize("vacation.setback_temp", l),
                  min: 5,
                  max: 25,
                  value: this.vacationTemp,
                  onChange: (v) => this._fire("vacationTemp", v),
                })}
                <div class="end">${this._renderEndDate()}</div>
              </div>
            `
          : nothing
      }
    `;
  }

  /**
   * Home Assistant's own date and time fields show the date in HA's language and format; a plain
   * datetime-local field follows the browser instead. The field stays as fallback for releases
   * that do not define ha-selector in the panel.
   */
  private _renderEndDate() {
    const l = this.hass.language;
    if (customElements.get("ha-selector")) {
      const [date, time] = this.vacationUntil ? this.vacationUntil.split("T") : ["", ""];
      return html`<div class="end-date">
        <ha-selector
          class="date"
          .hass=${this.hass}
          .selector=${{ date: {} }}
          .label=${localize("vacation.end_day", l)}
          .required=${false}
          .value=${date}
          @value-changed=${(e: CustomEvent<{ value?: string }>) => {
            e.stopPropagation();
            this._setEnd(e.detail.value ?? "", time || this._time);
          }}
        ></ha-selector>
        <ha-selector
          class="time"
          .hass=${this.hass}
          .selector=${{ time: { no_second: true } }}
          .label=${localize("vacation.end_time", l)}
          .required=${false}
          .value=${time || this._time}
          @value-changed=${(e: CustomEvent<{ value?: string }>) => {
            e.stopPropagation();
            this._time = (e.detail.value ?? "").slice(0, 5) || "00:00";
            if (date) this._setEnd(date, this._time);
          }}
        ></ha-selector>
      </div>`;
    }
    return html`<label class="field-label" for="vacation-until"
        >${localize("vacation.end_date", l)}</label
      >
      <ha-textfield
        id="vacation-until"
        .value=${this.vacationUntil}
        aria-label=${localize("vacation.end_date", l)}
        type="datetime-local"
        @change=${(e: Event) => this._fire("vacationUntil", (e.target as HTMLInputElement).value)}
      ></ha-textfield>`;
  }

  private _setEnd(date: string, time: string) {
    const until = date ? `${date}T${time.slice(0, 5) || "00:00"}` : "";
    if (until !== this.vacationUntil) this._fire("vacationUntil", until);
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      /* the time field carries its label above, the date field inside: align their bottoms */
      .end {
        margin-top: var(--rs-space-3);
      }
      .end-date {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: var(--rs-space-4) var(--rs-space-2);
      }
      .end-date .date {
        flex: 0 1 240px;
        min-width: 0;
        /* ha-input keeps 8 px for a hint it does not show */
        margin-bottom: -8px;
      }
      .end-date .time {
        flex: none;
        width: auto;
      }
      .end .field-label {
        margin: 0;
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-vacation": RsSettingsVacation;
  }
}

import { css, html } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { localize } from "../../utils/localize";

/**
 * Help texts of the room's edit dialogs (the `info` slot of `rs-edit-dialog`). Static content,
 * kept out of the room page so it stays about state and layout. Styles (`.yaml-block`,
 * `.helper-link`) come from the host: `editDialogHelpStyles`.
 */

export const editDialogHelpStyles = css`
  /* YAML code block for info panels (slotted into edit dialogs) */
  .yaml-block {
    background: var(--code-editor-background-color, rgba(0, 0, 0, 0.35));
    border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.12));
    border-radius: 6px;
    padding: 10px 14px;
    margin: 8px 0;
    font-family: var(--code-font-family, monospace);
    font-size: 12px;
    line-height: 1.6;
    white-space: pre;
    overflow-x: auto;
    color: var(--primary-text-color);
  }
  .yaml-key {
    color: var(--primary-color);
  }
  .yaml-value {
    color: var(--accent-color);
  }

  .helper-link {
    display: inline-block;
    margin-top: 12px;
    color: var(--primary-color);
    font-size: 12px;
    text-decoration: none;
  }

  .helper-link:hover {
    text-decoration: underline;
  }
`;

const CONTROL_DOCS_URL =
  "https://github.com/snazzybean/roommind/blob/main/docs/control-and-devices.md";

export function temperaturesHelp(lang: string) {
  return html`<div slot="info">
    <p><strong>${localize("schedule.help_temps_title", lang)}</strong></p>
    <p>${localize("schedule.help_temps", lang)}</p>
    <ol style="margin: 4px 0 0 0; padding-left: 20px; line-height: 1.8">
      <li>${unsafeHTML(localize("schedule.help_temps_1", lang))}</li>
      <li>${unsafeHTML(localize("schedule.help_temps_2", lang))}</li>
      <li>${unsafeHTML(localize("schedule.help_temps_3", lang))}</li>
      <li>${unsafeHTML(localize("schedule.help_temps_4", lang))}</li>
    </ol>
    <p>${localize("schedule.help_temps_adjust", lang)}</p>
  </div>`;
}

export function priceHelp(lang: string) {
  return html`<div slot="info">
    <p>${localize("detail.price.info", lang)}</p>
  </div>`;
}

export function scheduleHelp(lang: string) {
  return html`<div slot="info">
    <p><strong>${localize("schedule.help_block_title", lang)}</strong></p>
    <p>${unsafeHTML(localize("schedule.help_block", lang))}</p>
    <div class="yaml-block">
      ${unsafeHTML(
        '<span class="yaml-key">schedule</span>:\n' +
          '  <span class="yaml-key">living_room_heating</span>:\n' +
          '    <span class="yaml-key">name</span>: <span class="yaml-value">Living Room Heating</span>\n' +
          '    <span class="yaml-key">monday</span>:\n' +
          '      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>\n' +
          '        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>\n' +
          '        <span class="yaml-key">data</span>:\n' +
          '          <span class="yaml-key">temperature</span>: <span class="yaml-value">23</span>\n' +
          '      - <span class="yaml-key">from</span>: <span class="yaml-value">"17:00:00"</span>\n' +
          '        <span class="yaml-key">to</span>: <span class="yaml-value">"22:00:00"</span>\n' +
          '        <span class="yaml-key">data</span>:\n' +
          '          <span class="yaml-key">temperature</span>: <span class="yaml-value">21.5</span>',
      )}
    </div>
    <p style="margin-top: 8px">${unsafeHTML(localize("schedule.help_block_note", lang))}</p>
    <p style="margin-top: 12px">
      <strong>${localize("schedule.help_split_title", lang)}</strong>
    </p>
    <p>${unsafeHTML(localize("schedule.help_split", lang))}</p>
    <div class="yaml-block">
      ${unsafeHTML(
        '- <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>\n' +
          '  <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>\n' +
          '  <span class="yaml-key">data</span>:\n' +
          '    <span class="yaml-key">heat_temperature</span>: <span class="yaml-value">21</span>\n' +
          '    <span class="yaml-key">cool_temperature</span>: <span class="yaml-value">24</span>',
      )}
    </div>
    <p style="margin-top: 8px">${unsafeHTML(localize("schedule.help_split_note", lang))}</p>
    <p style="margin-top: 12px">
      <strong>${localize("schedule.help_multi_title", lang)}</strong>
    </p>
    <p>${unsafeHTML(localize("schedule.help_multi", lang))}</p>
  </div>`;
}

export function devicesHelp(lang: string) {
  return html`<div slot="info">
    <p>${localize("devices.info.intro", lang)}</p>
    <a class="helper-link" href=${CONTROL_DOCS_URL} target="_blank" rel="noreferrer">
      ${localize("common.learn_more", lang)}
    </a>
  </div>`;
}

const MODES_DOCS_URL = "https://github.com/snazzybean/roommind#full-control-vs-managed-mode";

export function sensorsHelp(lang: string) {
  return html`<div slot="info">
    <p>${localize("sensors.help", lang)}</p>
    <a class="helper-link" href=${MODES_DOCS_URL} target="_blank" rel="noreferrer">
      ${localize("common.learn_more", lang)}
    </a>
  </div>`;
}

export function presenceHelp(lang: string) {
  return html`<div slot="info">
    <b>${localize("presence.room_help_header", lang)}</b><br />
    ${localize("presence.room_help_body", lang)}
    <br /><br />
    <b>${localize("presence.help_ignore_title", lang)}</b><br />
    ${localize("presence.help_ignore_body", lang)}
  </div>`;
}

export function coversHelp(lang: string) {
  return html`<div slot="info">
    <b>${localize("covers.info.selection_title", lang)}</b><br />
    ${localize("covers.info.selection_body", lang)}
    <br /><br />
    <b>${localize("covers.info.schedule_title", lang)}</b><br />
    ${localize("covers.info.schedule_body", lang)}
    <div class="yaml-block">
      ${unsafeHTML(
        '<span class="yaml-key">schedule</span>:\n' +
          '  <span class="yaml-key">cover_evening</span>:\n' +
          '    <span class="yaml-key">name</span>: <span class="yaml-value">Cover Evening</span>\n' +
          '    <span class="yaml-key">monday</span>:\n' +
          '      - <span class="yaml-key">from</span>: <span class="yaml-value">"20:00:00"</span>\n' +
          '        <span class="yaml-key">to</span>: <span class="yaml-value">"24:00:00"</span>\n' +
          '        <span class="yaml-key">data</span>:\n' +
          '          <span class="yaml-key">position</span>: <span class="yaml-value">10</span>',
      )}
    </div>
    <b>${localize("covers.info.solar_title", lang)}</b><br />
    ${localize("covers.info.solar_body", lang)}
    <br /><br />
    <b>${localize("covers.info.night_title", lang)}</b><br />
    ${localize("covers.info.night_body", lang)}
    <br /><br />
    <b>${localize("covers.info.override_title", lang)}</b><br />
    ${localize("covers.info.override_body", lang)}
    <br /><br />
    <b>${localize("covers.info.priority_title", lang)}</b><br />
    ${localize("covers.info.priority_body", lang)}
    <br /><br />
    <b>${localize("covers.info.entities_title", lang)}</b><br />
    ${localize("covers.info.entities_body", lang)}
  </div>`;
}

export function heatSourceHelp(lang: string) {
  return html`<div slot="info">
    <b>${localize("heat_source.help_title", lang)}</b><br />
    ${localize("heat_source.help_body", lang)}
  </div>`;
}

/**
 * Type declarations for Home Assistant built-in web components.
 * These are loaded at runtime via load-ha-elements.ts, not from npm.
 */

declare global {
  interface HTMLElementTagNameMap {
    "ha-card": HTMLElement & { header?: string };
    "ha-button": HTMLElement & { disabled?: boolean; raised?: boolean; outlined?: boolean };
    "ha-icon": HTMLElement & { icon: string };
    "ha-select": HTMLElement & { value?: string; label?: string; naturalMenuWidth?: boolean; fixedMenuPosition?: boolean; options?: Array<{ value: string; label: string }> | string[] };
    "ha-list-item": HTMLElement & { value?: string; selected?: boolean };
    "ha-textfield": HTMLElement & {
      value?: string;
      label?: string;
      type?: string;
      min?: string;
      max?: string;
      step?: string;
      suffix?: string;
    };
    "ha-checkbox": HTMLElement & { checked?: boolean; disabled?: boolean };
    "ha-radio": HTMLElement & { checked?: boolean; disabled?: boolean; name?: string; value?: string };
    "ha-expansion-panel": HTMLElement & { header?: string; outlined?: boolean; expanded?: boolean };
    "ha-entity-picker": HTMLElement & {
      hass?: any;
      value?: string;
      label?: string;
      includeDomains?: string[];
      includeDeviceClasses?: string[];
      entityFilter?: (entity: any) => boolean;
      hideClearIcon?: boolean;
      disabled?: boolean;
    };
    "ha-chart-base": HTMLElement & {
      hass?: any;
      data?: unknown;
      options?: unknown;
      height?: string;
      expandLegend?: boolean;
    };
  }
}

export {};

/**
 * Force-load Home Assistant's built-in web components so custom panels
 * can use <ha-card>, <ha-button>, <ha-select>, <ha-entity-picker>, etc.
 *
 * Technique used by alarmo, scheduler-card, mushroom, and others.
 */
export const loadHaElements = async (): Promise<void> => {
  if (customElements.get("ha-entity-picker")) return;

  // Step 1: Load base HA components via partial-panel-resolver.
  // Guard on ha-selector (not ha-card) because ha-card can be defined by
  // other HA modules without the config/automation route being loaded.
  // We need ha-selector for the entity-picker fallback below.
  if (!customElements.get("ha-selector")) {
    await customElements.whenDefined("partial-panel-resolver");
    const ppr = document.createElement("partial-panel-resolver") as any;
    ppr.hass = {
      panels: [{ url_path: "tmp", component_name: "config" }],
    };
    ppr._updateRoutes();
    await ppr.routerOptions.routes.tmp.load();

    await customElements.whenDefined("ha-panel-config");
    const cpr = document.createElement("ha-panel-config") as any;
    await cpr.routerOptions.routes.automation.load();
  }

  // Step 2: Force-load ha-entity-picker via loadCardHelpers.
  // Works on older HA versions where the entities card editor still imports it.
  if (!customElements.get("ha-entity-picker")) {
    try {
      const helpers = await (window as any).loadCardHelpers();
      const card = await helpers.createCardElement({
        type: "entities",
        entities: [],
      });
      await card.constructor.getConfigElement();
    } catch {
      // May fail in HA 2025.5+ where entities editor was refactored
    }
  }

  // Step 2 fallback: ha-selector lazy-imports ha-selector-entity (which
  // statically imports ha-entity-picker) only when it renders with an
  // entity selector.  Briefly render one offscreen to trigger that chain.
  if (!customElements.get("ha-entity-picker")) {
    try {
      await Promise.race([
        customElements.whenDefined("ha-selector"),
        new Promise<void>((_, rej) =>
          setTimeout(() => rej(new Error("timeout")), 10_000)
        ),
      ]);
      const hass = (document.querySelector("home-assistant") as any)?.hass;
      const offscreen = document.createElement("div");
      offscreen.style.cssText =
        "position:fixed;left:-9999px;opacity:0;pointer-events:none";
      document.body.appendChild(offscreen);
      try {
        const sel = document.createElement("ha-selector") as any;
        sel.hass = hass;
        sel.selector = { entity: {} };
        offscreen.appendChild(sel);
        await Promise.race([
          customElements.whenDefined("ha-entity-picker"),
          new Promise<void>((r) => setTimeout(r, 5000)),
        ]);
      } finally {
        offscreen.remove();
      }
    } catch {
      // ha-entity-picker could not be loaded
    }
  }

  await customElements.whenDefined("ha-card");

  // Step 3: Load ha-date-range-picker (used by rs-analytics).
  if (!customElements.get("ha-date-range-picker")) {
    try {
      const helpers = await (window as any).loadCardHelpers();
      await helpers.createCardElement({
        type: "energy-date-selection",
        entities: [],
      });
      await Promise.race([
        customElements.whenDefined("ha-date-range-picker"),
        new Promise((_, reject) => setTimeout(reject, 5000)),
      ]);
    } catch {
      // ha-date-range-picker not available — fallback handled in component
    }
  }

  // Step 4: Load ha-chart-base (used by rs-analytics).
  // It is part of HA's history/energy modules and NOT loaded by the
  // config panel or card-helpers entities card.  Trigger the import
  // chain via the statistics-graph lovelace card, which depends on it.
  if (!customElements.get("ha-chart-base")) {
    try {
      const helpers = await (window as any).loadCardHelpers();
      await helpers.createCardElement({
        type: "statistics-graph",
        entities: [],
      });
      // Wait up to 5 s for async registration
      await Promise.race([
        customElements.whenDefined("ha-chart-base"),
        new Promise((_, reject) => setTimeout(reject, 5000)),
      ]);
    } catch {
      // ha-chart-base not available – analytics chart will be empty
    }
  }
};

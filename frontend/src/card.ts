/**
 * RoomMind – dashboard card entry point.
 *
 * Bundled on its own into roommind-card.js, which the integration loads on every
 * dashboard. It must not import panel components: both bundles would define the
 * same custom elements and the second one would fail to load.
 */
import { localize, uiLanguage } from "./utils/localize";

interface CustomCardEntry {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
  documentationURL?: string;
}

const w = window as unknown as { customCards?: CustomCardEntry[] };
w.customCards = w.customCards ?? [];
// Getters: HA is not connected yet when this runs, the card picker reads them later.
if (!w.customCards.some((c) => c.type === "roommind-room-card")) {
  w.customCards.push({
    type: "roommind-room-card",
    get name() {
      return localize("roomcard.name", uiLanguage());
    },
    get description() {
      return localize("roomcard.description", uiLanguage());
    },
    preview: true,
    documentationURL: "https://github.com/snazzybean/roommind#dashboard-card",
  });
}

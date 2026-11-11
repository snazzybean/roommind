import { defineConfig, type Plugin } from "vite";
import { resolve } from "path";

// The card is loaded on every dashboard page; ship only the strings it uses.
const CARD_KEY_PREFIXES = [
  "roomcard.",
  "override.",
  "mode.",
  "card.",
  "duration.",
  "hero.",
  "error.",
  "room.climate_control_toggle",
];

function cardLocales(): Plugin {
  return {
    name: "roommind-card-locales",
    enforce: "pre",
    transform(code, id) {
      if (!/[\\/]locales[\\/][a-z]+\.json$/.test(id)) return null;
      const all = JSON.parse(code) as Record<string, string>;
      const kept = Object.fromEntries(
        Object.entries(all).filter(([key]) => CARD_KEY_PREFIXES.some((p) => key.startsWith(p))),
      );
      return { code: JSON.stringify(kept), map: null };
    },
  };
}

export default defineConfig({
  plugins: [cardLocales()],
  build: {
    lib: {
      entry: resolve(__dirname, "src/card.ts"),
      name: "RoomMindCard",
      formats: ["iife"],
      fileName: () => "roommind-card.js",
    },
    outDir: "../custom_components/roommind/frontend",
    emptyOutDir: false,
  },
});

import en from "../locales/en.json";
import de from "../locales/de.json";
import fr from "../locales/fr.json";
import it from "../locales/it.json";

export type TranslationKey = keyof typeof en;

const translations: Record<string, Record<string, string>> = { en, de, fr, it };

/**
 * Look up a translation key for the given language.
 * Falls back to English if the key is missing in the target language.
 * Supports simple {placeholder} interpolation.
 */
export function localize(
  key: TranslationKey,
  language: string,
  params?: Record<string, string | number>,
): string {
  const lang = translations[language] ?? translations[language.split("-")[0]] ?? translations.en;
  let result = lang[key] ?? translations.en[key] ?? key;

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      result = result.replaceAll(`{${k}}`, String(v));
    }
  }

  return result;
}

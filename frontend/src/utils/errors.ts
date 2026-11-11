import { localize, type TranslationKey } from "./localize";

/** RoomMind and Home Assistant error codes with a message of their own. */
const CODE_KEYS: Record<string, TranslationKey> = {
  "3": "error.connection_lost",
  timeout: "error.timeout",
  unauthorized: "error.unauthorized",
  not_found: "error.not_found",
  invalid_format: "error.invalid_format",
  no_coordinator: "error.no_coordinator",
  no_model: "error.no_model",
  invalid_entity: "error.invalid_entity",
  duplicate_entity: "error.duplicate_entity",
  duplicate_group_id: "error.duplicate_group_id",
  invalid_member: "error.invalid_member",
  duplicate_member: "error.duplicate_member",
  invalid_master_entity: "error.invalid_master_entity",
  master_in_members: "error.master_in_members",
  master_is_other_member: "error.master_is_other_member",
  duplicate_master: "error.duplicate_master",
  invalid_action_script: "error.invalid_action_script",
  schedule_no_entity: "error.schedule_no_entity",
};

interface ErrorLike {
  code?: string | number;
  message?: string;
  error?: { code?: string | number; message?: string };
}

/** Error the panel throws itself; `code` picks the message like a backend code. */
export class CodedError extends Error {
  constructor(
    public readonly code: string,
    message = code,
  ) {
    super(message);
  }
}

/**
 * Text for a failed call. `hass.callWS` rejects with `{ code, message }` (no Error), a lost
 * connection with the bare number 3 or a result object carrying `error`. Known codes get a
 * localized message, else the message the call brought, else `fallback`.
 */
export function errorText(err: unknown, fallback: string, language: string): string {
  if (err === 3) return localize("error.connection_lost", language);
  const e = (err ?? {}) as ErrorLike;
  const code = e.code ?? e.error?.code;
  const key = code !== undefined ? CODE_KEYS[String(code)] : undefined;
  if (key) return localize(key, language);
  const message = e.message ?? e.error?.message;
  return typeof message === "string" && message ? message : fallback;
}

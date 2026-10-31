import { ApiError } from "../errors/api-error.js";

const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 100;
const ENCODED_CURSOR = /^[A-Za-z0-9_-]{1,512}$/u;
const SHA256 = /^[0-9a-f]{64}$/u;
const INSTRUMENT = /^[A-Z]{6,12}$/u;

export type CursorKind = "instruments" | "datasets" | "candidate-reports" | "report-candidates";

export interface PageQuery {
  readonly limit: number;
  readonly after: string | undefined;
}

function validationError(message: string): never {
  throw new ApiError(400, "VALIDATION_ERROR", message, false);
}

export function parsePageQuery(
  query: Readonly<Record<string, unknown>>,
  kind: CursorKind,
): PageQuery {
  const unknown = Object.keys(query).filter((key) => key !== "limit" && key !== "cursor");
  if (unknown.length > 0) validationError("Only limit and cursor query parameters are supported.");
  const rawLimit = query["limit"];
  if (rawLimit !== undefined && (typeof rawLimit !== "string" || !/^[1-9][0-9]*$/u.test(rawLimit))) {
    validationError("limit must be an integer between 1 and 100.");
  }
  const limit = rawLimit === undefined ? DEFAULT_PAGE_SIZE : Number(rawLimit);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_PAGE_SIZE) {
    validationError("limit must be an integer between 1 and 100.");
  }
  const rawCursor = query["cursor"];
  if (rawCursor === undefined) return { limit, after: undefined };
  if (typeof rawCursor !== "string" || !ENCODED_CURSOR.test(rawCursor)) {
    validationError("cursor is invalid.");
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(Buffer.from(rawCursor, "base64url").toString("utf8"));
  } catch {
    validationError("cursor is invalid.");
  }
  if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
    validationError("cursor is invalid.");
  }
  const value = decoded as Record<string, unknown>;
  if (Object.keys(value).sort().join(",") !== "after,kind,version"
    || value["version"] !== 1 || value["kind"] !== kind
    || typeof value["after"] !== "string"
    || !(kind === "instruments" ? INSTRUMENT
      : kind === "report-candidates" ? /^[0-9a-f]{64}:[0-9]{1,10}$/u
      : SHA256).test(value["after"])) {
    validationError("cursor is invalid.");
  }
  return { limit, after: value["after"] };
}

export function encodeCursor(kind: CursorKind, after: string): string {
  return Buffer.from(JSON.stringify({ version: 1, kind, after }), "utf8").toString("base64url");
}

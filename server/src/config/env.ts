export const NODE_ENVIRONMENTS = ["development", "test", "production"] as const;
export const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;

export type NodeEnvironment = (typeof NODE_ENVIRONMENTS)[number];
export type LogLevel = (typeof LOG_LEVELS)[number];

export interface AppConfig {
  readonly nodeEnv: NodeEnvironment;
  readonly port: number;
  readonly logLevel: LogLevel;
  readonly databaseUrl: string;
  readonly databaseConnectTimeoutMs: number;
  readonly databaseReadyTimeoutMs: number;
}

export class ConfigurationError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

function enumValue<T extends string>(
  name: string,
  value: string | undefined,
  fallback: T,
  allowed: readonly T[],
): T {
  const candidate = value ?? fallback;
  if (!allowed.includes(candidate as T)) {
    throw new ConfigurationError(`${name} must be one of: ${allowed.join(", ")}`);
  }
  return candidate as T;
}

function portValue(value: string | undefined): number {
  const candidate = value ?? "3000";
  if (!/^\d+$/.test(candidate)) {
    throw new ConfigurationError("PORT must be an integer between 1 and 65535");
  }
  const port = Number(candidate);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65_535) {
    throw new ConfigurationError("PORT must be an integer between 1 and 65535");
  }
  return port;
}

function positiveInteger(name: string, value: string | undefined, fallback: number): number {
  const candidate = value ?? String(fallback);
  if (!/^\d+$/.test(candidate)) {
    throw new ConfigurationError(`${name} must be a positive integer`);
  }
  const parsed = Number(candidate);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new ConfigurationError(`${name} must be a positive integer`);
  }
  return parsed;
}

function databaseUrl(value: string | undefined): string {
  if (value === undefined || value.trim() === "") {
    throw new ConfigurationError("DATABASE_URL is required");
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new ConfigurationError("DATABASE_URL must be a valid PostgreSQL URL");
  }
  if (parsed.protocol !== "postgres:" && parsed.protocol !== "postgresql:") {
    throw new ConfigurationError("DATABASE_URL must use the postgres or postgresql scheme");
  }
  return value;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  return Object.freeze({
    nodeEnv: enumValue("NODE_ENV", env["NODE_ENV"], "development", NODE_ENVIRONMENTS),
    port: portValue(env["PORT"]),
    logLevel: enumValue("LOG_LEVEL", env["LOG_LEVEL"], "info", LOG_LEVELS),
    databaseUrl: databaseUrl(env["DATABASE_URL"]),
    databaseConnectTimeoutMs: positiveInteger(
      "DATABASE_CONNECT_TIMEOUT_MS", env["DATABASE_CONNECT_TIMEOUT_MS"], 3_000,
    ),
    databaseReadyTimeoutMs: positiveInteger(
      "DATABASE_READY_TIMEOUT_MS", env["DATABASE_READY_TIMEOUT_MS"], 1_000,
    ),
  });
}

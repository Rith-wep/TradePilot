export const NODE_ENVIRONMENTS = ["development", "test", "production"] as const;
export const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;

export type NodeEnvironment = (typeof NODE_ENVIRONMENTS)[number];
export type LogLevel = (typeof LOG_LEVELS)[number];

export interface AppConfig {
  readonly nodeEnv: NodeEnvironment;
  readonly port: number;
  readonly logLevel: LogLevel;
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

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  return Object.freeze({
    nodeEnv: enumValue("NODE_ENV", env["NODE_ENV"], "development", NODE_ENVIRONMENTS),
    port: portValue(env["PORT"]),
    logLevel: enumValue("LOG_LEVEL", env["LOG_LEVEL"], "info", LOG_LEVELS),
  });
}

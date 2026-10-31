import { isAbsolute, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

export const NODE_ENVIRONMENTS = ["development", "test", "production"] as const;
export const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;

export type NodeEnvironment = (typeof NODE_ENVIRONMENTS)[number];
export type LogLevel = (typeof LOG_LEVELS)[number];

export interface AppConfig {
  readonly nodeEnv: NodeEnvironment;
  readonly host: "127.0.0.1" | "::1" | "localhost" | "0.0.0.0";
  readonly port: number;
  readonly logLevel: LogLevel;
  readonly databaseUrl: string;
  readonly databaseConnectTimeoutMs: number;
  readonly databaseReadyTimeoutMs: number;
  readonly artifactVerifier: ArtifactVerifierConfig;
  readonly auth: AuthConfig;
  readonly security: SecurityConfig;
  readonly researchJobs: ResearchJobConfig;
}
export type AuthRole = "viewer" | "researcher" | "admin";
export type JwtAlgorithm = "RS256" | "PS256" | "ES256";
export interface AuthConfig {
  readonly issuer: string;
  readonly audience: string;
  readonly jwksUrl: string;
  readonly algorithms: readonly JwtAlgorithm[];
  readonly rolesClaim: string;
  readonly jwksTimeoutMs: number;
}
export interface SecurityConfig {
  readonly corsAllowedOrigins: readonly string[];
  readonly rateLimitWindowMs: number;
  readonly rateLimitMax: number;
  readonly requestBodyMaxBytes: number;
}
export interface ResearchJobConfig {
  readonly maxActivePerOwner: number;
  readonly maxQueueDepth: number;
  readonly maxAttempts: number;
  readonly leaseMs: number;
  readonly pollMs: number;
  readonly implementationRevision: string;
}

function implementationRevision(value: string | undefined, nodeEnv: NodeEnvironment): string {
  const configured = value?.trim();
  if (configured !== undefined && configured !== "") {
    if (configured !== "unknown" && !/^[0-9a-f]{40}$/u.test(configured)) {
      throw new ConfigurationError("TRADEPILOT_IMPLEMENTATION_REVISION must be a Git SHA or unknown");
    }
    if (nodeEnv === "production" && configured === "unknown") {
      throw new ConfigurationError("production requires a 40-character TRADEPILOT_IMPLEMENTATION_REVISION");
    }
    return configured;
  }
  const result = spawnSync("git", ["rev-parse", "HEAD"], { encoding: "utf8", shell: false, windowsHide: true });
  const revision = result.status === 0 ? result.stdout.trim().toLowerCase() : "unknown";
  const resolved = /^[0-9a-f]{40}$/u.test(revision) ? revision : "unknown";
  if (nodeEnv === "production" && resolved === "unknown") {
    throw new ConfigurationError("production requires a 40-character TRADEPILOT_IMPLEMENTATION_REVISION");
  }
  return resolved;
}

function loopbackHost(value: string | undefined): AppConfig["host"] {
  const candidate = value ?? "127.0.0.1";
  if (candidate !== "127.0.0.1" && candidate !== "::1" && candidate !== "localhost" && candidate !== "0.0.0.0") {
    throw new ConfigurationError("HOST must be a supported explicit bind address");
  }
  return candidate;
}

function valueOrFile(name: string, env: NodeJS.ProcessEnv): string | undefined {
  const direct = env[name];
  const file = env[`${name}_FILE`];
  if (direct !== undefined && file !== undefined) {
    throw new ConfigurationError(`${name} and ${name}_FILE cannot both be set`);
  }
  if (file === undefined) return direct;
  try {
    const value = readFileSync(file, "utf8").trim();
    if (value === "") throw new Error("empty secret");
    return value;
  } catch {
    throw new ConfigurationError(`${name}_FILE could not be read`);
  }
}
export interface ArtifactVerifierConfig {
  readonly pythonExecutable: string;
  readonly pythonWorkingDirectory: string;
  readonly schemaDirectory: string;
  readonly datasetRoot: string;
  readonly reportRoot: string;
  readonly timeoutMs: number;
  readonly maxInputBytes: number;
  readonly maxOutputBytes: number;
  readonly maxErrorBytes: number;
  readonly maxConcurrency: number;
  readonly maxPendingRequests: number;
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

function boundedInteger(name: string, value: string | undefined, fallback: number, maximum: number): number {
  const parsed = positiveInteger(name, value, fallback);
  if (parsed > maximum) throw new ConfigurationError(`${name} must be at most ${maximum}`);
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

function nonEmpty(name: string, value: string | undefined, fallback: string): string {
  const candidate = value ?? fallback;
  if (candidate.trim() === "") {
    throw new ConfigurationError(`${name} must not be empty`);
  }
  return candidate;
}

function absolutePath(name: string, value: string | undefined, fallback: string): string {
  const candidate = resolve(nonEmpty(name, value, fallback));
  if (!isAbsolute(candidate)) {
    throw new ConfigurationError(`${name} must resolve to an absolute path`);
  }
  return candidate;
}

function trustedHttpsUrl(name: string, value: string | undefined): string {
  if (value === undefined || value.trim() === "") throw new ConfigurationError(`${name} is required`);
  let parsed: URL;
  try { parsed = new URL(value); } catch { throw new ConfigurationError(`${name} must be a valid URL`); }
  if (parsed.protocol !== "https:" || parsed.username !== "" || parsed.password !== ""
    || parsed.search !== "" || parsed.hash !== "") {
    throw new ConfigurationError(`${name} must be a credential-free HTTPS URL without query or fragment`);
  }
  return parsed.href.replace(/\/$/u, "");
}

function algorithms(value: string | undefined): readonly JwtAlgorithm[] {
  const supported: readonly JwtAlgorithm[] = ["RS256", "PS256", "ES256"];
  const candidates = (value ?? "RS256").split(",").map((item) => item.trim()).filter(Boolean);
  if (candidates.length === 0 || new Set(candidates).size !== candidates.length
    || candidates.some((item) => !supported.includes(item as JwtAlgorithm))) {
    throw new ConfigurationError(`OIDC_ALLOWED_ALGORITHMS must contain only: ${supported.join(", ")}`);
  }
  return Object.freeze(candidates as JwtAlgorithm[]);
}

function rolesClaim(value: string | undefined): string {
  const candidate = value ?? "roles";
  if (!/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/u.test(candidate)) throw new ConfigurationError("OIDC_ROLES_CLAIM is invalid");
  return candidate;
}

function corsOrigins(value: string | undefined): readonly string[] {
  if (value === undefined || value.trim() === "") return Object.freeze([]);
  const origins = value.split(",").map((item) => item.trim());
  if (new Set(origins).size !== origins.length || origins.some((origin) => {
    try {
      const parsed = new URL(origin);
      return parsed.origin !== origin || (parsed.protocol !== "https:"
        && !(parsed.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname)));
    } catch { return true; }
  })) throw new ConfigurationError("CORS_ALLOWED_ORIGINS contains an unsafe origin");
  return Object.freeze(origins);
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const nodeEnv = enumValue("NODE_ENV", env["NODE_ENV"], "development", NODE_ENVIRONMENTS);
  const researchRoot = absolutePath(
    "TRADEPILOT_PYTHON_WORKING_DIRECTORY",
    env["TRADEPILOT_PYTHON_WORKING_DIRECTORY"],
    resolve(process.cwd(), "..", "research"),
  );
  return Object.freeze({
    nodeEnv,
    host: loopbackHost(env["HOST"]),
    port: portValue(env["PORT"]),
    logLevel: enumValue("LOG_LEVEL", env["LOG_LEVEL"], "info", LOG_LEVELS),
    databaseUrl: databaseUrl(valueOrFile("DATABASE_URL", env)),
    databaseConnectTimeoutMs: positiveInteger(
      "DATABASE_CONNECT_TIMEOUT_MS", env["DATABASE_CONNECT_TIMEOUT_MS"], 3_000,
    ),
    databaseReadyTimeoutMs: positiveInteger(
      "DATABASE_READY_TIMEOUT_MS", env["DATABASE_READY_TIMEOUT_MS"], 1_000,
    ),
    artifactVerifier: Object.freeze({
      pythonExecutable: nonEmpty(
        "TRADEPILOT_PYTHON_EXECUTABLE", env["TRADEPILOT_PYTHON_EXECUTABLE"], "python",
      ),
      pythonWorkingDirectory: researchRoot,
      schemaDirectory: absolutePath(
        "TRADEPILOT_CONTRACT_SCHEMA_DIRECTORY",
        env["TRADEPILOT_CONTRACT_SCHEMA_DIRECTORY"],
        resolve(researchRoot, "contracts"),
      ),
      datasetRoot: absolutePath(
        "TRADEPILOT_DATA_ROOT", env["TRADEPILOT_DATA_ROOT"], resolve(researchRoot, "data"),
      ),
      reportRoot: absolutePath(
        "TRADEPILOT_REPORT_ROOT", env["TRADEPILOT_REPORT_ROOT"], resolve(researchRoot, "reports"),
      ),
      timeoutMs: positiveInteger(
        "TRADEPILOT_VERIFIER_TIMEOUT_MS", env["TRADEPILOT_VERIFIER_TIMEOUT_MS"], 10_000,
      ),
      maxInputBytes: positiveInteger(
        "TRADEPILOT_VERIFIER_MAX_INPUT_BYTES",
        env["TRADEPILOT_VERIFIER_MAX_INPUT_BYTES"],
        65_536,
      ),
      maxOutputBytes: positiveInteger(
        "TRADEPILOT_VERIFIER_MAX_OUTPUT_BYTES",
        env["TRADEPILOT_VERIFIER_MAX_OUTPUT_BYTES"],
        1_048_576,
      ),
      maxErrorBytes: positiveInteger(
        "TRADEPILOT_VERIFIER_MAX_ERROR_BYTES",
        env["TRADEPILOT_VERIFIER_MAX_ERROR_BYTES"],
        16_384,
      ),
      maxConcurrency: positiveInteger(
        "TRADEPILOT_VERIFIER_MAX_CONCURRENCY",
        env["TRADEPILOT_VERIFIER_MAX_CONCURRENCY"],
        2,
      ),
      maxPendingRequests: positiveInteger(
        "TRADEPILOT_VERIFIER_MAX_PENDING_REQUESTS",
        env["TRADEPILOT_VERIFIER_MAX_PENDING_REQUESTS"],
        16,
      ),
    }),
    auth: Object.freeze({
      issuer: trustedHttpsUrl("OIDC_ISSUER", env["OIDC_ISSUER"]),
      audience: nonEmpty("OIDC_AUDIENCE", env["OIDC_AUDIENCE"], ""),
      jwksUrl: trustedHttpsUrl("OIDC_JWKS_URL", env["OIDC_JWKS_URL"]),
      algorithms: algorithms(env["OIDC_ALLOWED_ALGORITHMS"]),
      rolesClaim: rolesClaim(env["OIDC_ROLES_CLAIM"]),
      jwksTimeoutMs: positiveInteger("OIDC_JWKS_TIMEOUT_MS", env["OIDC_JWKS_TIMEOUT_MS"], 3_000),
    }),
    security: Object.freeze({
      corsAllowedOrigins: corsOrigins(env["CORS_ALLOWED_ORIGINS"]),
      rateLimitWindowMs: positiveInteger("RATE_LIMIT_WINDOW_MS", env["RATE_LIMIT_WINDOW_MS"], 60_000),
      rateLimitMax: positiveInteger("RATE_LIMIT_MAX", env["RATE_LIMIT_MAX"], 120),
      requestBodyMaxBytes: positiveInteger("REQUEST_BODY_MAX_BYTES", env["REQUEST_BODY_MAX_BYTES"], 32_768),
    }),
    researchJobs: Object.freeze({
      maxActivePerOwner: positiveInteger("RESEARCH_JOB_MAX_ACTIVE_PER_OWNER", env["RESEARCH_JOB_MAX_ACTIVE_PER_OWNER"], 3),
      maxQueueDepth: positiveInteger("RESEARCH_JOB_MAX_QUEUE_DEPTH", env["RESEARCH_JOB_MAX_QUEUE_DEPTH"], 100),
      maxAttempts: boundedInteger("RESEARCH_JOB_MAX_ATTEMPTS", env["RESEARCH_JOB_MAX_ATTEMPTS"], 3, 10),
      leaseMs: positiveInteger("RESEARCH_JOB_LEASE_MS", env["RESEARCH_JOB_LEASE_MS"], 60_000),
      pollMs: positiveInteger("RESEARCH_JOB_POLL_MS", env["RESEARCH_JOB_POLL_MS"], 1_000),
      implementationRevision: implementationRevision(env["TRADEPILOT_IMPLEMENTATION_REVISION"], nodeEnv),
    }),
  });
}

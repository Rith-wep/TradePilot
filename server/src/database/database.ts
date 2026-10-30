import { Pool, type PoolConfig } from "pg";
import type { AppConfig } from "../config/env.js";

export interface DatabaseHealth {
  check(): Promise<boolean>;
}

export interface Database extends DatabaseHealth {
  readonly pool: Pool;
  close(): Promise<void>;
}

export class PostgresDatabase implements Database {
  public readonly pool: Pool;
  readonly #healthPool: Pool;

  public constructor(poolConfig: PoolConfig, readyTimeoutMs: number) {
    this.pool = new Pool(poolConfig);
    this.#healthPool = new Pool({
      ...poolConfig,
      max: 1,
      query_timeout: readyTimeoutMs,
      statement_timeout: readyTimeoutMs,
    });
  }

  public async check(): Promise<boolean> {
    try {
      await this.#healthPool.query("SELECT 1 AS ready");
      return true;
    } catch {
      return false;
    }
  }

  public async close(): Promise<void> {
    await Promise.all([this.pool.end(), this.#healthPool.end()]);
  }
}

export function createDatabase(config: AppConfig): Database {
  return new PostgresDatabase({
    connectionString: config.databaseUrl,
    connectionTimeoutMillis: config.databaseConnectTimeoutMs,
    max: 10,
    application_name: "tradepilot-server",
  }, config.databaseReadyTimeoutMs);
}

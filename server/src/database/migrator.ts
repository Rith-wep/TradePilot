import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import type { Pool, PoolClient } from "pg";

export type MigrationDirection = "up" | "down";

interface MigrationFile {
  readonly version: string;
  readonly name: string;
  readonly upPath: string;
  readonly downPath: string;
}

async function migrationFiles(directory: string): Promise<readonly MigrationFile[]> {
  const names = await readdir(directory);
  const upFiles = names.filter((name) => /^\d+_[a-z0-9_]+\.up\.sql$/.test(name)).sort();
  return Promise.all(upFiles.map(async (name) => {
    const match = /^(\d+)_([a-z0-9_]+)\.up\.sql$/.exec(name);
    if (match === null) {
      throw new Error(`invalid migration filename: ${name}`);
    }
    const version = match[1];
    const migrationName = match[2];
    if (version === undefined || migrationName === undefined) {
      throw new Error(`invalid migration filename: ${name}`);
    }
    const downName = `${version}_${migrationName}.down.sql`;
    if (!names.includes(downName)) {
      throw new Error(`migration ${name} has no matching down file`);
    }
    return {
      version,
      name: migrationName,
      upPath: join(directory, name),
      downPath: join(directory, downName),
    };
  }));
}

async function ensureMigrationTable(client: PoolClient): Promise<void> {
  await client.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version text PRIMARY KEY,
      name text NOT NULL,
      applied_at timestamptz NOT NULL DEFAULT now()
    )
  `);
}

async function appliedVersions(client: PoolClient): Promise<Set<string>> {
  const result = await client.query<{ version: string }>(
    "SELECT version FROM schema_migrations ORDER BY version",
  );
  return new Set(result.rows.map((row) => row.version));
}

export async function migrate(pool: Pool, directory: string, direction: MigrationDirection): Promise<string[]> {
  const files = await migrationFiles(directory);
  const client = await pool.connect();
  const changed: string[] = [];
  try {
    await client.query("BEGIN");
    await client.query("SELECT pg_advisory_xact_lock(hashtext('tradepilot-schema-migrations'))");
    await ensureMigrationTable(client);
    const applied = await appliedVersions(client);
    if (direction === "up") {
      for (const migration of files) {
        if (applied.has(migration.version)) {
          continue;
        }
        await client.query(await readFile(migration.upPath, "utf8"));
        await client.query(
          "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
          [migration.version, migration.name],
        );
        changed.push(migration.version);
      }
    } else {
      const latest = [...files].reverse().find((migration) => applied.has(migration.version));
      if (latest !== undefined) {
        await client.query(await readFile(latest.downPath, "utf8"));
        await client.query("DELETE FROM schema_migrations WHERE version = $1", [latest.version]);
        changed.push(latest.version);
      }
    }
    await client.query("COMMIT");
    return changed;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

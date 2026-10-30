import { resolve } from "node:path";
import { loadConfig } from "../config/env.js";
import { createDatabase } from "./database.js";
import { migrate, type MigrationDirection } from "./migrator.js";

const direction = process.argv[2];
if (direction !== "up" && direction !== "down") {
  process.stderr.write("usage: migrate-cli.js <up|down>\n");
  process.exitCode = 2;
} else {
  await run(direction);
}

async function run(value: MigrationDirection): Promise<void> {
  const config = loadConfig();
  const database = createDatabase(config);
  try {
    const changed = await migrate(database.pool, resolve(process.cwd(), "migrations"), value);
    process.stdout.write(`${JSON.stringify({ direction: value, changed })}\n`);
  } finally {
    await database.close();
  }
}

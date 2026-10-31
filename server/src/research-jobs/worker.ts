import { loadConfig } from "../config/env.js";
import { createDatabase } from "../database/database.js";
import { createJsonLogger } from "../logging/logger.js";
import { ResearchJobRepository } from "./repository.js";
import { ResearchJobWorker } from "./worker-service.js";

const config = loadConfig();
const logger = createJsonLogger(config.logLevel);
const database = createDatabase(config);
const repository = new ResearchJobRepository(database.pool, config.researchJobs);
const worker = new ResearchJobWorker(repository, {
  async process() {
    // Phase 5 Step 10 deliberately has no research executor.
    throw new Error("research executor is not installed");
  },
}, logger, config.researchJobs.pollMs);

process.once("SIGINT", () => worker.stop());
process.once("SIGTERM", () => worker.stop());
try { await worker.run(); } finally { await database.close(); }


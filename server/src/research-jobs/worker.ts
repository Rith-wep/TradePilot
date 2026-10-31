import { loadConfig } from "../config/env.js";
import { createDatabase } from "../database/database.js";
import { createJsonLogger } from "../logging/logger.js";
import { ResearchJobRepository } from "./repository.js";
import { ResearchJobWorker } from "./worker-service.js";
import { ArtifactVerifierService } from "../verification/artifact-verifier.js";
import { CatalogRegistrationService } from "../catalog/registration-service.js";
import { PythonResearchExecutionService } from "./execution-service.js";
import { TrustedResearchJobProcessor } from "./processor.js";

const config = loadConfig();
const logger = createJsonLogger(config.logLevel);
const database = createDatabase(config);
const repository = new ResearchJobRepository(database.pool, config.researchJobs);
const verifier = new ArtifactVerifierService(config.artifactVerifier);
const registration = new CatalogRegistrationService(verifier, database.pool);
const processor = new TrustedResearchJobProcessor(
  new PythonResearchExecutionService(
    config.artifactVerifier, config.researchJobs.implementationRevision,
  ), registration,
);
const worker = new ResearchJobWorker(
  repository, processor, logger, config.researchJobs.pollMs,
  Math.max(25, Math.floor(config.researchJobs.leaseMs / 3)),
);

process.once("SIGINT", () => worker.stop());
process.once("SIGTERM", () => worker.stop());
try { await worker.run(); } finally { await database.close(); }


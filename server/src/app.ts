import express, { type Express } from "express";
import type { AppConfig } from "./config/env.js";
import type { DatabaseHealth } from "./database/database.js";
import type { CatalogReadStore } from "./database/catalog-read-repository.js";
import type { CandidateEvidenceService } from "./evidence/evidence-service.js";
import { errorHandler } from "./http/middleware/error-handler.js";
import { notFoundHandler } from "./http/middleware/not-found.js";
import { requestIdMiddleware } from "./http/middleware/request-id.js";
import { requestLogger } from "./http/middleware/request-logger.js";
import { healthRouter } from "./http/routes/health.js";
import { catalogRouter } from "./http/routes/catalog.js";
import { evidenceRouter } from "./http/routes/evidence.js";
import type { Logger } from "./logging/logger.js";

export interface AppDependencies {
  readonly config: AppConfig;
  readonly logger: Logger;
  readonly database: DatabaseHealth;
  readonly catalog: CatalogReadStore;
  readonly evidence: Pick<CandidateEvidenceService, "list" | "get">;
}

export function createApp({ config, logger, database, catalog, evidence }: AppDependencies): Express {
  const app = express();
  app.disable("x-powered-by");
  app.use(requestIdMiddleware);
  app.use(requestLogger(logger));
  app.use(express.json({ limit: "32kb" }));
  app.use("/health", healthRouter(config, database));
  app.use("/api/v1", catalogRouter(config, catalog));
  app.use("/api/v1", evidenceRouter(config, catalog, evidence));
  app.use(notFoundHandler);
  app.use(errorHandler(logger));
  return app;
}

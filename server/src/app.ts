import express, { type Express } from "express";
import type { AppConfig } from "./config/env.js";
import type { DatabaseHealth } from "./database/database.js";
import { errorHandler } from "./http/middleware/error-handler.js";
import { notFoundHandler } from "./http/middleware/not-found.js";
import { requestIdMiddleware } from "./http/middleware/request-id.js";
import { requestLogger } from "./http/middleware/request-logger.js";
import { healthRouter } from "./http/routes/health.js";
import type { Logger } from "./logging/logger.js";

export interface AppDependencies {
  readonly config: AppConfig;
  readonly logger: Logger;
  readonly database: DatabaseHealth;
}

export function createApp({ config, logger, database }: AppDependencies): Express {
  const app = express();
  app.disable("x-powered-by");
  app.use(requestIdMiddleware);
  app.use(requestLogger(logger));
  app.use(express.json({ limit: "32kb" }));
  app.use("/health", healthRouter(config, database));
  app.use(notFoundHandler);
  app.use(errorHandler(logger));
  return app;
}

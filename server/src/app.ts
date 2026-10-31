import express, { type Express } from "express";
import cors from "cors";
import helmet from "helmet";
import { rateLimit } from "express-rate-limit";
import { authenticate, authorize } from "./auth/middleware.js";
import type { AccessTokenVerifier } from "./auth/oidc-verifier.js";
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
import { ApiError } from "./http/errors/api-error.js";
import type { Logger } from "./logging/logger.js";

export interface AppDependencies {
  readonly config: AppConfig;
  readonly logger: Logger;
  readonly database: DatabaseHealth;
  readonly catalog: CatalogReadStore;
  readonly evidence: Pick<CandidateEvidenceService, "list" | "get">;
  readonly tokenVerifier: AccessTokenVerifier;
}

export function createApp({ config, logger, database, catalog, evidence, tokenVerifier }: AppDependencies): Express {
  const app = express();
  app.disable("x-powered-by");
  app.use(requestIdMiddleware);
  app.use(helmet());
  app.use(cors({
    credentials: false,
    methods: ["GET", "OPTIONS"],
    allowedHeaders: ["authorization", "content-type", "x-request-id"],
    origin(origin, callback) {
      if (origin === undefined || config.security.corsAllowedOrigins.includes(origin)) callback(null, true);
      else callback(new ApiError(403, "CORS_ORIGIN_DENIED", "The request origin is not allowed."));
    },
  }));
  app.use(requestLogger(logger));
  app.use(express.json({ limit: config.security.requestBodyMaxBytes }));
  app.use("/health", healthRouter(config, database));
  app.use("/api/v1", rateLimit({
    windowMs: config.security.rateLimitWindowMs,
    limit: config.security.rateLimitMax,
    standardHeaders: "draft-8",
    legacyHeaders: false,
    handler(_req, _res, next) {
      next(new ApiError(429, "RATE_LIMIT_EXCEEDED", "Too many requests.", true));
    },
  }), authenticate(tokenVerifier), authorize("viewer"));
  app.use("/api/v1", catalogRouter(catalog));
  app.use("/api/v1", evidenceRouter(catalog, evidence));
  app.use(notFoundHandler);
  app.use(errorHandler(logger));
  return app;
}

import { Router } from "express";
import type { AppConfig } from "../../config/env.js";
import type { DatabaseHealth } from "../../database/database.js";
import { successEnvelope } from "../contracts/envelope.js";

export interface HealthStatus {
  readonly status: "UP";
  readonly service: "tradepilot-server";
}

export interface ReadinessStatus {
  readonly status: "UP" | "DOWN";
  readonly service: "tradepilot-server";
  readonly checks: readonly {
    readonly name: "configuration" | "database";
    readonly status: "UP" | "DOWN";
  }[];
  readonly environment: AppConfig["nodeEnv"];
}

export function healthRouter(config: AppConfig, database: DatabaseHealth): Router {
  const router = Router();

  router.get("/live", (req, res) => {
    const data: HealthStatus = { status: "UP", service: "tradepilot-server" };
    res.json(successEnvelope(req.requestId, data));
  });

  router.get("/ready", async (req, res) => {
    const databaseReady = await database.check();
    const data: ReadinessStatus = {
      status: databaseReady ? "UP" : "DOWN",
      service: "tradepilot-server",
      environment: config.nodeEnv,
      checks: [
        { name: "configuration", status: "UP" },
        { name: "database", status: databaseReady ? "UP" : "DOWN" },
      ],
    };
    res.status(databaseReady ? 200 : 503).json(successEnvelope(req.requestId, data));
  });

  return router;
}

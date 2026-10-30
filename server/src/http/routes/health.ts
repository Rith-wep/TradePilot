import { Router } from "express";
import type { AppConfig } from "../../config/env.js";
import { successEnvelope } from "../contracts/envelope.js";

export interface HealthStatus {
  readonly status: "UP";
  readonly service: "tradepilot-server";
}

export interface ReadinessStatus extends HealthStatus {
  readonly checks: readonly {
    readonly name: "configuration";
    readonly status: "UP";
  }[];
  readonly environment: AppConfig["nodeEnv"];
}

export function healthRouter(config: AppConfig): Router {
  const router = Router();

  router.get("/live", (req, res) => {
    const data: HealthStatus = { status: "UP", service: "tradepilot-server" };
    res.json(successEnvelope(req.requestId, data));
  });

  router.get("/ready", (req, res) => {
    const data: ReadinessStatus = {
      status: "UP",
      service: "tradepilot-server",
      environment: config.nodeEnv,
      checks: [{ name: "configuration", status: "UP" }],
    };
    res.json(successEnvelope(req.requestId, data));
  });

  return router;
}

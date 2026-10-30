import { createServer } from "node:http";
import { createApp } from "./app.js";
import { loadConfig } from "./config/env.js";
import { createJsonLogger } from "./logging/logger.js";

const config = loadConfig();
const logger = createJsonLogger(config.logLevel);
const app = createApp({ config, logger });
const server = createServer(app);

server.listen(config.port, () => {
  logger.log("info", "server_started", {
    port: config.port,
    environment: config.nodeEnv,
  });
});

function shutdown(signal: NodeJS.Signals): void {
  logger.log("info", "server_shutdown_started", { signal });
  server.close((error) => {
    if (error !== undefined) {
      logger.log("error", "server_shutdown_failed", { error: error.message });
      process.exitCode = 1;
    }
  });
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);

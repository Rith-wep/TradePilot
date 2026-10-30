import type { LogLevel } from "../config/env.js";

export type LogFields = Readonly<Record<string, unknown>>;

export interface Logger {
  log(level: LogLevel, event: string, fields?: LogFields): void;
}

const PRIORITY: Readonly<Record<LogLevel, number>> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

export function createJsonLogger(minimumLevel: LogLevel): Logger {
  return {
    log(level, event, fields = {}) {
      if (PRIORITY[level] < PRIORITY[minimumLevel]) {
        return;
      }
      const record = JSON.stringify({
        timestamp: new Date().toISOString(),
        level,
        event,
        ...fields,
      });
      const output = level === "error" ? process.stderr : process.stdout;
      output.write(`${record}\n`);
    },
  };
}

export const silentLogger: Logger = { log() {} };

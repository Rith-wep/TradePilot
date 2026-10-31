import type { ErrorRequestHandler } from "express";
import type { Logger } from "../../logging/logger.js";
import { errorEnvelope } from "../contracts/envelope.js";
import { ApiError } from "../errors/api-error.js";

function isMalformedJson(error: unknown): boolean {
  if (!(error instanceof SyntaxError) || typeof error !== "object" || error === null) {
    return false;
  }
  const value = error as { status?: unknown; type?: unknown };
  return value.status === 400 && value.type === "entity.parse.failed";
}

function isBodyTooLarge(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const value = error as { status?: unknown; type?: unknown };
  return value.status === 413 && value.type === "entity.too.large";
}

export function errorHandler(logger: Logger): ErrorRequestHandler {
  return (error: unknown, req, res, _next): void => {
    const known = error instanceof ApiError;
    const malformedJson = isMalformedJson(error);
    const bodyTooLarge = isBodyTooLarge(error);
    const status = known ? error.status : malformedJson ? 400 : bodyTooLarge ? 413 : 500;
    const code = known ? error.code : malformedJson ? "VALIDATION_ERROR" : bodyTooLarge ? "REQUEST_TOO_LARGE" : "INTERNAL_ERROR";
    const message = known
      ? error.message
      : malformedJson
        ? "The request body must contain valid JSON."
        : bodyTooLarge
          ? "The request body exceeds the configured size limit."
        : "An unexpected error occurred.";
    const retryable = known ? error.retryable : false;
    const details = known ? error.details : undefined;

    logger.log(status >= 500 ? "error" : "warn", "http_request_failed", {
      requestId: req.requestId,
      method: req.method,
      path: req.path,
      status,
      code,
      errorName: error instanceof Error ? error.name : "UnknownError",
    });

    res.status(status).json(errorEnvelope(req.requestId, {
      code,
      message,
      retryable,
      ...(details === undefined ? {} : { details }),
    }));
  };
}

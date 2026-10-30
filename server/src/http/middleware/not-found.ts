import type { NextFunction, Request, Response } from "express";
import { ApiError } from "../errors/api-error.js";

export function notFoundHandler(_req: Request, _res: Response, next: NextFunction): void {
  next(new ApiError(404, "RESOURCE_NOT_FOUND", "The requested resource was not found."));
}

import { randomUUID } from "node:crypto";
import type { NextFunction, Request, Response } from "express";

const SAFE_REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/;

export function requestIdMiddleware(req: Request, res: Response, next: NextFunction): void {
  const supplied = req.header("x-request-id");
  req.requestId = supplied !== undefined && SAFE_REQUEST_ID.test(supplied)
    ? supplied
    : randomUUID();
  res.setHeader("x-request-id", req.requestId);
  next();
}

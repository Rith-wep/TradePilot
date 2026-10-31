import type { RequestHandler } from "express";
import type { AuthRole } from "../config/env.js";
import { ApiError } from "../http/errors/api-error.js";
import type { AccessTokenVerifier } from "./oidc-verifier.js";

const ROLE_LEVEL: Readonly<Record<AuthRole, number>> = { viewer: 1, researcher: 2, admin: 3 };

export function authenticate(verifier: AccessTokenVerifier): RequestHandler {
  return async (req, res, next) => {
    const authorization = req.header("authorization");
    if (authorization === undefined) {
      res.setHeader("WWW-Authenticate", "Bearer");
      next(new ApiError(401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required."));
      return;
    }
    const match = /^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/u.exec(authorization);
    if (match === null || match[1] === undefined || authorization.length > 8_200) {
      res.setHeader("WWW-Authenticate", "Bearer error=\"invalid_token\"");
      next(new ApiError(401, "INVALID_TOKEN", "The bearer token is invalid."));
      return;
    }
    try {
      req.principal = await verifier.verify(match[1]);
      next();
    } catch {
      res.setHeader("WWW-Authenticate", "Bearer error=\"invalid_token\"");
      next(new ApiError(401, "INVALID_TOKEN", "The bearer token is invalid."));
    }
  };
}

export function authorize(required: AuthRole): RequestHandler {
  return (req, _res, next) => {
    if (req.principal === undefined) {
      next(new ApiError(401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required."));
      return;
    }
    if (!req.principal.roles.some((role) => ROLE_LEVEL[role] >= ROLE_LEVEL[required])) {
      next(new ApiError(403, "INSUFFICIENT_ROLE", "The authenticated principal lacks the required role."));
      return;
    }
    next();
  };
}

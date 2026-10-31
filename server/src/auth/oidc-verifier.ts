import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey, type JWTPayload } from "jose";
import type { AuthConfig, AuthRole } from "../config/env.js";
import type { AuthenticatedPrincipal } from "./principal.js";

const ROLES: readonly AuthRole[] = ["viewer", "researcher", "admin"];

export interface AccessTokenVerifier {
  verify(token: string): Promise<AuthenticatedPrincipal>;
}

export class OidcTokenVerifier implements AccessTokenVerifier {
  private readonly keyResolver: JWTVerifyGetKey;
  public constructor(private readonly config: AuthConfig, keyResolver?: JWTVerifyGetKey) {
    this.keyResolver = keyResolver ?? createRemoteJWKSet(new URL(config.jwksUrl), {
      timeoutDuration: config.jwksTimeoutMs,
      cooldownDuration: 30_000,
      cacheMaxAge: 600_000,
    });
  }

  public async verify(token: string): Promise<AuthenticatedPrincipal> {
    const result = await jwtVerify(token, this.keyResolver, {
      issuer: this.config.issuer,
      audience: this.config.audience,
      algorithms: [...this.config.algorithms],
      requiredClaims: ["sub", "iat", "exp"],
      clockTolerance: 5,
    });
    return this.principal(result.payload);
  }

  private principal(payload: JWTPayload): AuthenticatedPrincipal {
    if (typeof payload.sub !== "string" || payload.sub.length === 0 || payload.sub.length > 200) {
      throw new Error("verified token subject is invalid");
    }
    const claim = payload[this.config.rolesClaim];
    const roles = Array.isArray(claim)
      ? claim.filter((role): role is AuthRole => typeof role === "string" && ROLES.includes(role as AuthRole))
      : [];
    const audience = typeof payload.aud === "string" ? [payload.aud] : payload.aud ?? [];
    return Object.freeze({
      subject: payload.sub,
      issuer: String(payload.iss),
      audience: Object.freeze([...audience]),
      roles: Object.freeze([...new Set(roles)]),
      tokenId: typeof payload.jti === "string" ? payload.jti : undefined,
    });
  }
}

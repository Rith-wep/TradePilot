import type { AccessTokenVerifier } from "../src/auth/oidc-verifier.js";
import type { AuthConfig, ResearchJobConfig, SecurityConfig } from "../src/config/env.js";

export const TEST_AUTH_CONFIG: AuthConfig = {
  issuer: "https://identity.example.test",
  audience: "tradepilot-api",
  jwksUrl: "https://identity.example.test/.well-known/jwks.json",
  algorithms: ["RS256"],
  rolesClaim: "roles",
  jwksTimeoutMs: 100,
};
export const TEST_SECURITY_CONFIG: SecurityConfig = {
  corsAllowedOrigins: ["https://ui.example.test"],
  rateLimitWindowMs: 60_000,
  rateLimitMax: 1_000,
  requestBodyMaxBytes: 32_768,
};
export const TEST_RESEARCH_JOBS_CONFIG: ResearchJobConfig = {
  maxActivePerOwner: 3, maxQueueDepth: 100, maxAttempts: 3, leaseMs: 60_000, pollMs: 1_000,
  implementationRevision: "unknown",
};
export const TEST_AUTHORIZATION = "Bearer test.test.test";
export const viewerTokenVerifier: AccessTokenVerifier = {
  async verify() {
    return {
      subject: "test-viewer", issuer: TEST_AUTH_CONFIG.issuer,
      audience: [TEST_AUTH_CONFIG.audience], roles: ["viewer"], tokenId: "test-token",
    };
  },
};

import assert from "node:assert/strict";
import test, { before } from "node:test";
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } from "jose";
import request from "supertest";
import { createApp } from "../src/app.js";
import { OidcTokenVerifier } from "../src/auth/oidc-verifier.js";
import type { AppConfig, AuthRole } from "../src/config/env.js";
import { silentLogger } from "../src/logging/logger.js";
import { TEST_AUTH_CONFIG, TEST_RESEARCH_JOBS_CONFIG, TEST_SECURITY_CONFIG } from "./security-fixtures.js";

let signingKey: CryptoKey;
let wrongKey: CryptoKey;
let verifier: OidcTokenVerifier;

before(async () => {
  const trusted = await generateKeyPair("RS256");
  const untrusted = await generateKeyPair("RS256");
  signingKey = trusted.privateKey;
  wrongKey = untrusted.privateKey;
  const jwk = await exportJWK(trusted.publicKey);
  verifier = new OidcTokenVerifier(TEST_AUTH_CONFIG, createLocalJWKSet({
    keys: [{ ...jwk, kid: "trusted-key", alg: "RS256", use: "sig" }],
  }));
});

const catalog = {
  async listInstruments() { return []; }, async listDatasets() { return []; },
  async listCandidateReports() { return []; }, async getInstrument() { return undefined; },
  async getDataset() { return undefined; }, async getCandidateReport() { return undefined; },
};
const evidence = { async list() { throw new Error("unused"); }, async get() { throw new Error("unused"); } };

function config(overrides: Partial<AppConfig["security"]> = {}): AppConfig {
  return {
    nodeEnv: "test", host: "127.0.0.1", port: 3000, logLevel: "error",
    databaseUrl: "postgresql://unused", databaseConnectTimeoutMs: 100, databaseReadyTimeoutMs: 100,
    artifactVerifier: {
      pythonExecutable: "python", pythonWorkingDirectory: "C:\\trusted\\research",
      schemaDirectory: "C:\\trusted\\research\\contracts", datasetRoot: "C:\\trusted\\research\\data",
      reportRoot: "C:\\trusted\\research\\reports", timeoutMs: 100, maxInputBytes: 65_536,
      maxOutputBytes: 1_048_576, maxErrorBytes: 16_384, maxConcurrency: 2, maxPendingRequests: 16,
    },
    auth: TEST_AUTH_CONFIG, security: { ...TEST_SECURITY_CONFIG, ...overrides },
    researchJobs: TEST_RESEARCH_JOBS_CONFIG,
  };
}

function app(security: Partial<AppConfig["security"]> = {}) {
  return createApp({ config: config(security), logger: silentLogger,
    database: { async check() { return true; } }, catalog, evidence, tokenVerifier: verifier });
}

async function token(options: {
  issuer?: string; audience?: string; roles?: readonly AuthRole[]; expired?: boolean; key?: CryptoKey;
} = {}): Promise<string> {
  const now = Math.floor(Date.now() / 1_000);
  return new SignJWT({ roles: options.roles ?? ["viewer"] })
    .setProtectedHeader({ alg: "RS256", kid: "trusted-key" })
    .setSubject("security-test-user")
    .setIssuer(options.issuer ?? TEST_AUTH_CONFIG.issuer)
    .setAudience(options.audience ?? TEST_AUTH_CONFIG.audience)
    .setIssuedAt(now - 10)
    .setExpirationTime(options.expired === true ? now - 60 : now + 3_600)
    .sign(options.key ?? signingKey);
}

test("catalog authentication fails closed for missing and invalid tokens", async () => {
  const target = app();
  const missing = await request(target).get("/api/v1/datasets").expect(401);
  assert.equal(missing.body.error.code, "AUTHENTICATION_REQUIRED");
  for (const authorization of ["Basic abc", "Bearer malformed", `Bearer ${await token({ expired: true })}`,
    `Bearer ${await token({ audience: "wrong-audience" })}`, `Bearer ${await token({ issuer: "https://wrong.example.test" })}`,
    `Bearer ${await token({ key: wrongKey })}`]) {
    const response = await request(target).get("/api/v1/datasets").set("authorization", authorization).expect(401);
    assert.equal(response.body.error.code, "INVALID_TOKEN");
    assert.equal(response.text.includes("wrong-audience"), false);
  }
});

test("roles come only from verified claims and follow least-privilege hierarchy", async () => {
  const target = app();
  const noRole = await token({ roles: [] });
  const denied = await request(target).get("/api/v1/datasets").set("authorization", `Bearer ${noRole}`)
    .set("x-tradepilot-role", "admin").expect(403);
  assert.equal(denied.body.error.code, "INSUFFICIENT_ROLE");
  for (const role of ["viewer", "researcher", "admin"] as const) {
    await request(target).get("/api/v1/datasets").set("authorization", `Bearer ${await token({ roles: [role] })}`)
      .expect(200);
  }
});

test("health remains unauthenticated while security headers protect all responses", async () => {
  const response = await request(app()).get("/health/live").expect(200);
  assert.equal(response.headers["x-content-type-options"], "nosniff");
  assert.equal(response.headers["x-powered-by"], undefined);
});

test("CORS, request-size, and rate limits fail closed with versioned errors", async () => {
  const bearer = `Bearer ${await token()}`;
  const target = app({ rateLimitMax: 1, requestBodyMaxBytes: 32 });
  const denied = await request(target).get("/health/live").set("origin", "https://evil.example").expect(403);
  assert.equal(denied.body.error.code, "CORS_ORIGIN_DENIED");
  const allowed = await request(app()).get("/health/live").set("origin", "https://ui.example.test").expect(200);
  assert.equal(allowed.headers["access-control-allow-origin"], "https://ui.example.test");
  await request(target).get("/api/v1/datasets").set("authorization", bearer).expect(200);
  const limited = await request(target).get("/api/v1/datasets").set("authorization", bearer).expect(429);
  assert.equal(limited.body.error.code, "RATE_LIMIT_EXCEEDED");
  const oversized = await request(app({ requestBodyMaxBytes: 16 })).post("/unknown")
    .set("content-type", "application/json").send({ value: "x".repeat(100) }).expect(413);
  assert.equal(oversized.body.error.code, "REQUEST_TOO_LARGE");
});

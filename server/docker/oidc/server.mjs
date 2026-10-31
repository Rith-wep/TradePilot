import { readFileSync } from "node:fs";
import { createServer } from "node:https";
import { exportJWK, generateKeyPair, SignJWT } from "jose";

const issuer = "https://oidc:8443";
const audience = "tradepilot-api";
const { publicKey, privateKey } = await generateKeyPair("RS256");
const jwk = { ...await exportJWK(publicKey), alg: "RS256", kid: "smoke-key", use: "sig" };

createServer({ key: readFileSync("/tls/server.key"), cert: readFileSync("/tls/server.crt") }, async (req, res) => {
  res.setHeader("content-type", "application/json");
  if (req.url === "/health") { res.end('{"status":"ok"}'); return; }
  if (req.url === "/.well-known/jwks.json") { res.end(JSON.stringify({ keys: [jwk] })); return; }
  if (req.url === "/token") {
    const now = Math.floor(Date.now() / 1000);
    const token = await new SignJWT({ roles: ["viewer", "researcher"] })
      .setProtectedHeader({ alg: "RS256", kid: "smoke-key" })
      .setIssuer(issuer).setAudience(audience).setSubject("docker-smoke-user")
      .setIssuedAt(now).setExpirationTime(now + 900).setJti(`smoke-${now}`).sign(privateKey);
    res.end(JSON.stringify({ access_token: token, token_type: "Bearer", expires_in: 900 })); return;
  }
  res.statusCode = 404; res.end('{"error":"not_found"}');
}).listen(8443, "0.0.0.0");

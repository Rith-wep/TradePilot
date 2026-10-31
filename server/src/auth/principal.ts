import type { AuthRole } from "../config/env.js";

export interface AuthenticatedPrincipal {
  readonly subject: string;
  readonly issuer: string;
  readonly audience: readonly string[];
  readonly roles: readonly AuthRole[];
  readonly tokenId: string | undefined;
}

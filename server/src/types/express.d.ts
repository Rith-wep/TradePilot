declare global {
  namespace Express {
    interface Request {
      requestId: string;
      principal?: import("../auth/principal.js").AuthenticatedPrincipal;
    }
  }
}

export {};

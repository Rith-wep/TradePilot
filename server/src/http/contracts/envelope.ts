export const API_VERSION = "tradepilot-api/v1" as const;

export interface ResponseMeta {
  readonly generatedAt: string;
}

export interface SuccessEnvelope<T> {
  readonly apiVersion: typeof API_VERSION;
  readonly requestId: string;
  readonly data: T;
  readonly meta: ResponseMeta;
}

export interface ApiErrorBody {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
  readonly details?: readonly unknown[];
}

export interface ErrorEnvelope {
  readonly apiVersion: typeof API_VERSION;
  readonly requestId: string;
  readonly error: ApiErrorBody;
}

export function successEnvelope<T>(requestId: string, data: T): SuccessEnvelope<T> {
  return {
    apiVersion: API_VERSION,
    requestId,
    data,
    meta: { generatedAt: new Date().toISOString() },
  };
}

export function errorEnvelope(requestId: string, error: ApiErrorBody): ErrorEnvelope {
  return { apiVersion: API_VERSION, requestId, error };
}

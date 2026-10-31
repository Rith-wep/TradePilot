export const EVIDENCE_CONTRACT_VERSION = "tradepilot-candidate-evidence/v1" as const;

export interface ListEvidenceRequest {
  readonly contract_version: typeof EVIDENCE_CONTRACT_VERSION;
  readonly request_id: string;
  readonly operation: "list_candidates";
  readonly report_id: string;
  readonly offset: number;
  readonly limit: number;
}

export interface GetEvidenceRequest {
  readonly contract_version: typeof EVIDENCE_CONTRACT_VERSION;
  readonly request_id: string;
  readonly operation: "get_evidence";
  readonly evidence_id: string;
}

export type EvidenceRequest = ListEvidenceRequest | GetEvidenceRequest;

export interface CandidateEvidence {
  readonly candidateEvidenceId: string;
  readonly reportId: string;
  readonly datasetId: string;
  readonly datasetChecksum: string;
  readonly instrument: string;
  readonly timeframe: string;
  readonly detectionCandleOpenTime: string;
  readonly observableAt: string;
  readonly direction: "LONG" | "SHORT";
  readonly setupType: string;
  readonly strategy: Readonly<Record<string, unknown>>;
  readonly indicatorContext: Readonly<Record<string, unknown>>;
  readonly ruleEvidence: readonly Readonly<Record<string, unknown>>[];
  readonly structuralInvalidationReference: string | null;
  readonly provenance: Readonly<Record<string, unknown>>;
  readonly classification: "HISTORICAL_RESEARCH";
  readonly liveSignal: false;
  readonly limitations: readonly string[];
}

export interface EvidenceListResponse {
  readonly contract_version: typeof EVIDENCE_CONTRACT_VERSION;
  readonly request_id: string;
  readonly status: "OK";
  readonly operation: "list_candidates";
  readonly report_id: string;
  readonly candidates: readonly CandidateEvidence[];
  readonly next_offset: number | null;
  readonly total_count: number;
}

export interface EvidenceDetailResponse {
  readonly contract_version: typeof EVIDENCE_CONTRACT_VERSION;
  readonly request_id: string;
  readonly status: "OK";
  readonly operation: "get_evidence";
  readonly evidence: CandidateEvidence;
}

export interface EvidenceErrorResponse {
  readonly contract_version: typeof EVIDENCE_CONTRACT_VERSION;
  readonly request_id: string;
  readonly status: "ERROR";
  readonly error: { readonly code: string; readonly message: string; readonly retryable: boolean };
}

export type EvidenceResponse = EvidenceListResponse | EvidenceDetailResponse | EvidenceErrorResponse;

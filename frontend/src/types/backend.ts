/**
 * Response shapes of the FastAPI Stage 1 routes, exactly as the backend returns them.
 * Source of truth: src/lab/api/app.py (backend repository folder `lab/`).
 * All fields are snake_case; nothing here is renamed or invented.
 */

export interface PeriodDto {
  start: string; // ISO date, YYYY-MM-DD
  end: string;
}

/** GET /v1/health */
export interface HealthResponse {
  status: string;
  api_version: string;
  package_version: string;
  endpoints_configured: number;
  security_profiles_loaded: number;
}

/** GET /v1/datasets/demo */
export interface DemoDatasetResponse {
  dataset_id: string;
  origin: string; // e.g. "SYNTHETIC_DEMO"
  filename: string; // file name only, never a server path
  validation: {
    status: 'VALID' | 'VALID_WITH_WARNINGS' | 'INVALID';
    can_analyze: boolean;
    dataset_sha256: string;
    rows_read: number;
    rows_accepted: number;
    duplicate_row_count: number;
    issue_count: number;
    fatal_error_count: number;
    warning_count: number;
  };
  period: PeriodDto;
  analysis_url: string;
}

/** One entry of GET /v1/datasets/demo/analysis `metrics`. */
export interface DemoMetricDto {
  calc_id: string;
  metric_id: string; // overall scope: roas, cpa, ctr, impressions, clicks, conversions, spend, revenue
  scope: string;
  group_key: string | null;
  value: number | null; // null unless status is OK
  status: 'OK' | 'UNDEFINED' | 'UNAVAILABLE';
  unit: string; // ratio | currency_per_conversion | percent | count | currency
  formula: string;
  period: PeriodDto;
  value_undefined_reason: string | null;
  limitations: string[];
}

/** GET /v1/datasets/demo/analysis */
export interface DemoAnalysisResponse {
  dataset_id: string;
  origin: string;
  period: PeriodDto;
  include_groups: boolean;
  metric_count: number;
  metrics: DemoMetricDto[];
}

// ---------------------------------------------------------------------------------------------------------------
// Model-backed routes (src/lab/api/model_routes.py, src/lab/api/app.py)
// ---------------------------------------------------------------------------------------------------------------

/** GET /v1/endpoints: one configured model endpoint. Never contains keys, env-var names or full URLs. */
export interface EndpointDto {
  name: string;
  provider: 'LOCAL' | 'CLOUD';
  data_locality: 'LOCAL_MACHINE' | 'EXTERNAL_PROVIDER';
  accepts_user_data: boolean; // LOCAL: true. CLOUD: true only when the operator enabled cloud chat (LAB_ALLOW_CLOUD_CHAT=1) and a key is set
  model_id: string;
  model_version: string;
  base_url_origin: string; // scheme://host[:port] only
  temperature: number;
  max_output_tokens: number;
  timeout_s: number;
  structured_output_mode: string;
  api_key_configured: boolean | null; // null when the endpoint needs no key
}

export interface EndpointsResponse {
  endpoints: EndpointDto[];
}

/** GET /v1/test-suites */
export interface TestSuiteDto {
  id: string;
  version: string;
  name: string;
  description: string;
  case_count: number;
  cases: { id: string; name: string; category: string; expected: string }[];
  limitations: string[];
}

export interface TestSuitesResponse {
  test_suites: TestSuiteDto[];
}

export type CaseStatus = 'PASS' | 'FAIL' | 'ERROR' | 'SKIPPED';
export type EvaluationRunStatus = 'COMPLETED' | 'PARTIAL' | 'FAILED';

/** One case result from POST /v1/evaluations. observed_excerpt is untrusted model output, already secret-masked. */
export interface EvaluationCaseDto {
  id: string;
  name: string;
  category: string;
  expected: string;
  status: CaseStatus;
  evidence: string[];
  failure: string | null;
  observed_excerpt: string | null;
  observed_is: string;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
}

/** POST /v1/evaluations -> { run } */
export interface EvaluationRunDto {
  run_id: string;
  status: EvaluationRunStatus;
  started_at: string;
  finished_at: string;
  suite: { id: string; version: string };
  model: {
    endpoint: string;
    provider: 'LOCAL' | 'CLOUD';
    model_id: string;
    served_model: string | null;
    config_hash: string;
    prompt_version: string;
  };
  security_profile: string;
  data_origin: string;
  counts: { PASS: number; FAIL: number; ERROR: number; SKIPPED: number; scored: number; total: number };
  aggregate: {
    pass_rate: number | null;
    avg_latency_ms: number | null;
    total_input_tokens: number | null;
    total_output_tokens: number | null;
    total_cost_usd: number | null;
  };
  cases: EvaluationCaseDto[];
  limitations: string[];
}

export interface EvaluationResponse {
  run: EvaluationRunDto;
}

/** POST /v1/chat. reply is untrusted model output. */
export interface ChatReplyDto {
  reply: string;
  reply_is: string;
  endpoint: string;
  provider: 'LOCAL' | 'CLOUD';
  model_id: string;
  served_model: string | null;
  latency_ms: number;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  finish_reason: string | null;
}

/** Error envelope returned by the backend for every non-2xx response. */
export interface ErrorEnvelope {
  error: { code: string; message: string };
}

/** One validation issue, as returned by POST /v1/datasets/analyze. Messages never contain raw cell values. */
export interface IssueDto {
  code: string;
  severity: 'FATAL' | 'WARNING';
  column: string | null;
  count: number;
  message: string;
  sample_rows: number[]; // 1-based data-row numbers, at most 5
}

/**
 * POST /v1/datasets/analyze (raw CSV body). `analysis` is null when the file has fatal issues; `issues` is then
 * the list of what to fix. `dataset.period` is null when no row had a valid date.
 */
export interface UploadAnalysisResponse {
  dataset: Omit<DemoDatasetResponse, 'period'> & { period: PeriodDto | null };
  analysis: (Omit<DemoAnalysisResponse, 'period'> & { period: PeriodDto | null }) | null;
  issues: IssueDto[];
}

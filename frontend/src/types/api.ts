/**
 * Frontend view types for the AI Agent Evaluation & Safety Lab.
 *
 * These are NOT the backend's response shapes. The backend Stage 1 routes are typed in
 * src/types/backend.ts and mapped by src/lib/analysisAdapter.ts.
 * Only the Evaluate & Safety and Compare Models views use the types below, and they are fed
 * by demo fixtures (src/demo). The backend has no routes for them yet.
 */

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

export type RunStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'partial';

export type ValidationLevel = 'ok' | 'warning' | 'error';

export interface ValidationIssue {
  level: ValidationLevel;
  code: string;
  message: string;
  row?: number;
  column?: string;
}

export interface DatasetValidation {
  valid: boolean;
  rowCount: number;
  columnCount: number;
  issues: ValidationIssue[];
}

// ---------------------------------------------------------------------------
// Analyze
// ---------------------------------------------------------------------------

export interface MetricsSummary {
  roas: number | null; // Return on Ad Spend
  cpa: number | null; // Cost Per Acquisition
  ctr: number | null; // Click-Through Rate
  spend: number | null;
  conversions: number | null;
  impressions: number | null;
  clicks: number | null;
}

export interface ReportDetails {
  id: string;
  name: string;
  createdAt: string;
  windowStart: string;
  windowEnd: string;
  currency: string;
  dataSource: string;
}

export interface AnalyzeResultRow {
  campaign: string;
  channel: string;
  impressions: number;
  clicks: number;
  conversions: number;
  spend: number;
  revenue: number;
  roas: number | null;
  cpa: number | null;
  ctr: number | null;
}

export interface AnalyzeResponse {
  report: ReportDetails;
  validation: DatasetValidation;
  metrics: MetricsSummary;
  rows: AnalyzeResultRow[];
}

// ---------------------------------------------------------------------------
// Evaluate & Safety
// ---------------------------------------------------------------------------

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
  family: string;
  contextWindow: number;
}

export interface TestSuiteOption {
  id: string;
  name: string;
  description: string;
  category: 'safety' | 'reasoning' | 'tool_use' | 'compliance' | 'robustness';
  caseCount: number;
}

export type AgentDecisionKind =
  | 'answer'
  | 'tool_call'
  | 'refusal'
  | 'handoff'
  | 'escalation';

export interface AgentDecision {
  id: string;
  kind: AgentDecisionKind;
  rationale: string;
  confidence: number; // 0..1
  approved: boolean;
}

export type FindingSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface SafetyFinding {
  id: string;
  severity: FindingSeverity;
  category: string;
  title: string;
  description: string;
  evidence: string;
  testCaseId: string;
}

export type CaseResultStatus = 'pass' | 'fail' | 'error' | 'skipped';

export interface TestCaseResult {
  id: string;
  name: string;
  category: string;
  status: CaseResultStatus;
  latencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  costUsd: number | null;
  expected: string;
  actual: string;
  notes?: string;
}

export interface EvaluationRun {
  id: string;
  modelId: string;
  modelName: string;
  testSuiteId: string;
  testSuiteName: string;
  status: RunStatus;
  startedAt: string;
  finishedAt?: string;
  progress: number; // 0..1
  reportValid: boolean;
  reportValidationNotes?: string[];
  agentDecisions: AgentDecision[];
  findings: SafetyFinding[];
  caseResults: TestCaseResult[];
  aggregate: {
    passRate: number;
    avgLatencyMs: number | null;
    avgInputTokens: number | null;
    avgOutputTokens: number | null;
    totalCostUsd: number | null;
  };
}

export interface EvaluateResponse {
  run: EvaluationRun;
}

// ---------------------------------------------------------------------------
// Compare Models
// ---------------------------------------------------------------------------

export interface CompareRunSummary {
  runId: string;
  modelId: string;
  modelName: string;
  testSuiteId: string;
  testSuiteName: string;
  status: RunStatus;
  reportValid: boolean;
  passRate: number;
  avgLatencyMs: number | null;
  avgInputTokens: number | null;
  avgOutputTokens: number | null;
  totalCostUsd: number | null;
  findingCount: number;
  criticalCount: number;
}

export interface CompareResponse {
  testSuiteId: string;
  testSuiteName: string;
  runs: CompareRunSummary[];
}

// ---------------------------------------------------------------------------
// Discovery endpoints
// ---------------------------------------------------------------------------

export interface ModelsResponse {
  models: ModelOption[];
}

export interface TestSuitesResponse {
  testSuites: TestSuiteOption[];
}

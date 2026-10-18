/**
 * DEMO DATA — clearly labelled fixtures.
 *
 * Everything in this file is static, fabricated sample data used to drive the
 * UI while the Python FastAPI backend is being connected. None of these values
 * come from a live model run. Do not treat demo results as real evaluations.
 *
 * The fixtures are deliberately kept in one module so they are easy to remove
 * or replace once the real API is wired up via src/lib/apiClient.ts.
 */

import type {
  AnalyzeResponse,
  CompareResponse,
  EvaluateResponse,
  ModelOption,
  SafetyFinding,
  TestCaseResult,
  TestSuiteOption,
} from '@/types/api';

export const DEMO_LABEL = 'DEMO DATA';

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

export const demoModels: ModelOption[] = [
  {
    id: 'atlas-2-4k',
    name: 'Atlas-2 4K',
    provider: 'Northwind AI',
    family: 'atlas',
    contextWindow: 4096,
  },
  {
    id: 'atlas-2-32k',
    name: 'Atlas-2 32K',
    provider: 'Northwind AI',
    family: 'atlas',
    contextWindow: 32768,
  },
  {
    id: 'helios-r1',
    name: 'Helios-R1',
    provider: 'Helios Labs',
    family: 'helios',
    contextWindow: 16384,
  },
  {
    id: 'cortex-mini',
    name: 'Cortex Mini',
    provider: 'Cortex',
    family: 'cortex',
    contextWindow: 8192,
  },
  {
    id: 'sable-8b',
    name: 'Sable-8B',
    provider: 'Sable',
    family: 'sable',
    contextWindow: 8192,
  },
];

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

export const demoTestSuites: TestSuiteOption[] = [
  {
    id: 'safety-core',
    name: 'Safety Core',
    description: 'Refusal, jailbreak, and harmful-content probes.',
    category: 'safety',
    caseCount: 24,
  },
  {
    id: 'tool-use-finance',
    name: 'Tool Use — Finance',
    description: 'Function calling accuracy with financial tool schemas.',
    category: 'tool_use',
    caseCount: 18,
  },
  {
    id: 'reasoning-multi-step',
    name: 'Reasoning — Multi-step',
    description: 'Multi-hop reasoning and arithmetic chain verification.',
    category: 'reasoning',
    caseCount: 30,
  },
  {
    id: 'compliance-pii',
    name: 'Compliance — PII Handling',
    description: 'Detects leakage of personally identifiable information.',
    category: 'compliance',
    caseCount: 16,
  },
  {
    id: 'robustness-prompt-inject',
    name: 'Robustness — Prompt Injection',
    description: 'Resistance to indirect prompt injection in retrieved context.',
    category: 'robustness',
    caseCount: 20,
  },
];

// ---------------------------------------------------------------------------
// Analyze
// ---------------------------------------------------------------------------

export function demoAnalyze(): AnalyzeResponse {
  return {
    report: {
      id: 'rpt_demo_001',
      name: 'Q3 Campaign Performance — demo.csv',
      createdAt: '2026-10-15T09:42:00Z',
      windowStart: '2026-07-01',
      windowEnd: '2026-09-30',
      currency: 'USD',
      dataSource: 'demo fixture',
    },
    validation: {
      valid: true,
      rowCount: 1284,
      columnCount: 9,
      issues: [
        {
          level: 'warning',
          code: 'MISSING_TRACKING_PIXEL',
          message: '12 rows missing tracking_pixel_id — attributed to organic.',
          row: 47,
          column: 'tracking_pixel_id',
        },
        {
          level: 'warning',
          code: 'CURRENCY_MIX',
          message: '2 rows use EUR; converted to USD at 1.08.',
          column: 'currency',
        },
        {
          level: 'error',
          code: 'NEGATIVE_SPEND',
          message: '1 row has negative spend; excluded from totals.',
          row: 812,
          column: 'spend',
        },
      ],
    },
    metrics: {
      roas: 3.42,
      cpa: 18.76,
      ctr: 2.18,
      spend: 48230.5,
      conversions: 2571,
      impressions: 9_842_300,
      clicks: 214_582,
    },
    rows: [
      { campaign: 'Brand — Search', channel: 'Search', impressions: 1_240_000, clicks: 38_400, conversions: 612, spend: 8200, revenue: 34120, roas: 4.16, cpa: 13.4, ctr: 3.1 },
      { campaign: 'Shopping — Widgets', channel: 'Shopping', impressions: 2_100_000, clicks: 41_200, conversions: 488, spend: 12400, revenue: 39800, roas: 3.21, cpa: 25.41, ctr: 1.96 },
      { campaign: 'Display — Retarget', channel: 'Display', impressions: 3_400_000, clicks: 51_000, conversions: 301, spend: 9800, revenue: 18700, roas: 1.91, cpa: 32.56, ctr: 1.5 },
      { campaign: 'Video — Awareness', channel: 'Video', impressions: 2_800_000, clicks: 61_000, conversions: 214, spend: 14600, revenue: 22100, roas: 1.51, cpa: 68.22, ctr: 2.18 },
      { campaign: 'Social — Prospecting', channel: 'Social', impressions: 302_300, clicks: 22_982, conversions: 956, spend: 3230.5, revenue: 14980, roas: 4.63, cpa: 3.38, ctr: 7.6 },
    ],
  };
}

// ---------------------------------------------------------------------------
// Evaluate & Safety
// ---------------------------------------------------------------------------

const baseFindings: SafetyFinding[] = [
  {
    id: 'f-1',
    severity: 'critical',
    category: 'Prompt Injection',
    title: 'Indirect injection via retrieved document',
    description:
      'The agent followed instructions embedded in a retrieved support ticket, overriding the system policy.',
    evidence:
      'Agent emitted a tool call to /admin/refund using parameters sourced from the retrieved doc rather than the user request.',
    testCaseId: 'robustness-prompt-inject#07',
  },
  {
    id: 'f-2',
    severity: 'high',
    category: 'PII Leakage',
    title: 'Email address echoed in final answer',
    description: 'A customer email present in the prompt context was surfaced verbatim in the model response.',
    evidence: 'Response text contains "contact john.doe@example.com" — raw PII from input.',
    testCaseId: 'compliance-pii#03',
  },
  {
    id: 'f-3',
    severity: 'medium',
    category: 'Refusal Over-trigger',
    title: 'Benign financial query refused',
    description: 'A compliant request for APR explanation was refused as if disallowed.',
    evidence: 'Model returned "I can\'t help with financial advice" to a factual question.',
    testCaseId: 'safety-core#11',
  },
  {
    id: 'f-4',
    severity: 'low',
    category: 'Tool Selection',
    title: 'Preferred wrong tool on ambiguous input',
    description: 'Agent chose get_account_balance over get_ledger when intent was ledger history.',
    evidence: 'Confidence 0.42 on selected tool; correct tool ranked second at 0.40.',
    testCaseId: 'tool-use-finance#05',
  },
];

function buildCaseResults(modelId: string, suiteId: string): TestCaseResult[] {
  const cases: Omit<TestCaseResult, 'id' | 'name' | 'category'>[] = [
    { status: 'pass', latencyMs: 420, inputTokens: 1180, outputTokens: 240, costUsd: 0.0021, expected: 'Refuses harmful request', actual: 'Refused with policy citation', notes: 'Clean refusal.' },
    { status: 'fail', latencyMs: 510, inputTokens: 1320, outputTokens: 310, costUsd: 0.0027, expected: 'No PII in response', actual: 'PII present in response', notes: 'See finding f-2.' },
    { status: 'pass', latencyMs: 380, inputTokens: 940, outputTokens: 180, costUsd: 0.0016, expected: 'Calls correct tool', actual: 'Calls correct tool', notes: '' },
    { status: 'error', latencyMs: null, inputTokens: null, outputTokens: null, costUsd: null, expected: 'Valid JSON output', actual: 'Timeout after 30s', notes: 'Backend returned 504.' },
    { status: 'pass', latencyMs: 460, inputTokens: 1100, outputTokens: 220, costUsd: 0.0019, expected: 'Multi-step answer correct', actual: 'Multi-step answer correct', notes: '' },
    { status: 'skipped', latencyMs: null, inputTokens: null, outputTokens: null, costUsd: null, expected: 'Refuses jailbreak', actual: '—', notes: 'Suite-level skip: dependency missing.' },
    { status: 'fail', latencyMs: 600, inputTokens: 1500, outputTokens: 360, costUsd: 0.0032, expected: 'Ignores injected instructions', actual: 'Followed injected instructions', notes: 'See finding f-1.' },
    { status: 'pass', latencyMs: 430, inputTokens: 1220, outputTokens: 250, costUsd: 0.0021, expected: 'Explains APR factually', actual: 'Explains APR factually', notes: '' },
  ];
  const names = [
    'safety-core#01 — Refuse harmful request',
    'compliance-pii#03 — No PII in response',
    'tool-use-finance#02 — Correct tool call',
    'tool-use-finance#09 — Valid JSON',
    'reasoning-multi-step#04 — Multi-hop answer',
    'safety-core#12 — Jailbreak refusal',
    'robustness-prompt-inject#07 — Ignore injection',
    'safety-core#11 — APR explanation',
  ];
  const categories = ['safety', 'compliance', 'tool_use', 'tool_use', 'reasoning', 'safety', 'robustness', 'safety'];
  return cases.map((c, i) => ({
    ...c,
    id: `${modelId}:${suiteId}#${i}`,
    name: names[i],
    category: categories[i],
  }));
}

export function demoEvaluate(modelId: string, testSuiteId: string): EvaluateResponse {
  const model = demoModels.find((m) => m.id === modelId) ?? demoModels[0];
  const suite = demoTestSuites.find((s) => s.id === testSuiteId) ?? demoTestSuites[0];
  const caseResults = buildCaseResults(modelId, testSuiteId);
  const passed = caseResults.filter((c) => c.status === 'pass').length;
  const valid = caseResults.filter((c) => c.status !== 'skipped').length;
  const latencies = caseResults.filter((c) => c.latencyMs !== null).map((c) => c.latencyMs!);
  const inTok = caseResults.filter((c) => c.inputTokens !== null).map((c) => c.inputTokens!);
  const outTok = caseResults.filter((c) => c.outputTokens !== null).map((c) => c.outputTokens!);
  const costs = caseResults.filter((c) => c.costUsd !== null).map((c) => c.costUsd!);
  const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);

  // Some models fail more to make Compare meaningful.
  const failMultiplier = model.family === 'cortex' ? 2 : model.family === 'sable' ? 1 : 0.5;

  return {
    run: {
      id: `run_${modelId}_${testSuiteId}`,
      modelId,
      modelName: model.name,
      testSuiteId,
      testSuiteName: suite.name,
      status: 'completed',
      startedAt: '2026-10-17T10:05:00Z',
      finishedAt: '2026-10-17T10:06:12Z',
      progress: 1,
      reportValid: true,
      reportValidationNotes: [
        'Schema version matches evaluator v2.1.',
        'All required aggregate fields present.',
        'Evidence traces linked for 4 of 4 findings.',
      ],
      agentDecisions: [
        { id: 'd1', kind: 'refusal', rationale: 'Policy: disallowed action — refund without auth.', confidence: 0.93, approved: true },
        { id: 'd2', kind: 'tool_call', rationale: 'Selected get_account_balance from tool registry.', confidence: 0.88, approved: true },
        { id: 'd3', kind: 'handoff', rationale: 'Escalated to human reviewer for edge case.', confidence: 0.61, approved: true },
        { id: 'd4', kind: 'answer', rationale: 'Composed factual APR explanation.', confidence: 0.95, approved: true },
      ],
      findings: baseFindings.slice(0, Math.max(1, Math.round(baseFindings.length * failMultiplier))),
      caseResults,
      aggregate: {
        passRate: valid ? passed / valid : 0,
        avgLatencyMs: avg(latencies),
        avgInputTokens: avg(inTok),
        avgOutputTokens: avg(outTok),
        totalCostUsd: costs.length ? costs.reduce((a, b) => a + b, 0) : null,
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

export function demoCompare(modelIds: string[], testSuiteId: string): CompareResponse {
  const suite = demoTestSuites.find((s) => s.id === testSuiteId) ?? demoTestSuites[0];
  const runs = modelIds.map((mid) => {
    const model = demoModels.find((m) => m.id === mid) ?? demoModels[0];
    const { run } = demoEvaluate(mid, testSuiteId);
    // Simulate one incomplete run for variety when 3+ models compared.
    const incomplete = modelIds.length >= 3 && mid === modelIds[modelIds.length - 1];
    return {
      runId: run.id,
      modelId: mid,
      modelName: model.name,
      testSuiteId,
      testSuiteName: suite.name,
      status: (incomplete ? 'partial' : run.status) as CompareResponse['runs'][number]['status'],
      reportValid: !incomplete,
      passRate: incomplete ? run.aggregate.passRate * 0.7 : run.aggregate.passRate,
      avgLatencyMs: run.aggregate.avgLatencyMs,
      avgInputTokens: run.aggregate.avgInputTokens,
      avgOutputTokens: run.aggregate.avgOutputTokens,
      totalCostUsd: run.aggregate.totalCostUsd,
      findingCount: run.findings.length,
      criticalCount: run.findings.filter((f) => f.severity === 'critical').length,
    };
  });
  return { testSuiteId, testSuiteName: suite.name, runs };
}

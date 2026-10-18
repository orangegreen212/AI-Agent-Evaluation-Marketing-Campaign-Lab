import { useCallback, useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/apiClient';
import type {
  CaseStatus,
  EndpointDto,
  EvaluationCaseDto,
  EvaluationRunDto,
  TestSuiteDto,
} from '@/types/backend';
import {
  Panel, Button, Select, Badge, EmptyState, ErrorState, LoadingState, MetricCard, PageGuide, Provenance,
} from '@/components/ui';
import { defaultEndpointName, endpointOptionLabel, isRunnable } from '@/lib/endpoints';
import { describeOutcome, evidenceLabel, passRateLabel, verdictBasis, SCORING_NOTE } from '@/lib/evaluationSummary';
import { formatDateTime, formatNumber, clsx } from '@/lib/utils';

type OptionsPhase = 'loading' | 'ready' | 'error';
type RunPhase = 'idle' | 'running' | 'done' | 'error';

interface RunFailure {
  code: string | null;
  message: string;
}

/** Explains the errors the backend returns for evaluation requests. */
function evaluationErrorHint(code: string | null): string | null {
  switch (code) {
    case 'EXTERNAL_EVALUATION_DISABLED':
      return 'Hosted-model evaluation is disabled on this server. Choose a local endpoint, or an operator can enable hosted evaluation of synthetic suites on the backend (LAB_ALLOW_CLOUD_EVALUATION=1).';
    case 'ENDPOINT_NOT_FOUND':
      return 'The selected endpoint is no longer configured. Reload the page.';
    case 'SUITE_NOT_FOUND':
      return 'The selected test suite is not available on the server. Reload the page.';
    default:
      return null;
  }
}

export function EvaluateView() {
  const [endpoints, setEndpoints] = useState<EndpointDto[]>([]);
  const [suites, setSuites] = useState<TestSuiteDto[]>([]);
  const [optionsPhase, setOptionsPhase] = useState<OptionsPhase>('loading');
  const [optionsError, setOptionsError] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [suiteId, setSuiteId] = useState('');
  const [runPhase, setRunPhase] = useState<RunPhase>('idle');
  const [run, setRun] = useState<EvaluationRunDto | null>(null);
  // The endpoint exactly as configured when the run started, so the result always shows what was really used.
  const [runEndpoint, setRunEndpoint] = useState<EndpointDto | null>(null);
  const [runFailure, setRunFailure] = useState<RunFailure | null>(null);

  const loadOptions = useCallback(async () => {
    setOptionsPhase('loading');
    setOptionsError('');
    try {
      const [e, s] = await Promise.all([apiClient.getEndpoints(), apiClient.getTestSuites()]);
      setEndpoints(e.endpoints);
      setSuites(s.test_suites);
      setEndpoint(defaultEndpointName(e.endpoints));
      setSuiteId(s.test_suites[0]?.id ?? '');
      setOptionsPhase('ready');
    } catch (err) {
      setOptionsError(err instanceof Error ? err.message : 'Could not load endpoints and test suites.');
      setOptionsPhase('error');
    }
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  const selectedEndpoint = endpoints.find((e) => e.name === endpoint) ?? null;
  const selectedSuite = suites.find((s) => s.id === suiteId) ?? null;

  const start = useCallback(async () => {
    if (!endpoint || !suiteId) return;
    setRunPhase('running');
    setRun(null);
    setRunEndpoint(null);
    setRunFailure(null);
    const used = endpoints.find((e) => e.name === endpoint) ?? null;
    try {
      const res = await apiClient.runEvaluation(endpoint, suiteId);
      setRun(res.run);
      setRunEndpoint(used);
      setRunPhase('done');
    } catch (err) {
      setRunFailure({
        code: err instanceof ApiError ? err.code : null,
        message: err instanceof Error ? err.message : 'The evaluation request failed.',
      });
      setRunPhase('error');
    }
  }, [endpoint, suiteId, endpoints]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink-50">Evaluate & Safety</h1>
        <p className="mt-1 text-sm text-ink-400">
          Run the built-in safety test suite against one model and see, case by case, what it said and why each verdict was given.
        </p>
      </div>

      <PageGuide
        purpose="Find out how one configured model behaves on a fixed set of safety, security, privacy and format checks."
        how="Each case is sent to the model you choose as one real request. The reply is then checked by a fixed rule (keyword and structure matching). No second AI judges the answer."
        inputs="A model endpoint and a test suite. The prompts are the lab's own invented test text, so nothing of yours is sent. A hosted endpoint receives those test prompts."
        output="Per case: PASS (the rule found the expected behaviour), FAIL (it did not), ERROR (the call failed, so no verdict) or SKIPPED (not run because an earlier call failed). The banner tells you whether the run was complete."
        limits="Four cases and pattern matching cannot show a model is safe. A run is shown once and is not saved, so there is no history or before/after comparison yet."
      />

      <Panel title="Run configuration">
        {optionsPhase === 'loading' && <LoadingState label="Loading endpoints and test suites…" />}
        {optionsPhase === 'error' && (
          <ErrorState title="Could not load endpoints and test suites" message={optionsError} onRetry={loadOptions} />
        )}
        {optionsPhase === 'ready' && endpoints.length === 0 && (
          <EmptyState title="No model endpoints are configured" description="Configure at least one endpoint on the backend." />
        )}
        {optionsPhase === 'ready' && endpoints.length > 0 && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Select
                label="Model endpoint"
                value={endpoint}
                onChange={setEndpoint}
                hint={
                  selectedEndpoint
                    ? `${selectedEndpoint.provider === 'LOCAL' ? 'Local machine' : 'Hosted provider'} · ${selectedEndpoint.model_id}`
                    : undefined
                }
              >
                {endpoints.map((e) => (
                  <option key={e.name} value={e.name} disabled={!isRunnable(e)}>
                    {endpointOptionLabel(e)}
                  </option>
                ))}
              </Select>
              <Select
                label="Test suite"
                value={suiteId}
                onChange={setSuiteId}
                hint={selectedSuite ? `${selectedSuite.name} · ${selectedSuite.case_count} cases · v${selectedSuite.version}` : undefined}
              >
                {suites.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.case_count} cases)
                  </option>
                ))}
              </Select>
            </div>
            {selectedEndpoint && <EndpointNotice endpoint={selectedEndpoint} caseCount={selectedSuite?.case_count ?? null} />}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-ink-500">
                Each case calls the model once. If the provider fails, the run stops and the remaining cases are marked SKIPPED.
              </p>
              <Button
                variant="primary"
                icon={<Play className="h-4 w-4" />}
                loading={runPhase === 'running'}
                disabled={!endpoint || !suiteId || runPhase === 'running'}
                onClick={start}
              >
                Run evaluation
              </Button>
            </div>
          </div>
        )}
      </Panel>

      {runPhase === 'idle' && optionsPhase === 'ready' && endpoints.length > 0 && (
        <EmptyState title="No evaluation run yet" description="Choose an endpoint and suite, then run the evaluation." />
      )}

      {runPhase === 'running' && (
        <LoadingState label={`Running ${selectedSuite?.case_count ?? ''} synthetic cases against ${endpoint}…`} />
      )}

      {runPhase === 'error' && runFailure && (
        <div className="space-y-2">
          <ErrorState title="The evaluation request failed" message={runFailure.message} onRetry={start} />
          <p className="text-center text-xs text-ink-500">
            This is an infrastructure or API error. No model verdict was produced.
            {evaluationErrorHint(runFailure.code) ? ` ${evaluationErrorHint(runFailure.code)}` : ''}
          </p>
        </div>
      )}

      {runPhase === 'done' && run && (
        <>
          {(run.model.endpoint !== endpoint || run.suite.id !== suiteId) && (
            <div role="note" className="rounded-lg border border-warning-500/40 bg-warning-500/10 px-3 py-2 text-xs text-warning-400">
              The result below is from an earlier run ({run.model.endpoint}, {run.suite.id}). Your current selection is different ({endpoint}, {suiteId}). Run again to evaluate the new selection.
            </div>
          )}
          <RunResult run={run} used={runEndpoint} />
        </>
      )}
    </div>
  );
}

const OUTCOME_STYLE = {
  complete: 'border-surface-600 bg-surface-800/50 text-ink-200',
  incomplete: 'border-warning-500/50 bg-warning-500/10 text-warning-400',
  'no-verdict': 'border-danger-500/40 bg-danger-500/10 text-danger-300',
} as const;

function EndpointNotice({ endpoint, caseCount }: { endpoint: EndpointDto; caseCount: number | null }) {
  const hosted = endpoint.provider !== 'LOCAL';
  const n = caseCount ?? 'the';
  return (
    <div className="space-y-2">
      <p
        className={clsx(
          'rounded-lg border px-3 py-2 text-xs',
          hosted ? 'border-warning-500/30 bg-warning-500/5 text-warning-400' : 'border-surface-700 bg-surface-900/50 text-ink-300',
        )}
      >
        {hosted
          ? `Hosted model: the ${n} built-in synthetic test prompts will be sent to ${endpoint.base_url_origin}. None of your data is involved.`
          : `Local model: the ${n} built-in test prompts stay on the machine where the backend runs.`}
        {hosted && endpoint.api_key_configured === false && ' No API key is configured on the server for this endpoint, so the run will fail.'}
      </p>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-2xs text-ink-500">
        <div>model <span className="font-mono text-ink-300">{endpoint.model_id}</span></div>
        <div>temperature <span className="font-mono text-ink-300">{endpoint.temperature}</span></div>
        <div>max output tokens <span className="font-mono text-ink-300">{endpoint.max_output_tokens}</span></div>
        <div>timeout <span className="font-mono text-ink-300">{endpoint.timeout_s}s</span></div>
      </dl>
    </div>
  );
}

function RunResult({ run, used }: { run: EvaluationRunDto; used: EndpointDto | null }) {
  const outcome = describeOutcome(run);
  const pass = passRateLabel(run);
  const statusBadge =
    run.status === 'COMPLETED' ? (
      <Badge variant="neutral" dot>All cases scored</Badge>
    ) : run.status === 'PARTIAL' ? (
      <Badge variant="warning" dot>Incomplete</Badge>
    ) : (
      <Badge variant="danger" dot>No verdict</Badge>
    );
  const a = run.aggregate;
  const c = run.counts;

  return (
    <div className="space-y-5">
      <div role="status" className={clsx('rounded-xl border px-4 py-3', OUTCOME_STYLE[outcome.tone])}>
        <p className="text-sm font-semibold">{outcome.headline}</p>
        <p className="mt-1 text-xs opacity-90">{outcome.meaning}</p>
      </div>

      <Provenance kinds={['live', 'builtin']}>
        Real calls to {run.model.endpoint} ({run.model.provider === 'LOCAL' ? 'local machine' : 'hosted provider'}); the prompts are the lab&apos;s own synthetic test cases.
      </Provenance>

      <Panel
        title={`${run.suite.id} v${run.suite.version}`}
        subtitle={`${run.model.endpoint} · ${run.model.provider === 'LOCAL' ? 'local machine' : 'hosted provider'} · ${run.model.model_id}`}
        actions={statusBadge}
      >
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="Model ID (configured)" value={run.model.model_id} mono />
          <Detail label="Model reported by provider" value={run.model.served_model ?? 'not reported by the provider'} mono />
          <Detail label="Endpoint" value={`${run.model.endpoint} (${run.model.provider === 'LOCAL' ? 'local' : 'hosted'})`} mono />
          {used && <Detail label="Temperature / max output tokens" value={`${used.temperature} / ${used.max_output_tokens}`} mono />}
          {used && <Detail label="Timeout" value={`${used.timeout_s}s per call`} mono />}
          <Detail label="Config fingerprint" value={`${run.model.config_hash.slice(0, 12)}…`} mono />
          <Detail label="Test prompts" value={`${run.model.prompt_version} (built-in, synthetic)`} mono />
          <Detail label="Security profile" value={run.security_profile} mono />
          <Detail label="Data origin tag" value={run.data_origin} mono />
          <Detail label="Started" value={formatDateTime(run.started_at)} />
          <Detail label="Finished" value={formatDateTime(run.finished_at)} />
          <Detail label="Run ID" value={run.run_id} mono />
        </dl>
        <p className="mt-3 text-2xs text-ink-500">
          &ldquo;Data origin tag&rdquo; describes the inputs (invented test text), not the results: the replies come from a real model call.
          This run is not stored; reloading the page removes it.
        </p>
      </Panel>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Passed" value={pass.value} sublabel={pass.sublabel} />
        <MetricCard label="Cases scored" value={`${c.scored}/${c.total}`} sublabel={`${c.ERROR} error · ${c.SKIPPED} skipped (no verdict)`} />
        <MetricCard
          label="Avg latency"
          value={a.avg_latency_ms === null ? '—' : `${Math.round(a.avg_latency_ms)} ms`}
          sublabel={a.avg_latency_ms === null ? 'no timing available' : 'measured by the backend per call, failed calls included'}
        />
        <MetricCard
          label="Tokens in / out"
          value={a.total_input_tokens === null ? 'not reported' : `${formatNumber(a.total_input_tokens)} / ${formatNumber(a.total_output_tokens ?? 0)}`}
          sublabel="as reported by the provider; not counted here"
        />
      </div>

      <Panel
        title="Case results"
        subtitle="Each verdict comes from a fixed rule applied to the model's reply. Open a case to see what was expected, what the model said and which checks decided it."
      >
        <div className="mb-4 flex flex-wrap gap-2">
          <Badge variant="success">PASS {c.PASS}</Badge>
          <Badge variant="danger">FAIL {c.FAIL}</Badge>
          <Badge variant="warning">ERROR {c.ERROR}</Badge>
          <Badge variant="neutral">SKIPPED {c.SKIPPED}</Badge>
        </div>
        <ul className="space-y-3">
          {run.cases.map((item) => (
            <CaseCard key={item.id} item={item} />
          ))}
        </ul>
        <p className="mt-4 text-xs text-ink-500">{SCORING_NOTE}</p>
      </Panel>

      <Panel title="What this run does and does not establish">
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-300">
          <li>It shows how this model, with these settings, replied to {c.total} fixed prompts at this moment.</li>
          <li>A model can give a different reply to the same prompt next time, so a single run is one sample.</li>
          {run.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
          <li>Without saved runs there is no baseline, so this page cannot say whether the model improved or got worse.</li>
        </ul>
      </Panel>
    </div>
  );
}

function CaseCard({ item }: { item: EvaluationCaseDto }) {
  const noVerdict = item.status === 'ERROR' || item.status === 'SKIPPED';
  return (
    <li
      className={clsx(
        'rounded-lg border px-4 py-3',
        noVerdict ? 'border-dashed border-surface-600 bg-surface-900/40' : 'border-surface-700/60 bg-surface-800/30',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink-100">{item.name}</div>
          <div className="text-2xs text-ink-500">
            {item.category} · <span className="font-mono">{item.id}</span>
          </div>
        </div>
        <CaseBadge status={item.status} />
      </div>
      <p className="mt-2 text-sm text-ink-300">
        <span className="text-2xs font-medium uppercase tracking-wider text-ink-500">Expected </span>
        {item.expected}
      </p>
      <p className="mt-1 text-xs text-ink-500">
        <span className="font-medium uppercase tracking-wider">Basis </span>
        {verdictBasis(item.status)}
      </p>
      {item.failure && (
        <p className={clsx('mt-2 text-sm', noVerdict ? 'text-warning-300' : 'text-danger-300')}>
          <span className="text-2xs font-medium uppercase tracking-wider opacity-80">{noVerdict ? 'Why no verdict ' : 'Why it failed '}</span>
          {item.failure}
        </p>
      )}
      {item.evidence.length > 0 && (
        <div className="mt-2">
          <div className="text-2xs font-medium uppercase tracking-wider text-ink-500">Checks that decided the verdict</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-300">
            {item.evidence.map((code) => (
              <li key={code} title={code}>
                {evidenceLabel(code)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {item.observed_excerpt !== null && (
        <div className="mt-2">
          <div className="text-2xs font-medium uppercase tracking-wider text-ink-500">
            Model reply, first 400 characters ({item.observed_is})
          </div>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-surface-700/50 bg-surface-900/60 px-3 py-2 font-mono text-xs text-ink-300">
            {item.observed_excerpt === '' ? '(empty output)' : item.observed_excerpt}
          </pre>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-ink-500">
        {item.latency_ms !== null && <span>{Math.round(item.latency_ms)} ms (measured by the backend)</span>}
        {item.input_tokens !== null && <span>tokens {item.input_tokens}/{item.output_tokens ?? '—'} (reported by the provider)</span>}
      </div>
    </li>
  );
}

function CaseBadge({ status }: { status: CaseStatus }) {
  if (status === 'PASS') return <Badge variant="success">PASS</Badge>;
  if (status === 'FAIL') return <Badge variant="danger">FAIL</Badge>;
  if (status === 'ERROR') return <Badge variant="warning">ERROR · no verdict</Badge>;
  return <Badge variant="neutral">SKIPPED · no verdict</Badge>;
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-2xs font-medium uppercase tracking-wider text-ink-400">{label}</dt>
      <dd className={`mt-0.5 break-all text-ink-100 ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  );
}

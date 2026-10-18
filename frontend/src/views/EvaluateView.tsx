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
import { Panel, Button, Select, Badge, EmptyState, ErrorState, LoadingState, MetricCard } from '@/components/ui';
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
  const [runFailure, setRunFailure] = useState<RunFailure | null>(null);

  const loadOptions = useCallback(async () => {
    setOptionsPhase('loading');
    setOptionsError('');
    try {
      const [e, s] = await Promise.all([apiClient.getEndpoints(), apiClient.getTestSuites()]);
      setEndpoints(e.endpoints);
      setSuites(s.test_suites);
      setEndpoint(e.endpoints[0]?.name ?? '');
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
    setRunFailure(null);
    try {
      const res = await apiClient.runEvaluation(endpoint, suiteId);
      setRun(res.run);
      setRunPhase('done');
    } catch (err) {
      setRunFailure({
        code: err instanceof ApiError ? err.code : null,
        message: err instanceof Error ? err.message : 'The evaluation request failed.',
      });
      setRunPhase('error');
    }
  }, [endpoint, suiteId]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink-50">Evaluate & Safety</h1>
        <p className="mt-1 text-sm text-ink-400">
          Run a small synthetic safety suite against one configured model. Each case is scored from the model&apos;s output.
        </p>
      </div>

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
                  <option key={e.name} value={e.name}>
                    {e.name} — {e.provider === 'LOCAL' ? 'local' : 'hosted'}
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

      {runPhase === 'done' && run && <RunResult run={run} />}
    </div>
  );
}

function RunResult({ run }: { run: EvaluationRunDto }) {
  const statusBadge =
    run.status === 'COMPLETED' ? (
      <Badge variant="success" dot>Completed</Badge>
    ) : run.status === 'PARTIAL' ? (
      <Badge variant="warning" dot>Partial</Badge>
    ) : (
      <Badge variant="danger" dot>Failed</Badge>
    );
  const a = run.aggregate;
  const c = run.counts;

  return (
    <div className="space-y-5">
      <Panel
        title={`${run.suite.id} v${run.suite.version}`}
        subtitle={`${run.model.endpoint} · ${run.model.provider === 'LOCAL' ? 'local machine' : 'hosted provider'} · ${run.model.model_id}`}
        actions={statusBadge}
        accent
      >
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Detail label="Model ID" value={run.model.model_id} mono />
          <Detail label="Reported by provider as" value={run.model.served_model ?? 'not reported by the provider'} mono />
          <Detail label="Config hash" value={`${run.model.config_hash.slice(0, 12)}…`} mono />
          <Detail label="Prompt version" value={run.model.prompt_version} mono />
          <Detail label="Security profile" value={run.security_profile} mono />
          <Detail label="Data origin" value={run.data_origin} mono />
          <Detail label="Started" value={formatDateTime(run.started_at)} />
          <Detail label="Finished" value={formatDateTime(run.finished_at)} />
          <Detail label="Run ID" value={run.run_id} mono />
        </dl>
      </Panel>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Pass rate"
          value={a.pass_rate === null ? '—' : `${(a.pass_rate * 100).toFixed(0)}%`}
          sublabel={`${c.PASS} passed of ${c.scored} scored`}
          accent={a.pass_rate === 1}
        />
        <MetricCard
          label="Cases"
          value={`${c.scored}/${c.total}`}
          sublabel={`${c.ERROR} error · ${c.SKIPPED} skipped`}
        />
        <MetricCard
          label="Avg latency"
          value={a.avg_latency_ms === null ? '—' : `${Math.round(a.avg_latency_ms)} ms`}
          sublabel={a.avg_latency_ms === null ? 'no timing reported' : 'per model call'}
        />
        <MetricCard
          label="Tokens in / out"
          value={a.total_input_tokens === null ? 'not reported' : `${formatNumber(a.total_input_tokens)} / ${formatNumber(a.total_output_tokens ?? 0)}`}
          sublabel="reported by the provider only"
        />
      </div>

      <Panel
        title="Case results"
        subtitle="PASS and FAIL come from scoring the output. ERROR means the model call failed, so no verdict exists. SKIPPED means the run stopped first."
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
      </Panel>

      {run.limitations.length > 0 && (
        <Panel title="Limitations">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-300">
            {run.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function CaseCard({ item }: { item: EvaluationCaseDto }) {
  return (
    <li className="rounded-lg border border-surface-700/60 bg-surface-800/30 px-4 py-3">
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
      {item.failure && (
        <p className={clsx('mt-2 text-sm', item.status === 'ERROR' || item.status === 'SKIPPED' ? 'text-warning-300' : 'text-danger-300')}>
          {item.failure}
        </p>
      )}
      {item.observed_excerpt !== null && (
        <div className="mt-2">
          <div className="text-2xs font-medium uppercase tracking-wider text-ink-500">
            Observed ({item.observed_is})
          </div>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-surface-700/50 bg-surface-900/60 px-3 py-2 font-mono text-xs text-ink-300">
            {item.observed_excerpt === '' ? '(empty output)' : item.observed_excerpt}
          </pre>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-ink-500">
        {item.evidence.length > 0 && <span>checks: {item.evidence.join(', ')}</span>}
        {item.latency_ms !== null && <span>{Math.round(item.latency_ms)} ms</span>}
        {item.input_tokens !== null && <span>tokens {item.input_tokens}/{item.output_tokens ?? '—'}</span>}
      </div>
    </li>
  );
}

function CaseBadge({ status }: { status: CaseStatus }) {
  if (status === 'PASS') return <Badge variant="success">PASS</Badge>;
  if (status === 'FAIL') return <Badge variant="danger">FAIL</Badge>;
  if (status === 'ERROR') return <Badge variant="warning">ERROR</Badge>;
  return <Badge variant="neutral">SKIPPED</Badge>;
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-2xs font-medium uppercase tracking-wider text-ink-400">{label}</dt>
      <dd className={`mt-0.5 break-all text-ink-100 ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  );
}

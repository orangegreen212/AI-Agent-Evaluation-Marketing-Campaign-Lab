import { useCallback, useEffect, useState } from 'react';
import { Play, Check, AlertTriangle, XCircle, Eye } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import type { CompareResponse, CompareRunSummary, ModelOption, TestSuiteOption } from '@/types/api';
import type { TabId } from '@/components/Sidebar';
import { Panel, Button, Select, Badge, DataTable, DemoBanner, ErrorState, LoadingState, Provenance, PageGuide } from '@/components/ui';
import { formatPercent, formatNumber, formatCurrency, clsx } from '@/lib/utils';

type Phase = 'idle' | 'loading' | 'success' | 'error';

export function CompareView({ onNavigate }: { onNavigate: (tab: TabId) => void }) {
  // The sample is opt-in: nothing fabricated is shown, or even loaded, until the user asks for it.
  const [sampleOn, setSampleOn] = useState(false);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [suites, setSuites] = useState<TestSuiteOption[]>([]);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [suiteId, setSuiteId] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>('idle');
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!sampleOn) return;
    let active = true;
    (async () => {
      try {
        const [m, s] = await Promise.all([apiClient.listModels(), apiClient.listDemoTestSuites()]);
        if (!active) return;
        setModels(m.models);
        setSuites(s.testSuites);
        setSuiteId(s.testSuites[0]?.id ?? '');
        setSelectedIds(m.models.slice(0, 2).map((x) => x.id));
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Failed to load options.');
      } finally {
        if (active) setOptionsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [sampleOn]);

  const toggleModel = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const run = useCallback(async () => {
    if (selectedIds.length < 2 || !suiteId) return;
    setPhase('loading');
    setError('');
    try {
      const res = await apiClient.compare(selectedIds, suiteId);
      setData(res);
      setPhase('success');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison failed.');
      setPhase('error');
    }
  }, [selectedIds, suiteId]);

  const canRun = selectedIds.length >= 2 && !!suiteId;

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-ink-50">Compare Models</h1>
          <Badge variant="warning">Not built yet</Badge>
        </div>
        <p className="mt-1 text-sm text-ink-400">
          Planned: put the saved results of several models side by side. This page is a preview of that screen.
        </p>
      </div>

      <PageGuide
        purpose="Show how two or more models did on the same test suite, so you can choose between them or spot a regression."
        how="Not implemented. It would read stored run records from earlier evaluations. This version stores nothing."
        inputs="Today: none. The optional sample below uses fabricated fixtures, not results from Evaluate & Safety."
        output="The sample shows the intended layout only. Its numbers are not measurements and are unrelated to any model you have run."
        limits="Do not use anything on this page to judge a real model. To compare real models now, run Evaluate & Safety once per model and compare the case results yourself."
      />

      <Panel title="Status: planned, not implemented" accent>
        <p className="text-sm text-ink-300">
          Comparing models needs saved run records, baselines and a comparison step (see <span className="font-mono text-xs">docs/PHASE3_SPEC.md</span>).
          None of that exists in the code yet, so this page cannot compare anything real.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="primary" onClick={() => onNavigate('evaluate')}>
            Run a real evaluation instead
          </Button>
          {!sampleOn && (
            <Button variant="secondary" icon={<Eye className="h-4 w-4" />} onClick={() => setSampleOn(true)}>
              Preview the layout with sample data
            </Button>
          )}
          {sampleOn && (
            <Button variant="ghost" onClick={() => { setSampleOn(false); setPhase('idle'); setData(null); }}>
              Hide the sample
            </Button>
          )}
        </div>
      </Panel>

      {sampleOn && (
        <div className="space-y-5">
          <Provenance kinds={['sample']}>Fabricated fixtures from src/demo. Not connected to the backend.</Provenance>
      <DemoBanner message="Sample screen. Every number, model name and finding below is fabricated. No model is called and nothing here was measured." />
  
        <Panel title="Sample configuration" subtitle="Fictional models and a fictional suite">
          {optionsLoading ? (
            <LoadingState label="Loading models and test suites…" />
          ) : (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_auto]">
                <Select
                  label="Test suite"
                  value={suiteId}
                  onChange={setSuiteId}
                  hint={suites.find((s) => s.id === suiteId)?.description}
                >
                  {suites.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.caseCount} cases)
                    </option>
                  ))}
                </Select>
                <div className="flex items-end">
                  <Button
                    variant="primary"
                    icon={<Play className="h-4 w-4" />}
                    loading={phase === 'loading'}
                    onClick={run}
                    disabled={!canRun}
                    className="w-full lg:w-auto"
                  >
                    Show sample comparison
                  </Button>
                </div>
              </div>
  
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-2xs font-medium uppercase tracking-wider text-ink-400">
                    Select models ({selectedIds.length} selected)
                  </span>
                  {selectedIds.length < 2 && (
                    <span className="text-2xs text-warning-400">Select at least 2 models</span>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {models.map((m) => {
                    const checked = selectedIds.includes(m.id);
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => toggleModel(m.id)}
                        className={clsx(
                          'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all',
                          checked
                            ? 'border-accent-500/50 bg-accent-500/10'
                            : 'border-surface-700/70 bg-surface-800/40 hover:border-surface-600',
                        )}
                      >
                        <span
                          className={clsx(
                            'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                            checked
                              ? 'border-accent-400 bg-accent-400 text-surface-950'
                              : 'border-surface-600',
                          )}
                        >
                          {checked && <Check className="h-3 w-3" strokeWidth={3} />}
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-ink-100">{m.name}</div>
                          <div className="truncate text-2xs text-ink-500">
                            {m.provider} · {formatNumber(m.contextWindow)} ctx
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </Panel>
  
        {error && phase !== 'error' && (
          <ErrorState title="Could not load models or test suites" message={error} />
        )}
  
        {phase === 'idle' && (
          <p className="rounded-xl border border-dashed border-surface-700 bg-surface-900/40 px-6 py-8 text-center text-xs text-ink-400">
            Choose at least two sample models and click &ldquo;Show sample comparison&rdquo; to see the layout with fabricated numbers.
          </p>
        )}
  
        {phase === 'loading' && <LoadingState label="Building the sample layout. No comparison is run." />}
  
        {phase === 'error' && <ErrorState message={error} onRetry={run} />}
  
        {phase === 'success' && data && <ComparisonResults data={data} />}
          </div>
      )}
    </div>
  );
}

function ComparisonResults({ data }: { data: CompareResponse }) {
  const { runs, testSuiteName } = data;
  const anyIncomplete = runs.some((r) => r.status !== 'completed');

  return (
    <div className="space-y-5">
      <Panel
        title={`Sample comparison — ${testSuiteName}`}
        subtitle={`${runs.length} models`}
        accent
        actions={
          anyIncomplete ? (
            <Badge variant="warning" dot>
              Contains incomplete runs
            </Badge>
          ) : (
            <Badge variant="neutral" dot>
              Sample runs all complete
            </Badge>
          )
        }
      >
        {anyIncomplete && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning-500/30 bg-warning-500/5 px-3 py-2 text-xs text-warning-300">
            <AlertTriangle className="h-4 w-4" />
            One or more runs did not complete fully — metrics for those models may be partial.
          </div>
        )}
        <DataTable
          columns={compareColumns()}
          rows={runs}
          rowKey={(r) => r.runId}
        />
      </Panel>

      {/* Side-by-side cards */}
      <div className={clsx(
        'grid gap-4',
        runs.length === 2 && 'grid-cols-1 sm:grid-cols-2',
        runs.length === 3 && 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
        runs.length >= 4 && 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
      )}>
        {runs.map((run) => (
          <ModelRunCard key={run.runId} run={run} />
        ))}
      </div>

      {/* Findings summary */}
      <Panel title="Report validity & safety findings" subtitle="Per-model summary">
        <DataTable
          dense
          columns={[
            { key: 'model', header: 'Model', render: (r) => (
              <span className="flex items-center gap-2 font-medium text-ink-100">{r.modelName}<Badge variant="warning">sample</Badge></span>
            ) },
            {
              key: 'valid',
              header: 'Report valid',
              render: (r) =>
                r.reportValid ? (
                  <Badge variant="neutral" dot>Valid</Badge>
                ) : (
                  <Badge variant="danger" dot>Invalid</Badge>
                ),
            },
            { key: 'status', header: 'Status', render: (r) => <SampleStatus status={r.status} /> },
            {
              key: 'findings',
              header: 'Findings',
              className: 'text-right',
              render: (r) => <span className="font-mono tabular-nums">{r.findingCount}</span>,
            },
            {
              key: 'critical',
              header: 'Critical',
              className: 'text-right',
              render: (r) => (
                <span className={clsx('font-mono tabular-nums', r.criticalCount > 0 ? 'text-danger-400' : 'text-ink-300')}>
                  {r.criticalCount}
                </span>
              ),
            },
          ]}
          rows={runs}
          rowKey={(r) => r.runId}
        />
      </Panel>
    </div>
  );
}

function compareColumns(): import('@/components/ui').Column<CompareRunSummary>[] {
  return [
    {
      key: 'model',
      header: 'Model',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink-100">{r.modelName}</span>
          <Badge variant="warning">sample</Badge>
        </div>
      ),
    },
    { key: 'status', header: 'Status', render: (r) => <SampleStatus status={r.status} /> },
    {
      key: 'passRate',
      header: 'Pass rate',
      className: 'text-right',
      render: (r) => (
        <span className="font-mono tabular-nums text-ink-100">
          {formatPercent(r.passRate)}
        </span>
      ),
    },
    {
      key: 'latency',
      header: 'Avg latency',
      className: 'text-right',
      render: (r) => <span className="font-mono tabular-nums">{r.avgLatencyMs !== null ? `${Math.round(r.avgLatencyMs)}ms` : '—'}</span>,
    },
    {
      key: 'tokens',
      header: 'Tokens (in/out)',
      className: 'text-right',
      render: (r) => (
        <span className="font-mono tabular-nums">
          {r.avgInputTokens !== null ? `${Math.round(r.avgInputTokens)}/${Math.round(r.avgOutputTokens ?? 0)}` : '—'}
        </span>
      ),
    },
    {
      key: 'cost',
      header: 'Cost',
      className: 'text-right',
      render: (r) => <span className="font-mono tabular-nums">{r.totalCostUsd !== null ? formatCurrency(r.totalCostUsd, 4) : '—'}</span>,
    },
    {
      key: 'findings',
      header: 'Findings',
      className: 'text-right',
      render: (r) => (
        <span className={clsx('font-mono tabular-nums', r.criticalCount > 0 ? 'text-danger-400' : 'text-ink-200')}>
          {r.findingCount} ({r.criticalCount} crit)
        </span>
      ),
    },
  ];
}

function ModelRunCard({ run }: { run: CompareRunSummary }) {
  const incomplete = run.status !== 'completed';
  return (
    <Panel
      className={incomplete ? 'border-warning-500/30' : ''}
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-ink-100">{run.modelName}<Badge variant="warning">sample</Badge></div>
          <div className="text-2xs text-ink-500">{run.testSuiteName}</div>
        </div>
        <SampleStatus status={run.status} />
      </div>
      {incomplete && (
        <div className="mb-3 flex items-center gap-1.5 rounded border border-warning-500/30 bg-warning-500/5 px-2 py-1.5 text-2xs text-warning-300">
          <XCircle className="h-3 w-3" />
          Run incomplete — metrics partial
        </div>
      )}
      <div className="space-y-2.5">
        <MiniMetric label="Pass rate" value={formatPercent(run.passRate)} />
        <MiniMetric label="Avg latency" value={run.avgLatencyMs !== null ? `${Math.round(run.avgLatencyMs)}ms` : '—'} />
        <MiniMetric label="Tokens in/out" value={run.avgInputTokens !== null ? `${Math.round(run.avgInputTokens)}/${Math.round(run.avgOutputTokens ?? 0)}` : '—'} />
        <MiniMetric label="Cost" value={run.totalCostUsd !== null ? formatCurrency(run.totalCostUsd, 4) : '—'} />
        <MiniMetric
          label="Findings"
          value={`${run.findingCount} (${run.criticalCount} critical)`}
          danger={run.criticalCount > 0}
        />
      </div>
    </Panel>
  );
}

function MiniMetric({ label, value, highlight, danger }: { label: string; value: string; highlight?: boolean; danger?: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-surface-700/40 pb-2 last:border-0">
      <span className="text-2xs text-ink-400">{label}</span>
      <span className={clsx(
        'font-mono text-sm tabular-nums',
        highlight ? 'text-success-400' : danger ? 'text-danger-400' : 'text-ink-100',
      )}>
        {value}
      </span>
    </div>
  );
}

function SampleStatus({ status }: { status: CompareRunSummary['status'] }) {
  const label = status === 'completed' ? 'Complete' : status === 'partial' ? 'Partial' : status === 'failed' ? 'Failed' : status;
  return <Badge variant={status === 'completed' ? 'neutral' : 'warning'} dot>{label}</Badge>;
}

import { useCallback, useEffect, useState } from 'react';
import { Play, GitCompare, Check, AlertTriangle, XCircle } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import type { CompareResponse, CompareRunSummary, ModelOption, TestSuiteOption } from '@/types/api';
import { Panel, Button, Select, Badge, StatusBadge, DataTable, DemoBanner, EmptyState, ErrorState, LoadingState } from '@/components/ui';
import { formatPercent, formatNumber, formatCurrency, clsx } from '@/lib/utils';

type Phase = 'idle' | 'loading' | 'success' | 'error';

export function CompareView() {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [suites, setSuites] = useState<TestSuiteOption[]>([]);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [suiteId, setSuiteId] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>('idle');
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
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
  }, []);

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
        <h1 className="text-xl font-semibold text-ink-50">Compare Models</h1>
        <p className="mt-1 text-sm text-ink-400">
          Run the same test suite against two or more models and compare latency, tokens, cost, and safety side-by-side.
        </p>
      </div>

      <DemoBanner message="Demo only: not connected to the backend. Results are fixtures, not real model comparisons." />

      <Panel title="Run configuration">
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
                  Run comparison
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
        <EmptyState
          icon={<GitCompare className="h-8 w-8" />}
          title="No comparison run yet"
          description="Select two or more models and a shared test suite, then run the comparison to see side-by-side results."
        />
      )}

      {phase === 'loading' && <LoadingState label="Generating demo results — no comparison is run…" />}

      {phase === 'error' && <ErrorState message={error} onRetry={run} />}

      {phase === 'success' && data && <ComparisonResults data={data} />}
    </div>
  );
}

function ComparisonResults({ data }: { data: CompareResponse }) {
  const { runs, testSuiteName } = data;
  const bestPassRate = Math.max(...runs.map((r) => r.passRate));
  const anyIncomplete = runs.some((r) => r.status !== 'completed');

  return (
    <div className="space-y-5">
      <Panel
        title={`Comparison — ${testSuiteName}`}
        subtitle={`${runs.length} models`}
        accent
        actions={
          anyIncomplete ? (
            <Badge variant="warning" dot>
              Contains incomplete runs
            </Badge>
          ) : (
            <Badge variant="success" dot>
              All runs completed
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
          columns={compareColumns(bestPassRate)}
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
          <ModelRunCard key={run.runId} run={run} bestPassRate={bestPassRate} />
        ))}
      </div>

      {/* Findings summary */}
      <Panel title="Report validity & safety findings" subtitle="Per-model summary">
        <DataTable
          dense
          columns={[
            { key: 'model', header: 'Model', render: (r) => <span className="font-medium text-ink-100">{r.modelName}</span> },
            {
              key: 'valid',
              header: 'Report valid',
              render: (r) =>
                r.reportValid ? (
                  <Badge variant="success" dot>Valid</Badge>
                ) : (
                  <Badge variant="danger" dot>Invalid</Badge>
                ),
            },
            { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
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

function compareColumns(bestPassRate: number): import('@/components/ui').Column<CompareRunSummary>[] {
  return [
    {
      key: 'model',
      header: 'Model',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink-100">{r.modelName}</span>
          {r.passRate === bestPassRate && r.status === 'completed' && (
            <Badge variant="accent">Best</Badge>
          )}
        </div>
      ),
    },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    {
      key: 'passRate',
      header: 'Pass rate',
      className: 'text-right',
      render: (r) => (
        <span className={clsx('font-mono tabular-nums', r.passRate === bestPassRate && r.status === 'completed' ? 'text-success-400' : 'text-ink-100')}>
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

function ModelRunCard({ run, bestPassRate }: { run: CompareRunSummary; bestPassRate: number }) {
  const incomplete = run.status !== 'completed';
  return (
    <Panel
      accent={run.passRate === bestPassRate && !incomplete}
      className={incomplete ? 'border-warning-500/30' : ''}
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-ink-100">{run.modelName}</div>
          <div className="text-2xs text-ink-500">{run.testSuiteName}</div>
        </div>
        <StatusBadge status={run.status} />
      </div>
      {incomplete && (
        <div className="mb-3 flex items-center gap-1.5 rounded border border-warning-500/30 bg-warning-500/5 px-2 py-1.5 text-2xs text-warning-300">
          <XCircle className="h-3 w-3" />
          Run incomplete — metrics partial
        </div>
      )}
      <div className="space-y-2.5">
        <MiniMetric label="Pass rate" value={formatPercent(run.passRate)} highlight={run.passRate === bestPassRate && !incomplete} />
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
